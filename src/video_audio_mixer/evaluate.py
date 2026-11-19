from __future__ import annotations

from pathlib import Path

from .models import EvaluationResult


class EvaluationHook:
    """Post-render evaluation extension point.

    No automatic planner feedback loop is implemented in this version.
    """

    def evaluate(self, *, output_path: str | Path, context, plan) -> EvaluationResult:
        path = Path(output_path)
        if not path.is_file() or path.stat().st_size == 0:
            return EvaluationResult(
                status="failed",
                acceptable=False,
                findings=["Rendered output is missing or empty."],
            )
        return EvaluationResult(
            status="not_configured",
            acceptable=None,
            findings=["Basic artifact existence check passed; perceptual evaluation is not configured."],
            metrics={"output_bytes": path.stat().st_size},
        )
