from pathlib import Path

from .deterministic import default_plan
from .evaluate import EvaluationHook
from .ffmpeg import execute_mix, measure_levels
from .gemini import plan_with_gemini
from .models import MixPlan


def create_plan(context, *, use_llm: bool, model: str) -> MixPlan:
    if use_llm:
        return plan_with_gemini(context, model=model)
    original = measure_levels(context.video_path)
    music = measure_levels(context.music_path)
    return default_plan(
        context.duration_seconds,
        original_mean_db=original[0] if original else None,
        music_mean_db=music[0] if music else None,
        music_peak_db=music[1] if music else None,
    )


def write_plan(plan: MixPlan, output) -> None:
    Path(output).write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_plan(path) -> MixPlan:
    return MixPlan.model_validate_json(Path(path).read_text(encoding="utf-8"))


def mix(context, plan: MixPlan, output):
    result = execute_mix(context.video_path, context.music_path, plan, output)
    evaluation = EvaluationHook().evaluate(output_path=result, context=context, plan=plan)
    return result, evaluation
