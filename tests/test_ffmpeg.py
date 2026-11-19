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
    assert "[music]apad[mixed]" in graph


def test_original_only_plan_on_silent_video_is_rejected():
    import pytest
    with pytest.raises(ValueError, match="no audio track"):
        build_filter_complex(MixPlan(purpose="test", music_enabled=False), original_audio_available=False)


def test_ducking_ramps_instead_of_switching():
    from video_audio_mixer.models import DuckingSegment
    plan = MixPlan(purpose="t", music_gain_db=-10, ducking_ramp_seconds=0.25,
                   ducking=[DuckingSegment(start_seconds=2, end_seconds=4, music_gain_db=-18)])
    graph = build_filter_complex(plan)
    assert "enable=" not in graph
    assert "eval=frame" in graph and "-8.00*clip" in graph


def test_loudness_target_is_applied_last():
    graph = build_filter_complex(MixPlan(purpose="t", output_loudness_lufs=-16))
    assert graph.endswith("loudnorm=I=-16.0:TP=-1.5:LRA=11,aresample=48000[aout]")
