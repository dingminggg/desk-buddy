# src/desk_buddy/install_hooks.py
"""把 desk-buddy 的三条 Claude Code hook 幂等写进 ~/.claude/settings.json。

用法：python -m desk_buddy.install_hooks
命令里用安装时的 sys.executable 绝对路径，保证指向 venv 内的 Python。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HOOK_MODULES = {
    "Notification": "desk_buddy.hooks.notify",
    "Stop": "desk_buddy.hooks.clear",
    "UserPromptSubmit": "desk_buddy.hooks.clear",
}


def _command(python_exe: str, module: str) -> str:
    return f'"{python_exe}" -m {module}'


def add_hook_entries(settings: dict, python_exe: str) -> dict:
    """幂等地把三条 hook 加入 settings（原地修改并返回）。"""
    hooks = settings.setdefault("hooks", {})
    for event, module in HOOK_MODULES.items():
        cmd = _command(python_exe, module)
        entries = hooks.setdefault(event, [])
        already = any(
            cmd == h.get("command")
            for entry in entries
            for h in entry.get("hooks", [])
        )
        if already:
            continue
        entries.append({"hooks": [{"type": "command", "command": cmd}]})
    return settings


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".json",
                               dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def install(python_exe: str | None = None, home: Path | None = None) -> Path:
    python_exe = python_exe or sys.executable
    home = home or Path.home()
    path = home / ".claude" / "settings.json"

    settings: dict = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings = loaded
        except (json.JSONDecodeError, ValueError, OSError):
            settings = {}
        # 备份原文件
        try:
            backup = path.with_suffix(".json.bak")
            backup.write_text(json.dumps(settings, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        except OSError:
            pass

    add_hook_entries(settings, python_exe)
    _atomic_write(path, json.dumps(settings, ensure_ascii=False, indent=2))
    return path


def main() -> int:
    path = install()
    print(f"desk-buddy hooks 已写入 {path}")
    print("三条 hook：Notification→notify, Stop→clear, UserPromptSubmit→clear")
    print("重启 Claude Code 使其生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
