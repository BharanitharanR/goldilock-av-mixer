from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from google import genai

from .models import MixPlan
from .prompt import SYSTEM_PROMPT, build_prompt

DEFAULT_MODEL = "gemini-3.6-flash"

# Tried after the requested model when Gemini answers with a quota, rate-limit
# or server error. Free-tier models with quota (AI Studio, 2026-11-20); the
# Flash-Lite models have the most headroom (15 RPM / 500 RPD).
DEFAULT_FALLBACK_MODELS = (
    "gemini-3.8-flash",
    "gemini-4-hydrogen",
    "gemini-2.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)

_RETRYABLE_MARKERS = ("INTERNAL", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED",
                      "OVERLOADED", "QUOTA", "RATE LIMIT", "TOO MANY REQUESTS")
_RETRYABLE_CODES = {429, 500, 502, 503, 504}


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ValueError)):
        return False
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int) and code in _RETRYABLE_CODES:
        return True
    return any(marker in str(exc).upper() for marker in _RETRYABLE_MARKERS)


def model_chain(primary: str) -> list[str]:
    """Requested model first, then GOLDILOCK_MIX_MODELS (comma-separated) or
    the defaults; at most GOLDILOCK_MAX_MODEL_ATTEMPTS (default 3) models,
    since every try is a paid call. GOLDILOCK_MODEL_FALLBACK=0 disables it."""
    if os.environ.get("GOLDILOCK_MODEL_FALLBACK", "1").strip() == "0":
        return [primary]
    configured = os.environ.get("GOLDILOCK_MIX_MODELS")
    rest = [m.strip() for m in configured.split(",")] if configured else list(DEFAULT_FALLBACK_MODELS)
    chain: list[str] = []
    for name in [primary, *rest]:
        if name and name not in chain:
            chain.append(name)
    return chain[:max(1, int(os.environ.get("GOLDILOCK_MAX_MODEL_ATTEMPTS", "3")))]


def _plan_once(client, context, model, poll_interval_seconds, timeout_seconds) -> str:
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
            # Keep Gemini's own error (e.g. INTERNAL, RESOURCE_EXHAUSTED) so the
            # fallback can tell a busy model from a bad request.
            raise RuntimeError(f"Gemini interaction {status}: {getattr(current, 'errors', None)}")
        if time.monotonic() - started > timeout_seconds:
            raise TimeoutError("Gemini mixing-plan inference timed out")
        time.sleep(poll_interval_seconds)

    output_text = getattr(current, "output_text", None)
    if not output_text:
        raise RuntimeError("Gemini returned no output_text")
    return output_text


def plan_with_gemini(context, *, model: str = DEFAULT_MODEL, poll_interval_seconds: float = 3.0,
                     timeout_seconds: float = 900.0, raw_output_path: str = "mixing-response.raw.json") -> MixPlan:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)
    chain = model_chain(model)
    failures = []
    for index, name in enumerate(chain):
        try:
            output_text = _plan_once(client, context, name, poll_interval_seconds, timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - classified below
            if not is_retryable(exc):
                raise
            failures.append(f"{name}: {' '.join(str(exc).split())[:240]}")
            if index + 1 < len(chain):
                print(f"Gemini model {name} unavailable; trying {chain[index + 1]}", file=sys.stderr, flush=True)
            continue
        print(f"Gemini model used: {name}", file=sys.stderr, flush=True)
        Path(raw_output_path).write_text(output_text, encoding="utf-8")
        return MixPlan.model_validate(json.loads(output_text))
    raise RuntimeError("Every Gemini model in the fallback chain failed: " + " | ".join(failures))
