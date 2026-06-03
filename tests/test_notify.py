import desk_buddy.notify as notify


def test_toast_calls_backend(monkeypatch):
    captured = {}

    def fake_notify(title, message, app_name, timeout):
        captured["title"] = title
        captured["message"] = message

    monkeypatch.setattr(notify, "_plyer_notify", fake_notify)
    notify.toast("标题", "内容")
    assert captured == {"title": "标题", "message": "内容"}


def test_toast_swallows_backend_errors(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no notifier on this box")

    monkeypatch.setattr(notify, "_plyer_notify", boom)
    notify.toast("t", "m")  # must NOT raise


def test_play_sound_swallows_errors(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no audio")

    monkeypatch.setattr(notify, "_beep", boom)
    notify.play_sound()  # must NOT raise
