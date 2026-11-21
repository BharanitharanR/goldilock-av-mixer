import json
import shutil
import subprocess

import pytest

from video_audio_mixer.context import discover_context
from video_audio_mixer.deterministic import default_plan
from video_audio_mixer.ffmpeg import build_filter_complex, execute_mix, measure_levels
from video_audio_mixer.models import MixPlan, UnderVoice, VoiceWindow
from video_audio_mixer.voice import merge_windows, voice_gain_for, windows_from_timeline

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def _timeline(tmp_path, spans):
    path = tmp_path / "voiceover-timeline.json"
    path.write_text(json.dumps({"schema_version": "1.0", "lines": [
        {"segment_index": i, "turn_index": None, "speaker": "A", "text": "x",
         "start_seconds": a, "end_seconds": b, "speed_factor": 1.0, "fit_status": "fits"}
        for i, (a, b) in enumerate(spans)]}))
    return path


def test_windows_are_padded_and_merged_when_gap_is_small():
    w = merge_windows([(1.0, 2.0), (2.3, 3.0), (6.0, 7.0)], 10.0)
    assert [(x.start_seconds, x.end_seconds) for x in w] == [(0.85, 3.15), (5.85, 7.15)]


def test_windows_clamp_to_the_video(tmp_path):
    w = windows_from_timeline(_timeline(tmp_path, [(0.05, 1.0), (9.9, 10.0)]), 10.0)
    assert w[0].start_seconds == 0.0 and w[-1].end_seconds == 10.0


def test_voice_gain_targets_mean_and_respects_peak():
    assert voice_gain_for(-27.0, -12.0)[0] == 10.0
    assert voice_gain_for(-27.0, -3.0)[0] == 2.0      # peak ceiling -1 dBFS


def test_plan_with_voice_dips_music_and_trims_speech_ducking():
    from video_audio_mixer.speech import SpeechSegment
    windows = [VoiceWindow(start_seconds=2, end_seconds=4)]
    speech = [SpeechSegment(1.0, 3.0), SpeechSegment(6.0, 7.0)]
    plan = default_plan(10.0, original_mean_db=-20.0, music_mean_db=-16.0, music_peak_db=-2.0,
                        speech_segments=speech, voice_windows=windows, voice_mean_db=-27.0,
                        voice_peak_db=-12.0)
    assert plan.voice_enabled and plan.voice_gain_db == 10.0
    spans = [(d.start_seconds, d.end_seconds, d.music_gain_db - plan.music_gain_db) for d in plan.ducking]
    assert spans == [(1.0, 2.0, -8.0), (2.0, 4.0, -11.0), (6.0, 7.0, -8.0)]
    assert any("voiceover windows" in n for n in plan.notes)
    assert plan.original_under_voice == UnderVoice.KEEP


def test_no_voice_plan_is_unchanged():
    plan = default_plan(10.0, music_mean_db=-20.0, music_peak_db=-3.0)
    assert not plan.voice_enabled and plan.voice_windows == []


def test_filter_has_three_inputs_and_original_dip():
    plan = default_plan(10.0, original_mean_db=-20.0, music_mean_db=-16.0, music_peak_db=-2.0,
                        voice_windows=[VoiceWindow(start_seconds=2, end_seconds=4)],
                        voice_mean_db=-27.0, voice_peak_db=-12.0)
    g = build_filter_complex(plan)
    assert "[2:a]volume=10.0dB" in g and "amix=inputs=3:duration=first" in g and "normalize=0" in g
    assert "[0:a]volume=0.0dB,volume=eval=frame" in g and "-12.00*clip" in g


def test_drop_mode_mutes_original_in_windows():
    plan = MixPlan(purpose="t", voice_enabled=True, original_under_voice="drop",
                   voice_windows=[VoiceWindow(start_seconds=2, end_seconds=4)])
    assert "-60.00*clip" in build_filter_complex(plan)


def test_voice_without_music_uses_input_one():
    plan = MixPlan(purpose="t", music_enabled=False, voice_enabled=True)
    g = build_filter_complex(plan)
    assert "[1:a]volume=" in g and "[2:a]" not in g and "amix=inputs=2" in g


def test_voice_only_on_silent_video_is_padded():
    plan = MixPlan(purpose="t", music_enabled=False, voice_enabled=True)
    assert "[voice]apad[mixed]" in build_filter_complex(plan, original_audio_available=False)


