from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .models import MixPlan, OutputDurationPolicy, UnderVoice


def require_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("ffmpeg executable not found on PATH")
    return executable


def has_audio_stream(path) -> bool:
    """True when the media file carries at least one audio stream.

    Screen recordings, exported edits and some phone clips have no audio
    track at all; mapping [0:a] on those makes FFmpeg fail outright.
    """
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe executable not found on PATH")
    completed = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("ffprobe failed:\n" + completed.stderr)
    return bool(completed.stdout.strip())


def measure_levels(path) -> tuple[float, float] | None:
    """(mean, peak) level in dBFS of the first audio stream, or None when the
    file has no audio. Uses FFmpeg's volumedetect."""
    if not has_audio_stream(path):
        return None
    completed = subprocess.run(
        [require_ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    mean = peak = None
    for line in completed.stderr.splitlines():
        if "mean_volume:" in line:
            mean = float(line.split("mean_volume:")[1].split()[0])
        elif "max_volume:" in line:
            peak = float(line.split("max_volume:")[1].split()[0])
    if mean is None or peak is None:
        raise RuntimeError("Could not measure audio level of " + str(path))
    return mean, peak


def build_filter_complex(plan: MixPlan, *, original_audio_available: bool = True) -> str:
    use_original = plan.original_audio_enabled and original_audio_available
    use_voice = plan.voice_enabled
    # Input order: 0 video, then music (when enabled), then voiceover (when enabled).
    music_index = 1
    voice_index = 2 if plan.music_enabled else 1
    inputs = []
    carriers = []   # labels of the audio streams that go into the mix

    if use_original:
        original_filters = [f"volume={plan.original_audio_gain_db}dB"]
        if use_voice and plan.voice_windows:
            drop = -60.0 if plan.original_under_voice == UnderVoice.DROP else plan.original_under_voice_db
            original_filters.append(_dip_filter(
                [(w.start_seconds, w.end_seconds, drop) for w in plan.voice_windows],
                plan.ducking_ramp_seconds))
        inputs.append("[0:a]" + ",".join(original_filters) + "[original]")
        carriers.append("[original]")

    if plan.music_enabled:
        music_filters = [f"volume={plan.music_gain_db}dB"]
        if plan.music_start_seconds > 0:
            music_filters.insert(0, f"adelay={plan.music_start_seconds * 1000:.0f}:all=1")
        if plan.music_fade_in_seconds > 0:
            music_filters.append(
                f"afade=t=in:st={plan.music_start_seconds}:d={plan.music_fade_in_seconds}"
            )
        if plan.music_end_seconds is not None and plan.music_fade_out_seconds > 0:
            fade_start = max(plan.music_start_seconds,
                             plan.music_end_seconds - plan.music_fade_out_seconds)
            music_filters.append(
                f"afade=t=out:st={fade_start}:d={plan.music_fade_out_seconds}"
            )
        if plan.ducking:
            music_filters.append(_ducking_filter(plan))
        inputs.append(f"[{music_index}:a]" + ",".join(music_filters) + "[music]")
        carriers.append("[music]")

    if use_voice:
        # Upmix to stereo so a mono voiceover sits in the centre of the mix.
        inputs.append(f"[{voice_index}:a]volume={plan.voice_gain_db}dB,"
                      "aformat=channel_layouts=stereo[voice]")
        carriers.append("[voice]")

    if not carriers:
        if plan.original_audio_enabled and not original_audio_available:
            raise ValueError("MixPlan uses only the original audio, but the video has no audio track")
        raise ValueError("MixPlan disables both audio sources")

    if len(carriers) == 1:
        label = carriers[0]
        if not use_original and plan.output_duration_policy == OutputDurationPolicy.VIDEO:
            # Pad so a short track never cuts the picture; execute_mix then
            # stops at the end of the video with -shortest.
            inputs.append(f"{label}apad[mixed]")
        else:
            inputs.append(f"{label}anull[mixed]")
    else:
        # normalize=0: amix otherwise scales every input by 1/inputs, which
        # silently lowers the original audio (speech) by about 6 dB even when
        # the music is muted. The plan's gains are meant to be absolute.
        # With the original present it sets the length; without it the longest
        # track does, and the video policy pads and trims to the picture.
        duration = "first" if use_original else "longest"
        mixer = (f"{''.join(carriers)}amix=inputs={len(carriers)}:duration={duration}:"
                 "dropout_transition=2:normalize=0")
        if not use_original and plan.output_duration_policy == OutputDurationPolicy.VIDEO:
            mixer += ",apad"
        inputs.append(mixer + "[mixed]")

    if plan.output_loudness_lufs is not None:
        # One-pass EBU R128 normalisation: quiet phone recordings come up to a
        # consistent level, true peaks stay under -1.5 dBTP. loudnorm works at
        # 192 kHz internally, so resample back for the AAC encoder.
        inputs.append(f"[mixed]loudnorm=I={plan.output_loudness_lufs}:TP=-1.5:LRA=11,aresample=48000[aout]")
    else:
        inputs.append("[mixed]anull[aout]")
    return ";".join(inputs)


def _dip_expr(dips, ramp_seconds: float) -> str:
    """Gain change in dB over time. At time t each (start, end, drop_db) pulls
    the gain toward its drop by a weight that ramps 0 -> 1 -> 0 around it;
    where dips overlap the deepest drop wins."""
    ramp = max(ramp_seconds, 0.01)
    terms = []
    for start, end, drop in dips:
        weight = (f"clip(min((t-{start - ramp:.3f})/{ramp:.3f},"
                  f"({end + ramp:.3f}-t)/{ramp:.3f}),0,1)")
        terms.append(f"{drop:.2f}*{weight}")
    expr = terms[0]
    for term in terms[1:]:
        expr = f"min({expr},{term})"
    return expr


def _dip_filter(dips, ramp_seconds: float) -> str:
    # Commas inside the expression are escaped for the filtergraph parser.
    expr = _dip_expr(dips, ramp_seconds)
    return "volume=eval=frame:volume='pow(10,(" + expr.replace(",", "\\,") + ")/20)'"


def _ducking_filter(plan: MixPlan) -> str:
    """One volume filter whose gain follows every ducking segment, easing in
    and out over ducking_ramp_seconds."""
    return _dip_filter([(seg.start_seconds, seg.end_seconds, seg.music_gain_db - plan.music_gain_db)
                        for seg in plan.ducking], plan.ducking_ramp_seconds)


def execute_mix(video, music, plan: MixPlan, output, voiceover=None) -> Path:
    executable = require_ffmpeg()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if plan.voice_enabled and voiceover is None:
        raise ValueError("MixPlan has voice_enabled but no voiceover file was given")
    original_audio_available = has_audio_stream(video)
    # Without the video's own sound, the music and/or voice carry the track.
    carried_by_added_audio = not (plan.original_audio_enabled and original_audio_available)

    command = [executable, "-y", "-i", str(video)]
    if plan.music_enabled:
        command += ["-i", str(music)]
    if plan.voice_enabled:
        command += ["-i", str(voiceover)]
    command += [
        "-filter_complex", build_filter_complex(plan, original_audio_available=original_audio_available),
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-movflags", "+faststart",
    ]
    if plan.output_duration_policy == OutputDurationPolicy.SHORTEST or (
        carried_by_added_audio and plan.output_duration_policy == OutputDurationPolicy.VIDEO
    ):
        command.append("-shortest")
    command.append(str(output_path))

    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError("FFmpeg failed:\n" + completed.stderr)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg reported success but output is missing or empty")
    return output_path
