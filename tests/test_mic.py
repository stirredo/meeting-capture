from meeting_capture import mic


def test_is_mic_active_returns_bool():
    result = mic.is_mic_active()
    assert isinstance(result, bool)


def test_mic_name_returns_str_or_none():
    name = mic.mic_name()
    assert name is None or isinstance(name, str)


def test_is_mic_active_handles_missing_pyobjc(monkeypatch):
    """If AVFoundation isn't importable (e.g. on a non-macOS test machine),
    is_mic_active() should return False rather than raising."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "AVFoundation":
            raise ImportError("simulated missing AVFoundation")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert mic.is_mic_active() is False
    assert mic.mic_name() is None
