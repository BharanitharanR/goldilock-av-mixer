from __future__ import annotations

from .voice import voice_gain_for
from .models import DuckingSegment, MixPlan, UnderVoice, VoiceWindow

# Average (mean) level the music should land at, in dBFS, before the final
# loudness normalisation brings the whole mix to OUTPUT_LOUDNESS_LUFS.
MUSIC_ALONE_TARGET_DB = -18.0      # when the video has no meaningful sound of its own
MUSIC_UNDER_ORIGINAL_DB = 4.0      # music sits this far below the video's own level
SPEECH_DUCK_DB = 8.0               # and drops this much more while someone speaks
NEAR_SILENT_ORIGINAL_DB = -45.0    # below this mean, the video's audio is treated as silent
PEAK_CEILING_DB = -1.0             # never push the music's peaks above this
FALLBACK_MUSIC_GAIN_DB = -16.0     # used only when levels could not be measured
OUTPUT_LOUDNESS_LUFS = -16.0       # common target for social video
DUCK_RAMP_SECONDS = 0.25
VOICE_MUSIC_DUCK_DB = 11.0         # music dips this much more under the voiceover
ORIGINAL_UNDER_VOICE_DB = -12.0    # "keep": original audio sits this far down under the voice
MIN_SPEECH_REMNANT_SECONDS = 0.30  # original-speech ducking pieces shorter than this are dropped


def music_gain_for(original_mean_db: float | None, music_mean_db: float | None,
                   music_peak_db: float | None) -> tuple[float, str]:
    """Music gain (dB) that places the music by measured level, not by a fixed
    offset. A fixed -16 dB under a near-silent video left the soundtrack around
    -36 dB; a fixed 10 dB under a quiet phone recording made it inaudible."""
    if music_mean_db is None:
        return FALLBACK_MUSIC_GAIN_DB, "Music level unknown: fixed -16 dB gain."
    if original_mean_db is None or original_mean_db < NEAR_SILENT_ORIGINAL_DB:
        target = MUSIC_ALONE_TARGET_DB
        why = ("Video has no audio track" if original_mean_db is None
               else f"Video audio is near-silent ({original_mean_db:.1f} dB mean)")
        why += f": music carries the soundtrack at about {target:.0f} dB mean."
    else:
        target = min(original_mean_db - MUSIC_UNDER_ORIGINAL_DB, MUSIC_ALONE_TARGET_DB)
        why = (f"Video audio at {original_mean_db:.1f} dB mean: music placed about "
               f"{original_mean_db - target:.0f} dB below it.")
    gain = target - music_mean_db
    if music_peak_db is not None:
        gain = min(gain, PEAK_CEILING_DB - music_peak_db)
    gain = round(max(-40.0, min(12.0, gain)), 1)
    return gain, why


def _subtract(start: float, end: float, windows) -> list[tuple[float, float]]:
    pieces = [(start, end)]
    for w in windows:
        nxt = []
        for a, b in pieces:
            if w.end_seconds <= a or w.start_seconds >= b:
                nxt.append((a, b))
                continue
            if w.start_seconds > a:
                nxt.append((a, w.start_seconds))
            if w.end_seconds < b:
                nxt.append((w.end_seconds, b))
        pieces = nxt
    return pieces


