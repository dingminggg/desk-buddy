import desk_buddy.notify as notify


def test_play_sound_beeps_when_no_file(monkeypatch):
    calls = {"beep": 0, "file": []}
    monkeypatch.setattr(notify, "_beep", lambda: calls.__setitem__("beep", calls["beep"] + 1))
    monkeypatch.setattr(notify, "_play_file", lambda p: calls["file"].append(p))
    notify.play_sound("")  # no custom file -> default beep
    assert calls["beep"] == 1
    assert calls["file"] == []


def test_play_sound_plays_existing_file(monkeypatch, tmp_path):
    snd = tmp_path / "guagua.mp3"
    snd.write_bytes(b"fake")
    calls = {"beep": 0, "file": []}
    monkeypatch.setattr(notify, "_beep", lambda: calls.__setitem__("beep", calls["beep"] + 1))
    monkeypatch.setattr(notify, "_play_file", lambda p: calls["file"].append(p))
    notify.play_sound(str(snd))
    assert calls["file"] == [str(snd)]
    assert calls["beep"] == 0


def test_play_sound_beeps_when_file_missing(monkeypatch):
    calls = {"beep": 0, "file": []}
    monkeypatch.setattr(notify, "_beep", lambda: calls.__setitem__("beep", calls["beep"] + 1))
    monkeypatch.setattr(notify, "_play_file", lambda p: calls["file"].append(p))
    notify.play_sound("C:/does/not/exist.mp3")  # bad path -> fall back to beep
    assert calls["beep"] == 1
    assert calls["file"] == []


def test_play_sound_swallows_errors(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no audio")

    monkeypatch.setattr(notify, "_beep", boom)
    notify.play_sound("")  # must NOT raise
