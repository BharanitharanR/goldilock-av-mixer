"""Rule-based speech detection: no model, same audio in -> same segments out.

A 30 ms frame counts as speech when all of these hold:
  1. LOUD ENOUGH   its level is clearly above the clip's noise floor;
  2. VOICED        it has a pitch: the autocorrelation shows a repeating period
                   between 80 and 400 Hz (vowels do; hiss, rumble and most
                   machine noise do not, or hold one fixed pitch);
  3. VOICE BAND    most of its energy sits between 80 and 4000 Hz (voice pitch
                   and formants), not in rumble below or hiss above;
  4. SYLLABIC      it sits inside a stretch whose loudness rises and falls 2-8
                   times a second (about 4 syllables/s), unlike steady noise.
Frames are then smoothed into segments: short bursts dropped, small gaps
merged, edges padded. Every threshold is a named constant below.

Known limits: singing or a TV/radio in the scene count as speech (fine for
ducking); whispering has no pitch and can be missed; very loud scenes lower
accuracy.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000
FRAME_SECONDS = 0.030
HOP_SECONDS = 0.010

ABOVE_FLOOR_DB = 8.0          # 1. frame level vs. the clip's 10th-percentile level
MIN_LEVEL_DB = -55.0          # 1. and never quieter than this (dBFS)
PITCH_MIN_HZ, PITCH_MAX_HZ = 80.0, 400.0
VOICED_MIN = 0.40             # 2. normalised autocorrelation peak in the pitch range
# The band includes the voice's own pitch (male ~100-150 Hz), not only the
# 300-3400 Hz telephone band, or male speech scores low on its own fundamental.
VOICE_BAND_HZ = (80.0, 4000.0)
VOICE_BAND_MIN = 0.60         # 3. share of 60-8000 Hz energy inside the voice band (white noise ~0.5)
RHYTHM_WINDOW_SECONDS = 1.0
RHYTHM_BAND_HZ = (2.0, 8.0)
RHYTHM_MIN = 0.30             # 4. share of envelope modulation energy at 2-8 Hz

MIN_SEGMENT_SECONDS = 0.30    # drop speech bursts shorter than this
MERGE_GAP_SECONDS = 0.40      # join segments closer than this
PAD_SECONDS = 0.15            # widen each segment on both sides


@dataclass(frozen=True)
class SpeechSegment:
    start_seconds: float
    end_seconds: float


def load_mono(path, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """First audio stream as mono float32 in [-1, 1]; empty when there is none."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg executable not found on PATH")
    completed = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-map", "0:a:0?", "-ac", "1",
         "-ar", str(sample_rate), "-f", "s16le", "-"],
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("ffmpeg could not decode audio:\n" + completed.stderr.decode(errors="replace"))
    return np.frombuffer(completed.stdout, dtype="<i2").astype(np.float32) / 32768.0


def _frames(signal: np.ndarray, frame: int, hop: int) -> np.ndarray:
    if len(signal) < frame:
        return np.zeros((0, frame), dtype=np.float32)
    count = 1 + (len(signal) - frame) // hop
    idx = np.arange(frame)[None, :] + hop * np.arange(count)[:, None]
    return signal[idx]


