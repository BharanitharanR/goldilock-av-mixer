from __future__ import annotations

import json
import os
import time
from pathlib import Path

from google import genai

from .models import MixPlan
from .prompt import SYSTEM_PROMPT, build_prompt

DEFAULT_MODEL = "gemini-3.6-flash"


def plan_with_gemini(context, *, model: str = DEFAULT_MODEL, poll_interval_seconds: float = 3.0,
                     timeout_seconds: float = 900.0, raw_output_path: str = "mixing-response.raw.json") -> MixPlan:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)
    interaction = client.interactions.create(
        model=model,
        input=[{"type": "text", "text": build_prompt(context)}],
        system_instruction=SYSTEM_PROMPT,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": MixPlan.model_json_schema(),
        },
        background=True,
        store=True,
    )

    started = time.monotonic()
    while True:
        current = client.interactions.get(interaction.id)
        status = getattr(current, "status", None)
        if status == "completed":
            break
        if status in {"failed", "cancelled"}:
            raise RuntimeError(f"Gemini interaction {status}")
        if time.monotonic() - started > timeout_seconds:
            raise TimeoutError("Gemini mixing-plan inference timed out")
        time.sleep(poll_interval_seconds)

    output_text = getattr(current, "output_text", None)
    if not output_text:
        raise RuntimeError("Gemini returned no output_text")
    Path(raw_output_path).write_text(output_text, encoding="utf-8")
    return MixPlan.model_validate(json.loads(output_text))
