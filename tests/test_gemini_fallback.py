import json

import pytest

from video_audio_mixer import gemini


class _Done:
    id = "i"
    status = "completed"
    output_text = json.dumps({"purpose": "test"})


class _Failed:
    id = "i"
    status = "failed"
    errors = "[Error(code='INTERNAL', message='There was a problem')]"


def _client(failing_models, calls):
    class Interactions:
        def create(self, model, **kwargs):
            calls.append(model)
            self.result = _Failed() if model in failing_models else _Done()
            return self.result

        def get(self, _id):
            return self.result

    class Client:
        def __init__(self, api_key):
            self.interactions = Interactions()

    return Client


def test_planner_moves_to_next_model_on_internal_error(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.delenv("GOLDILOCK_MIX_MODELS", raising=False)
    monkeypatch.setattr(gemini.genai, "Client", _client({"gemini-3.6-flash"}, calls))
    monkeypatch.setattr(gemini, "build_prompt", lambda context: "prompt")
    plan = gemini.plan_with_gemini(None, raw_output_path=str(tmp_path / "raw.json"))
    assert plan.purpose == "test"
    assert calls == ["gemini-3.6-flash", "gemini-3.8-flash"]


def test_planner_stops_after_attempt_cap(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("GOLDILOCK_MAX_MODEL_ATTEMPTS", "2")
    monkeypatch.setattr(gemini.genai, "Client", _client({"gemini-3.6-flash", "gemini-3.8-flash"}, calls))
    monkeypatch.setattr(gemini, "build_prompt", lambda context: "prompt")
    with pytest.raises(RuntimeError, match="fallback chain failed"):
        gemini.plan_with_gemini(None, raw_output_path=str(tmp_path / "raw.json"))
    assert len(calls) == 2
