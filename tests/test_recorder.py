import numpy as np

from meeting_capture import recorder


def test_rms_int16_silence():
    silent = np.zeros(1000, dtype=np.int16)
    assert recorder._rms_int16(silent) == 0.0


def test_rms_int16_signal():
    val = int(0.2 * 32768)
    sig = np.full(1000, val, dtype=np.int16)
    assert abs(recorder._rms_int16(sig) - 0.2) < 1e-3


def test_trim_trailing_silence_keeps_signal():
    sample_rate = recorder.SAMPLE_RATE
    block = int(sample_rate * recorder.CHUNK_DURATION)
    speech_val = int(0.3 * 32768)
    speech = np.full(block * 4, speech_val, dtype=np.int16)
    silence = np.zeros(block * 6, dtype=np.int16)
    audio = np.concatenate([speech, silence])
    trimmed = recorder._trim_trailing_silence(audio, sample_rate)
    assert len(trimmed) <= len(speech) + block
    assert len(trimmed) >= len(speech) - block


def test_trim_trailing_silence_all_silent():
    sample_rate = recorder.SAMPLE_RATE
    block = int(sample_rate * recorder.CHUNK_DURATION)
    audio = np.zeros(block * 5, dtype=np.int16)
    trimmed = recorder._trim_trailing_silence(audio, sample_rate)
    assert len(trimmed) <= block


def test_find_audiotee_via_env(tmp_path, monkeypatch):
    fake = tmp_path / "audiotee"
    fake.write_text("")
    monkeypatch.setenv(recorder.AUDIOTEE_ENV_VAR, str(fake))
    assert recorder.find_audiotee() == fake


def test_find_audiotee_returns_none_when_missing(monkeypatch):
    monkeypatch.delenv(recorder.AUDIOTEE_ENV_VAR, raising=False)
    monkeypatch.setattr(recorder.shutil, "which", lambda _name: None)
    monkeypatch.setattr(recorder.Path, "is_file", lambda self: False)
    assert recorder.find_audiotee() is None


def test_find_sysaudio_via_env(tmp_path, monkeypatch):
    fake = tmp_path / "sysaudio"
    fake.write_text("")
    monkeypatch.setenv(recorder.SYSAUDIO_ENV_VAR, str(fake))
    assert recorder.find_sysaudio() == fake


def test_find_sysaudio_returns_none_when_missing(monkeypatch):
    monkeypatch.delenv(recorder.SYSAUDIO_ENV_VAR, raising=False)
    monkeypatch.setattr(recorder.shutil, "which", lambda _name: None)
    monkeypatch.setattr(recorder.Path, "is_file", lambda self: False)
    assert recorder.find_sysaudio() is None


def test_find_capture_binary_prefers_sysaudio(tmp_path, monkeypatch):
    fake_sysaudio = tmp_path / "sysaudio"
    fake_audiotee = tmp_path / "audiotee"
    fake_sysaudio.write_text("")
    fake_audiotee.write_text("")
    monkeypatch.setenv(recorder.SYSAUDIO_ENV_VAR, str(fake_sysaudio))
    monkeypatch.setenv(recorder.AUDIOTEE_ENV_VAR, str(fake_audiotee))
    assert recorder.find_capture_binary() == fake_sysaudio


def test_find_capture_binary_falls_back_to_audiotee(tmp_path, monkeypatch):
    fake_audiotee = tmp_path / "audiotee"
    fake_audiotee.write_text("")
    monkeypatch.delenv(recorder.SYSAUDIO_ENV_VAR, raising=False)
    monkeypatch.setenv(recorder.AUDIOTEE_ENV_VAR, str(fake_audiotee))
    monkeypatch.setattr(recorder.shutil, "which", lambda name: None)
    # Also need to patch the bin/ search; easiest is monkeypatching find_sysaudio to None
    monkeypatch.setattr(recorder, "find_sysaudio", lambda: None)
    assert recorder.find_capture_binary() == fake_audiotee


def test_flush_min_seconds_constant_exists():
    assert recorder.FLUSH_MIN_SECONDS > 0
    assert recorder.FLUSH_MIN_SECONDS < recorder.MIN_CHUNK_SECONDS
