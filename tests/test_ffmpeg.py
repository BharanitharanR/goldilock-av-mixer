from video_audio_mixer.ffmpeg import build_filter_complex
from video_audio_mixer.models import MixPlan


def test_builds_two_source_mix():
    graph = build_filter_complex(MixPlan(purpose="test"))
    assert "[0:a]" in graph
    assert "[1:a]" in graph
    assert "amix=inputs=2" in graph


def test_amix_keeps_absolute_levels():
    graph = build_filter_complex(MixPlan(purpose="test"))
    assert "normalize=0" in graph


def test_video_without_audio_uses_music_only():
    graph = build_filter_complex(MixPlan(purpose="test"), original_audio_available=False)
    assert "[0:a]" not in graph
    assert "[music]apad[aout]" in graph


def test_original_only_plan_on_silent_video_is_rejected():
    import pytest
    with pytest.raises(ValueError, match="no audio track"):
        build_filter_complex(MixPlan(purpose="test", music_enabled=False), original_audio_available=False)
