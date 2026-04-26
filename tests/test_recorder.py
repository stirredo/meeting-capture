import numpy as np

from meeting_capture import recorder


def test_rms_silence():
    silent = np.zeros(1000, dtype=np.float32)
    assert recorder._rms(silent) == 0.0


def test_rms_signal():
    sig = np.full(1000, 0.1, dtype=np.float32)
    assert abs(recorder._rms(sig) - 0.1) < 1e-6


def test_trim_trailing_silence_keeps_signal():
    sample_rate = recorder.SAMPLE_RATE
    block = int(sample_rate * recorder.BLOCK_SECONDS)
    speech = np.full(block * 4, 0.2, dtype=np.float32)
    silence = np.zeros(block * 6, dtype=np.float32)
    audio = np.concatenate([speech, silence])
    trimmed = recorder._trim_trailing_silence(audio, sample_rate)
    assert len(trimmed) <= len(speech) + block
    assert len(trimmed) >= len(speech) - block


def test_trim_trailing_silence_all_silent():
    sample_rate = recorder.SAMPLE_RATE
    block = int(sample_rate * recorder.BLOCK_SECONDS)
    audio = np.zeros(block * 5, dtype=np.float32)
    trimmed = recorder._trim_trailing_silence(audio, sample_rate)
    assert len(trimmed) <= block
