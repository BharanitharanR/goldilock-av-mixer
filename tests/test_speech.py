import numpy as np

from video_audio_mixer.speech import SAMPLE_RATE, detect_speech_signal

RNG = np.random.default_rng(0)
SR = SAMPLE_RATE


def _t(seconds):
    return np.arange(int(seconds * SR)) / SR


def speech_like(seconds):
    """Voiced harmonics on a gliding ~150 Hz pitch, pulsing at 4 syllables/s."""
    t = _t(seconds)
    f0 = 150 + 25 * np.sin(2 * np.pi * 0.7 * t)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    voice = sum(np.sin(k * phase) / k for k in range(1, 12))
    syllables = np.clip(np.sin(2 * np.pi * 4 * t), 0, None) ** 1.5
    return 0.3 * voice * syllables / 3


def noise(seconds, level=0.02):
    return level * RNG.standard_normal(int(seconds * SR))


def test_speech_between_silences_is_found_with_its_timing():
    signal = np.concatenate([noise(2, 0.003), speech_like(3) + noise(3, 0.003), noise(2, 0.003)])
    segs = detect_speech_signal(signal)
    assert len(segs) == 1
    assert 1.6 <= segs[0].start_seconds <= 2.4
    assert 4.6 <= segs[0].end_seconds <= 5.4


def test_steady_noise_is_not_speech():
    assert detect_speech_signal(np.concatenate([noise(2, 0.001), noise(4, 0.2)])) == []


def test_steady_hum_is_not_speech():
    t = _t(5)
    hum = 0.2 * (np.sin(2 * np.pi * 120 * t) + 0.5 * np.sin(2 * np.pi * 240 * t))
    assert detect_speech_signal(np.concatenate([noise(1, 0.001), hum])) == []


def test_same_input_same_output():
    signal = np.concatenate([noise(1, 0.003), speech_like(2), noise(1, 0.003)])
    assert detect_speech_signal(signal) == detect_speech_signal(signal.copy())
