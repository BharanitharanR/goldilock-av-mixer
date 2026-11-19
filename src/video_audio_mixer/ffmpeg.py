from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .models import MixPlan, OutputDurationPolicy


def require_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("ffmpeg executable not found on PATH")
    return executable


def has_audio_stream(path) -> bool:
    """True when the media file carries at least one audio stream.

    Screen recordings, exported edits and some phone clips have no audio
    track at all; mapping [0:a] on those makes FFmpeg fail outright.
    """
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe executable not found on PATH")
    completed = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("ffprobe failed:\n" + completed.stderr)
    return bool(completed.stdout.strip())


def measure_levels(path) -> tuple[float, float] | None:
    """(mean, peak) level in dBFS of the first audio stream, or None when the
    file has no audio. Uses FFmpeg's volumedetect."""
    if not has_audio_stream(path):
        return None
    completed = subprocess.run(
        [require_ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    mean = peak = None
    for line in completed.stderr.splitlines():
        if "mean_volume:" in line:
            mean = float(line.split("mean_volume:")[1].split()[0])
        elif "max_volume:" in line:
            peak = float(line.split("max_volume:")[1].split()[0])
    if mean is None or peak is None:
        raise RuntimeError("Could not measure audio level of " + str(path))
    return mean, peak


def build_filter_complex(plan: MixPlan, *, original_audio_available: bool = True) -> str:
    use_original = plan.original_audio_enabled and original_audio_available
    inputs = []

    if use_original:
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

    if use_original and plan.music_enabled:
        # normalize=0: amix otherwise scales every input by 1/inputs, which
        # silently lowers the original audio (speech) by about 6 dB even when
        # the music is muted. The plan's gains are meant to be absolute.
        inputs.append(
            "[original][music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
        )
    elif use_original:
        inputs.append("[original]anull[aout]")
    elif plan.music_enabled:
        # Music alone carries the soundtrack. For the "video" policy pad it
        # with silence so a short track never cuts the picture; execute_mix
        # then stops at the end of the video with -shortest.
        if plan.output_duration_policy == OutputDurationPolicy.VIDEO:
            inputs.append("[music]apad[aout]")
        else:
            inputs.append("[music]anull[aout]")
    elif plan.original_audio_enabled and not original_audio_available:
        raise ValueError("MixPlan uses only the original audio, but the video has no audio track")
    else:
        raise ValueError("MixPlan disables both audio sources")

    return ";".join(inputs)


def execute_mix(video, music, plan: MixPlan, output) -> Path:
    executable = require_ffmpeg()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    original_audio_available = has_audio_stream(video)
    music_only = plan.music_enabled and not (plan.original_audio_enabled and original_audio_available)

    command = [
        executable, "-y",
        "-i", str(video),
        "-i", str(music),
        "-filter_complex", build_filter_complex(plan, original_audio_available=original_audio_available),
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-movflags", "+faststart",
    ]
    if plan.output_duration_policy == OutputDurationPolicy.SHORTEST or (
        music_only and plan.output_duration_policy == OutputDurationPolicy.VIDEO
    ):
        command.append("-shortest")
    command.append(str(output_path))

    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError("FFmpeg failed:\n" + completed.stderr)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg reported success but output is missing or empty")
    return output_path
