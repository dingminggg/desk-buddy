# tests/test_install_hooks.py
import json

from desk_buddy import install_hooks


def test_add_hook_entries_registers_three_events():
    settings = {}
    install_hooks.add_hook_entries(settings, "C:/py/python.exe")
    hooks = settings["hooks"]
    assert set(hooks) == {"Notification", "Stop", "UserPromptSubmit"}
    cmds = [h["command"]
            for ev in hooks.values() for entry in ev for h in entry["hooks"]]
    assert any("desk_buddy.hooks.notify" in c for c in cmds)
    assert sum("desk_buddy.hooks.clear" in c for c in cmds) == 2
    assert all(c.startswith('"C:/py/python.exe"') for c in cmds)


def test_add_hook_entries_is_idempotent():
    settings = {}
    install_hooks.add_hook_entries(settings, "py.exe")
    install_hooks.add_hook_entries(settings, "py.exe")
    notif = settings["hooks"]["Notification"]
    assert len(notif) == 1  # not duplicated


def test_add_hook_entries_preserves_unrelated(tmp_path):
    settings = {"model": "opus", "hooks": {"PreToolUse": [{"hooks": []}]}}
    install_hooks.add_hook_entries(settings, "py.exe")
    assert settings["model"] == "opus"
    assert "PreToolUse" in settings["hooks"]
    assert "Notification" in settings["hooks"]


def test_install_writes_settings_file(tmp_path):
    path = install_hooks.install(python_exe="py.exe", home=tmp_path)
    assert path == tmp_path / ".claude" / "settings.json"
    data = json.loads(path.read_text("utf-8"))
    assert "Notification" in data["hooks"]


def test_install_merges_into_existing(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    install_hooks.install(python_exe="py.exe", home=tmp_path)
    data = json.loads(settings_path.read_text("utf-8"))
    assert data["model"] == "opus"
    assert "Stop" in data["hooks"]