def frame_features(signal: np.ndarray, sample_rate: int = SAMPLE_RATE) -> dict[str, np.ndarray]:
    frame = int(FRAME_SECONDS * sample_rate)
    hop = int(HOP_SECONDS * sample_rate)
    frames = _frames(signal, frame, hop)
    if len(frames) == 0:
        empty = np.zeros(0)
        return {"level_db": empty, "voiced": empty, "voice_band": empty, "rhythm": empty}

    frames = frames - frames.mean(axis=1, keepdims=True)
    level_db = 10 * np.log10(np.mean(frames ** 2, axis=1) + 1e-12)

    windowed = frames * np.hanning(frame)[None, :]
    nfft = 2 * frame
    spectrum = np.fft.rfft(windowed, n=nfft, axis=1)
    power = np.abs(spectrum) ** 2
    freqs = np.fft.rfftfreq(nfft, 1 / sample_rate)

    in_range = (freqs >= 60) & (freqs <= 8000)
    in_band = (freqs >= VOICE_BAND_HZ[0]) & (freqs <= VOICE_BAND_HZ[1])
    voice_band = power[:, in_band].sum(axis=1) / (power[:, in_range].sum(axis=1) + 1e-12)

    # Autocorrelation via the power spectrum, normalised by lag-0 energy.
    autocorr = np.fft.irfft(power, n=nfft, axis=1)[:, :frame]
    autocorr = autocorr / (autocorr[:, :1] + 1e-12)
    lo = int(sample_rate / PITCH_MAX_HZ)
    hi = min(int(sample_rate / PITCH_MIN_HZ), frame - 1)
    voiced = autocorr[:, lo:hi].max(axis=1)

    # Syllable rhythm: how much of the loudness envelope's movement, over a
    # 1 s window around each frame, falls in the 2-8 Hz band.
    envelope = np.sqrt(np.mean(frames ** 2, axis=1))
    win = int(RHYTHM_WINDOW_SECONDS / HOP_SECONDS)
    rhythm = np.zeros(len(envelope))
    if len(envelope) >= win:
        env_frames = _frames(envelope.astype(np.float32), win, 1)
        env_frames = env_frames - env_frames.mean(axis=1, keepdims=True)
        env_power = np.abs(np.fft.rfft(env_frames * np.hanning(win)[None, :], axis=1)) ** 2
        env_freqs = np.fft.rfftfreq(win, HOP_SECONDS)
        band = (env_freqs >= RHYTHM_BAND_HZ[0]) & (env_freqs <= RHYTHM_BAND_HZ[1])
        moving = env_freqs >= 0.5
        share = env_power[:, band].sum(axis=1) / (env_power[:, moving].sum(axis=1) + 1e-12)
        half = win // 2
        rhythm[half:half + len(share)] = share
        rhythm[:half] = share[0]
        rhythm[half + len(share):] = share[-1]
    return {"level_db": level_db, "voiced": voiced, "voice_band": voice_band, "rhythm": rhythm}


def _segments_from_mask(mask: np.ndarray, duration: float) -> list[SpeechSegment]:
    segments, start = [], None
    for i, on in enumerate(np.append(mask, False)):
        t = i * HOP_SECONDS
        if on and start is None:
            start = t
        elif not on and start is not None:
            segments.append([start, t + FRAME_SECONDS])
            start = None
    merged: list[list[float]] = []
    for s, e in segments:
        if merged and s - merged[-1][1] < MERGE_GAP_SECONDS:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    out = []
    for s, e in merged:
        if e - s >= MIN_SEGMENT_SECONDS:
            out.append(SpeechSegment(round(max(0.0, s - PAD_SECONDS), 2),
                                     round(min(duration, e + PAD_SECONDS), 2)))
    # Padding can make neighbours touch again.
    final: list[SpeechSegment] = []
    for seg in out:
        if final and seg.start_seconds <= final[-1].end_seconds:
            final[-1] = SpeechSegment(final[-1].start_seconds, seg.end_seconds)
        else:
            final.append(seg)
    return final


def detect_speech_signal(signal: np.ndarray, sample_rate: int = SAMPLE_RATE) -> list[SpeechSegment]:
    f = frame_features(signal, sample_rate)
    if len(f["level_db"]) == 0:
        return []
    floor = float(np.percentile(f["level_db"], 10))
    loud = (f["level_db"] > floor + ABOVE_FLOOR_DB) & (f["level_db"] > MIN_LEVEL_DB)
    mask = loud & (f["voiced"] > VOICED_MIN) & (f["voice_band"] > VOICE_BAND_MIN) & (f["rhythm"] > RHYTHM_MIN)
    return _segments_from_mask(mask, len(signal) / sample_rate)


def detect_speech(path) -> list[SpeechSegment]:
    """Speech segments in a media file's first audio stream ([] when none)."""
    return detect_speech_signal(load_mono(path))
