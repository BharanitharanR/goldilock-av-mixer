from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .models import MixPlan


def require_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("ffmpeg executable not found on PATH")
    return executable


def build_filter_complex(plan: MixPlan) -> str:
    inputs = []

    if plan.original_audio_enabled:
        inputs.append(f"[0:a]volume={plan.original_audio_gain_db}dB[original]")

    if plan.music_enabled:
        music_filters = [f"volume={plan.music_gain_db}dB"]
        if plan.music_start_seconds > 0:
            music_filters.insert(0, f"adelay={plan.music_start_seconds * 1000:.0f}:all=1")
        if plan.music_fade_in_seconds > 0:
            music_filters.append(
                f"afade=t=in:st={plan.music_start_seconds}:d={plan.music_fade_in_seconds}"
            )
        if plan.music_end_seconds is not None and plan.music_fade_out_seconds > 0:
            fade_start = max(plan.music_start_seconds,
                             plan.music_end_seconds - plan.music_fade_out_seconds)
            music_filters.append(
                f"afade=t=out:st={fade_start}:d={plan.music_fade_out_seconds}"
            )
        for segment in plan.ducking:
            relative_gain = segment.music_gain_db - plan.music_gain_db
            music_filters.append(
                f"volume={relative_gain}dB:enable='between(t,{segment.start_seconds},{segment.end_seconds})'"
            )
        inputs.append("[1:a]" + ",".join(music_filters) + "[music]")

    if plan.original_audio_enabled and plan.music_enabled:
        inputs.append("[original][music]amix=inputs=2:duration=first:dropout_transition=2[aout]")
    elif plan.original_audio_enabled:
        inputs.append("[original]anull[aout]")
    elif plan.music_enabled:
        inputs.append("[music]anull[aout]")
    else:
        raise ValueError("MixPlan disables both audio sources")

    return ";".join(inputs)


def execute_mix(video, music, plan: MixPlan, output) -> Path:
    executable = require_ffmpeg()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        executable, "-y",
        "-i", str(video),
        "-i", str(music),
        "-filter_complex", build_filter_complex(plan),
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-movflags", "+faststart",
    ]
    if plan.output_duration_policy.value == "shortest":
        command.append("-shortest")
    command.append(str(output_path))

    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError("FFmpeg failed:\n" + completed.stderr)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg reported success but output is missing or empty")
    return output_path
