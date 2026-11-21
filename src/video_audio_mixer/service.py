import json
from pathlib import Path

from .deterministic import add_voice_layer, default_plan
from .evaluate import EvaluationHook
from .ffmpeg import execute_mix, measure_levels
from .gemini import plan_with_gemini
from .models import MixPlan
from .voice import (measure_voice_level, voice_gain_for, windows_from_audio, windows_from_timeline)
from .speech import detect_speech


def _voice_inputs(context) -> dict:
    """Windows and level of the voiceover, from the timeline when there is one."""
    duration = context.duration_seconds
    if context.voice_timeline_path:
        windows = windows_from_timeline(context.voice_timeline_path, duration)
    else:
        windows = windows_from_audio(context.voiceover_path, duration)
    level = measure_voice_level(context.voiceover_path)
    return {"voice_windows": windows,
            "voice_mean_db": level[0] if level else None,
            "voice_peak_db": level[1] if level else None}


def create_plan(context, *, use_llm: bool, model: str, original_under_voice="keep") -> MixPlan:
    voice = _voice_inputs(context) if context.voiceover_path else {}
    if use_llm:
        # The Gemini planner does not know about the voiceover. Whatever it
        # returns, the voice layer is added by the same rules as the
        # rule-based path, and any voice fields it invented are cleared.
        plan = plan_with_gemini(context, model=model)
        plan = plan.model_copy(update={"voice_enabled": False, "voice_windows": []})
        if voice:
            gain, why = voice_gain_for(voice["voice_mean_db"], voice["voice_peak_db"])
            plan = add_voice_layer(plan, voice["voice_windows"], voice_gain_db=gain, voice_note=why,
                                   original_under_voice=original_under_voice)
        return plan
    original = measure_levels(context.video_path)
    music = measure_levels(context.music_path)
    return default_plan(
        context.duration_seconds,
        original_mean_db=original[0] if original else None,
        music_mean_db=music[0] if music else None,
        music_peak_db=music[1] if music else None,
        speech_segments=detect_speech(context.video_path) if original else [],
        original_under_voice=original_under_voice,
        **voice,
    )


def write_plan(plan: MixPlan, output) -> None:
    Path(output).write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_plan(path) -> MixPlan:
    return MixPlan.model_validate_json(Path(path).read_text(encoding="utf-8"))


def mix(context, plan: MixPlan, output):
    result = execute_mix(context.video_path, context.music_path, plan, output,
                         voiceover=context.voiceover_path)
    evaluation = EvaluationHook().evaluate(output_path=result, context=context, plan=plan)
    return result, evaluation


def write_speech(video, output) -> None:
    """[{start_seconds, end_seconds}] for the video's own audio ([] when none)."""
    segments = [{"start_seconds": round(s.start_seconds, 3), "end_seconds": round(s.end_seconds, 3)}
                for s in detect_speech(video)]
    Path(output).write_text(json.dumps(segments, indent=2) + "\n", encoding="utf-8")
