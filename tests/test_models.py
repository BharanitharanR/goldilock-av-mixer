import pytest

from video_audio_mixer.models import DuckingSegment, MixPlan


def test_mix_plan_defaults():
    plan = MixPlan(purpose="unit test")
    assert plan.original_audio_enabled
    assert plan.music_enabled


def test_ducking_rejects_reversed_interval():
    with pytest.raises(ValueError):
        DuckingSegment(start_seconds=9, end_seconds=4, music_gain_db=-24)
