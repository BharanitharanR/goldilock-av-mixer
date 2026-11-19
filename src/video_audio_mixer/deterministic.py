from __future__ import annotations

from .models import DuckingSegment, MixPlan

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


def default_plan(duration_seconds: float | None, *, original_mean_db: float | None = None,
                 music_mean_db: float | None = None, music_peak_db: float | None = None,
                 speech_segments=None) -> MixPlan:
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
    return MixPlan(
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
