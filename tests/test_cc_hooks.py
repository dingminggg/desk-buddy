# tests/test_cc_hooks.py
import pytest

from desk_buddy import cc_signals
from desk_buddy.hooks import clear as clear_hook
from desk_buddy.hooks import notify as notify_hook


@pytest.fixture
def pending(tmp_path, monkeypatch):
    d = tmp_path / "pending"
    monkeypatch.setattr(cc_signals, "pending_dir", lambda: d)
    return d


def test_notify_writes_on_permission_message(pending):
    notify_hook.handle({
        "session_id": "s1",
        "message": "Claude needs your permission to use Bash",
    })
    assert cc_signals.read_pending() == {"s1": "Claude Code"}


def test_notify_forwards_cwd_as_project_name(pending):
    notify_hook.handle({
        "session_id": "s1",
        "message": "needs your permission to use Bash",
        "cwd": "/home/me/projects/desk-buddy",
    })
    assert cc_signals.read_pending() == {"s1": "desk-buddy"}


def test_notify_ignores_non_permission_message(pending):
    notify_hook.handle({
        "session_id": "s1",
        "message": "Claude is waiting for your input",
    })
    assert cc_signals.read_pending() == {}


def test_notify_ignores_missing_session(pending):
    notify_hook.handle({"message": "needs your permission"})
    assert cc_signals.read_pending() == {}


def test_clear_removes_session(pending):
    cc_signals.write_pending("s1", "needs permission")
    clear_hook.handle({"session_id": "s1"})
    assert cc_signals.read_pending() == {}


def test_clear_missing_session_is_silent(pending):
    clear_hook.handle({})  # must not raise
