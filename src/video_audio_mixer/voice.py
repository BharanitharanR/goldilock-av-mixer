"""Voiceover helpers: speaking windows from the timeline, and its level.

The timeline follows the narrator contract: {"lines": [{"start_seconds",
"end_seconds", ...}]}. Only those two fields are read here.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .models import VoiceWindow
from .speech import SAMPLE_RATE, detect_speech, load_mono

VOICE_PAD_SECONDS = 0.15     # widen each window on both sides
VOICE_MERGE_GAP_SECONDS = 0.40   # join windows closer than this
VOICE_TARGET_MEAN_DB = -17.0     # mean level of the voice's non-silent parts, before loudnorm
VOICE_PEAK_CEILING_DB = -1.0
_ACTIVE_FLOOR_DB = -50.0         # frames quieter than this are not "speech" for the mean
_FRAME = int(0.05 * SAMPLE_RATE)


def merge_windows(intervals, duration_seconds: float | None = None, *,
                  pad: float = VOICE_PAD_SECONDS, gap: float = VOICE_MERGE_GAP_SECONDS) -> list[VoiceWindow]:
    padded = []
    for start, end in intervals:
        s, e = max(0.0, start - pad), end + pad
        if duration_seconds is not None:
            e = min(e, duration_seconds)
        if e > s:
            padded.append([s, e])
    padded.sort()
    merged: list[list[float]] = []
    for s, e in padded:
        if merged and s - merged[-1][1] < gap:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [VoiceWindow(start_seconds=round(s, 3), end_seconds=round(e, 3)) for s, e in merged]


def windows_from_timeline(path, duration_seconds: float | None = None) -> list[VoiceWindow]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list):
        raise ValueError(f"{path} has no 'lines' list")
    spans = []
    for line in lines:
        start, end = line.get("start_seconds"), line.get("end_seconds")
        if start is None or end is None:
            raise ValueError(f"{path}: every line needs start_seconds and end_seconds")
        if end > start:
            spans.append((float(start), float(end)))
    return merge_windows(spans, duration_seconds)


def windows_from_audio(path, duration_seconds: float | None = None) -> list[VoiceWindow]:
    """Fallback when no timeline is given: find the speech in the voiceover itself."""
    return merge_windows([(s.start_seconds, s.end_seconds) for s in detect_speech(path)], duration_seconds)


def measure_voice_level(path) -> tuple[float, float] | None:
    """(mean, peak) dBFS over the voiceover's non-silent parts. The mean is a
    power average over frames above -50 dBFS, so the long silences around a
    voiceover do not pull it down. None when empty or entirely silent."""
    signal = load_mono(path)
    if len(signal) < _FRAME:
        return None
    n = len(signal) // _FRAME
    frames = signal[: n * _FRAME].reshape(n, _FRAME).astype(np.float64)
    power = (frames ** 2).mean(axis=1)
    level = 10 * np.log10(np.maximum(power, 1e-12))
    active = level > _ACTIVE_FLOOR_DB
    if not active.any():
        return None
    mean = float(10 * np.log10(power[active].mean()))
    peak = float(20 * np.log10(max(float(np.abs(signal).max()), 1e-6)))
    return mean, peak


def voice_gain_for(mean_db: float | None, peak_db: float | None) -> tuple[float, str]:
    if mean_db is None:
        return 0.0, "Voiceover level unknown: gain left at 0 dB."
    gain = VOICE_TARGET_MEAN_DB - mean_db
    why = (f"Voiceover speech averages {mean_db:.1f} dB: gain {gain:+.1f} dB puts it at about "
           f"{VOICE_TARGET_MEAN_DB:.0f} dB mean, above the music.")
    if peak_db is not None and peak_db + gain > VOICE_PEAK_CEILING_DB:
        gain = VOICE_PEAK_CEILING_DB - peak_db
        why += f" Reduced to {gain:+.1f} dB to keep peaks under {VOICE_PEAK_CEILING_DB:.0f} dBFS."
    return round(max(-40.0, min(24.0, gain)), 1), why
