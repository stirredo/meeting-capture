from meeting_capture import mic


def test_is_mic_active_returns_bool():
    assert isinstance(mic.is_mic_active(), bool)


def test_mic_name_returns_str_or_none():
    name = mic.mic_name()
    assert name is None or isinstance(name, str)


def test_active_mic_name_returns_str_or_none():
    name = mic.active_mic_name()
    assert name is None or isinstance(name, str)


def test_active_mic_name_is_none_when_no_mic_active():
    if not mic.is_mic_active():
        assert mic.active_mic_name() is None


def test_all_device_ids_returns_list():
    ids = mic._all_device_ids()
    assert isinstance(ids, list)
    assert all(isinstance(i, int) for i in ids)


def test_handles_missing_coreaudio(monkeypatch):
    """If CoreAudio framework can't be loaded (e.g. non-macOS), is_mic_active returns False."""
    monkeypatch.setattr(mic, "_CA", None)
    assert mic.is_mic_active() is False
    assert mic.mic_name() is None
    assert mic.active_mic_name() is None
    assert mic._all_device_ids() == []
