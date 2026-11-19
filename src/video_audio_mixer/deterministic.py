from .models import MixPlan


def default_plan(duration_seconds: float | None) -> MixPlan:
    return MixPlan(
        purpose="Conservative mix retaining original audio and placing music underneath.",
        original_audio_enabled=True,
        original_audio_gain_db=0.0,
        music_enabled=True,
        music_gain_db=-16.0,
        music_start_seconds=0.0,
        music_end_seconds=duration_seconds,
        music_fade_in_seconds=1.5,
        music_fade_out_seconds=2.0,
        notes=["Deterministic fallback: no speech-aware ducking was inferred."],
    )