def test_discover_picks_up_voiceover_and_keeps_it_out_of_music(tmp_path):
    for n in ["input.mp4", "song.wav", "voiceover.wav"]:
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "analysis.json").write_text("{}")
    (tmp_path / "song-spec.json").write_text("{}")
    (tmp_path / "voiceover-timeline.json").write_text("{}")
    ctx = discover_context(tmp_path)
    assert ctx.music_path.endswith("song.wav")
    assert ctx.voiceover_path.endswith("voiceover.wav")
    assert ctx.voice_timeline_path.endswith("voiceover-timeline.json")
    (tmp_path / "other.json").write_text("{}")
    assert discover_context(tmp_path, voice_timeline="other.json").voice_timeline_path.endswith("other.json")


# ---- real ffmpeg runs on tiny synthetic files ----

def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True, check=True).stdout
    return float(out)


@pytest.fixture
def media(tmp_path):
    d = 6
    _ff("-f", "lavfi", "-i", f"testsrc=size=64x48:rate=10:duration={d}", "-f", "lavfi",
        "-i", f"sine=f=220:d={d}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        str(tmp_path / "with_audio.mp4"))
    _ff("-f", "lavfi", "-i", f"testsrc=size=64x48:rate=10:duration={d}", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", str(tmp_path / "silent.mp4"))
    _ff("-f", "lavfi", "-i", "sine=f=440:d=4", "-ac", "2", str(tmp_path / "music.wav"))
    # 48 kHz mono, exactly the video length: tone from 1 s to 3 s, silence elsewhere.
    _ff("-f", "lavfi", "-i", f"aevalsrc='if(between(t,1,3),0.3*sin(2*PI*600*t),0)':s=48000:d={d}",
        "-ac", "1", str(tmp_path / "voiceover.wav"))
    return tmp_path


def _plan(**kw):
    return default_plan(6.0, original_mean_db=-20.0, music_mean_db=-16.0, music_peak_db=-2.0,
                        voice_windows=[VoiceWindow(start_seconds=0.85, end_seconds=3.15)],
                        voice_mean_db=-10.0, voice_peak_db=-10.0, **kw)


@needs_ffmpeg
@pytest.mark.parametrize("mode", ["keep", "drop"])
def test_video_with_audio_music_and_voice(media, mode):
    out = execute_mix(media / "with_audio.mp4", media / "music.wav", _plan(original_under_voice=mode),
                      media / f"out_{mode}.mp4", voiceover=media / "voiceover.wav")
    assert abs(_duration(out) - 6.0) < 0.3
    assert measure_levels(out) is not None


@needs_ffmpeg
def test_silent_video_with_music_and_voice(media):
    plan = default_plan(6.0, music_mean_db=-16.0, music_peak_db=-2.0,
                        voice_windows=[VoiceWindow(start_seconds=0.85, end_seconds=3.15)],
                        voice_mean_db=-10.0, voice_peak_db=-10.0)
    out = execute_mix(media / "silent.mp4", media / "music.wav", plan, media / "out.mp4",
                      voiceover=media / "voiceover.wav")
    assert abs(_duration(out) - 6.0) < 0.3     # music is 4 s: padded to the picture
    assert measure_levels(out) is not None


@needs_ffmpeg
def test_voice_without_music(media):
    plan = _plan().model_copy(update={"music_enabled": False, "ducking": []})
    out = execute_mix(media / "with_audio.mp4", media / "music.wav", plan, media / "out.mp4",
                      voiceover=media / "voiceover.wav")
    assert abs(_duration(out) - 6.0) < 0.3 and measure_levels(out) is not None
    silent = execute_mix(media / "silent.mp4", media / "music.wav", plan, media / "out2.mp4",
                         voiceover=media / "voiceover.wav")
    assert abs(_duration(silent) - 6.0) < 0.3 and measure_levels(silent) is not None


@needs_ffmpeg
def test_voice_gain_measured_on_the_active_part(media):
    from video_audio_mixer.voice import measure_voice_level
    mean, peak = measure_voice_level(media / "voiceover.wav")
    assert -14 < mean < -11 and peak < -8       # 0.3 sine: about -13.5 dB mean over active frames


def test_missing_voiceover_file_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="voiceover"):
        execute_mix(tmp_path / "v.mp4", tmp_path / "m.wav", MixPlan(purpose="t", voice_enabled=True),
                    tmp_path / "o.mp4")
