from __future__ import annotations

from .models import MixPlan

# Average (mean) level the music should land at, in dBFS.
MUSIC_ALONE_TARGET_DB = -18.0      # when the video has no meaningful sound of its own
MUSIC_UNDER_ORIGINAL_DB = 10.0     # how far below the video's own sound the music sits
NEAR_SILENT_ORIGINAL_DB = -45.0    # below this mean, the video's audio is treated as silent
PEAK_CEILING_DB = -1.0             # never push the music's peaks above this
FALLBACK_MUSIC_GAIN_DB = -16.0     # used only when levels could not be measured


def music_gain_for(original_mean_db: float | None, music_mean_db: float | None,
                   music_peak_db: float | None) -> tuple[float, str]:
    """Music gain (dB) that places the music by measured level, not by a fixed
    offset. A fixed -16 dB under a near-silent video (screen recordings, muted
    clips, exported edits) left the whole soundtrack around -36 dB."""
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
                 music_mean_db: float | None = None, music_peak_db: float | None = None) -> MixPlan:
    gain, why = music_gain_for(original_mean_db, music_mean_db, music_peak_db)
    return MixPlan(
        purpose="Conservative mix retaining original audio and placing music underneath.",
        original_audio_enabled=True,
        original_audio_gain_db=0.0,
        music_enabled=True,
        music_gain_db=gain,
        music_start_seconds=0.0,
        music_end_seconds=duration_seconds,
        music_fade_in_seconds=1.5,
        music_fade_out_seconds=2.0,
        notes=["Deterministic fallback: no speech-aware ducking was inferred.", why],
    )