def add_voice_layer(plan: MixPlan, windows: list[VoiceWindow], *, voice_gain_db: float,
                    voice_note: str, original_under_voice: UnderVoice | str = UnderVoice.KEEP,
                    original_available: bool = True) -> MixPlan:
    """Adds the voiceover to a plan: voice gain, windows, a further music dip
    inside each window and the original audio dip. Ducking from detected
    original speech is trimmed to the stretches outside the windows, so the
    same moment is never ducked twice."""
    mode = UnderVoice(original_under_voice)
    notes = list(plan.notes)
    notes.append(voice_note)
    outside = []
    for seg in plan.ducking:
        for a, b in _subtract(seg.start_seconds, seg.end_seconds, windows):
            if b - a >= MIN_SPEECH_REMNANT_SECONDS:
                outside.append(seg.model_copy(update={"start_seconds": round(a, 3), "end_seconds": round(b, 3)}))
    if plan.ducking:
        notes.append("Original-speech ducking kept only outside voiceover windows "
                     f"({len(plan.ducking)} -> {len(outside)} stretches), so nothing is ducked twice.")
    voice_duck = [DuckingSegment(start_seconds=w.start_seconds, end_seconds=w.end_seconds,
                                 music_gain_db=round(plan.music_gain_db - VOICE_MUSIC_DUCK_DB, 1),
                                 reason="voiceover window (timeline)")
                  for w in windows]
    if plan.music_enabled and windows:
        notes.append(f"{len(windows)} voiceover windows (timeline times, padded 0.15 s, merged under 0.4 s): "
                     f"music drops a further {VOICE_MUSIC_DUCK_DB:.0f} dB in each, easing over "
                     f"{plan.ducking_ramp_seconds} s.")
    if original_available and windows:
        notes.append(f"Original audio {'muted' if mode == UnderVoice.DROP else f'lowered {-ORIGINAL_UNDER_VOICE_DB:.0f} dB'} "
                     "inside voiceover windows, unchanged elsewhere.")
    return plan.model_copy(update={
        "voice_enabled": True,
        "voice_gain_db": voice_gain_db,
        "voice_windows": windows,
        "original_under_voice": mode,
        "original_under_voice_db": ORIGINAL_UNDER_VOICE_DB,
        "ducking": sorted(outside + voice_duck, key=lambda d: d.start_seconds) if plan.music_enabled else outside,
        "notes": notes,
        "purpose": plan.purpose + " Voiceover on top, music and original audio dip under it.",
    })


def default_plan(duration_seconds: float | None, *, original_mean_db: float | None = None,
                 music_mean_db: float | None = None, music_peak_db: float | None = None,
                 speech_segments=None, voice_windows=None, voice_mean_db: float | None = None,
                 voice_peak_db: float | None = None,
                 original_under_voice: UnderVoice | str = UnderVoice.KEEP) -> MixPlan:
    gain, why = music_gain_for(original_mean_db, music_mean_db, music_peak_db)
    notes = [why]
    ducking = []
    audible = original_mean_db is not None and original_mean_db >= NEAR_SILENT_ORIGINAL_DB
    if speech_segments and audible:
        ducking = [DuckingSegment(start_seconds=s.start_seconds, end_seconds=s.end_seconds,
                                  music_gain_db=round(gain - SPEECH_DUCK_DB, 1),
                                  reason="speech (rule-based: level, pitch, voice band, syllable rhythm)")
                   for s in speech_segments]
        total = sum(s.end_seconds - s.start_seconds for s in speech_segments)
        notes.append(f"Speech detected in {len(speech_segments)} stretches ({total:.0f} s): "
                     f"music drops a further {SPEECH_DUCK_DB:.0f} dB there, easing over "
                     f"{DUCK_RAMP_SECONDS} s.")
    elif audible:
        notes.append("No speech detected: music stays at one level.")
    notes.append(f"Finished mix normalised to {OUTPUT_LOUDNESS_LUFS:.0f} LUFS.")
    plan = MixPlan(
        purpose="Rule-based mix: original audio kept, music placed by measured level and lowered under speech.",
        original_audio_enabled=True,
        original_audio_gain_db=0.0,
        music_enabled=True,
        music_gain_db=gain,
        music_start_seconds=0.0,
        music_end_seconds=duration_seconds,
        music_fade_in_seconds=1.5,
        music_fade_out_seconds=2.0,
        ducking=ducking,
        ducking_ramp_seconds=DUCK_RAMP_SECONDS,
        output_loudness_lufs=OUTPUT_LOUDNESS_LUFS,
        notes=notes,
    )
    if voice_windows is not None:
        gain, why = voice_gain_for(voice_mean_db, voice_peak_db)
        plan = add_voice_layer(plan, list(voice_windows), voice_gain_db=gain, voice_note=why,
                               original_under_voice=original_under_voice,
                               original_available=audible)
    return plan
