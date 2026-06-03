"""Windows toast + sound. All failures are swallowed so the UI never crashes."""


def _plyer_notify(title: str, message: str, app_name: str, timeout: int) -> None:
    from plyer import notification
    notification.notify(title=title, message=message,
                        app_name=app_name, timeout=timeout)


def _beep() -> None:
    import winsound
    winsound.MessageBeep()


def toast(title: str, message: str) -> None:
    try:
        _plyer_notify(title, message, "desk-buddy", 5)
    except Exception:
        pass


def play_sound() -> None:
    try:
        _beep()
    except Exception:
        pass
