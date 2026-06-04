from pathlib import Path

import desk_buddy.notify as notify


def _spy(monkeypatch):
    calls = {"beep": 0, "file": []}
    monkeypatch.setattr(notify, "_beep",
                        lambda: calls.__setitem__("beep", calls["beep"] + 1))
    monkeypatch.setattr(notify, "_play_file", lambda p: calls["file"].append(p))
    return calls


def test_explicit_file_is_played(monkeypatch, tmp_path):
    snd = tmp_path / "custom.wav"
    snd.write_bytes(b"fake")
    calls = _spy(monkeypatch)
    notify.play_sound(str(snd))
    assert calls["file"] == [str(snd)]
    assert calls["beep"] == 0


def test_empty_falls_back_to_bundled_default(monkeypatch, tmp_path):
    default = tmp_path / "guagua.mp3"
    default.write_bytes(b"fake")
    monkeypatch.setattr(notify, "_DEFAULT_SOUND", default)
    calls = _spy(monkeypatch)
    notify.play_sound("")  # no custom file -> bundled default
    assert calls["file"] == [str(default)]
    assert calls["beep"] == 0


def test_bad_path_falls_back_to_bundled_default(monkeypatch, tmp_path):
    default = tmp_path / "guagua.mp3"
    default.write_bytes(b"fake")
    monkeypatch.setattr(notify, "_DEFAULT_SOUND", default)
    calls = _spy(monkeypatch)
    notify.play_sound("C:/does/not/exist.mp3")
    assert calls["file"] == [str(default)]
    assert calls["beep"] == 0


def test_beeps_when_no_file_and_no_default(monkeypatch):
    monkeypatch.setattr(notify, "_DEFAULT_SOUND", Path("C:/nope/missing.mp3"))
    calls = _spy(monkeypatch)
    notify.play_sound("")
    assert calls["beep"] == 1
    assert calls["file"] == []


def test_play_sound_swallows_errors(monkeypatch):
    monkeypatch.setattr(notify, "_DEFAULT_SOUND", Path("C:/nope/missing.mp3"))

    def boom(*a, **k):
        raise RuntimeError("no audio")

    monkeypatch.setattr(notify, "_beep", boom)
    notify.play_sound("")  # must NOT raise


def test_bundled_default_exists_in_repo():
    # 真正随包发布的默认音应当存在，保证开箱即有咕咕声
    assert notify._DEFAULT_SOUND.is_file()
