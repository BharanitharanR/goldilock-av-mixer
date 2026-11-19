from video_audio_mixer.ffmpeg import build_filter_complex
from video_audio_mixer.models import MixPlan


def test_builds_two_source_mix():
    graph = build_filter_complex(MixPlan(purpose="test"))
    assert "[0:a]" in graph
    assert "[1:a]" in graph
    assert "amix=inputs=2" in graph
