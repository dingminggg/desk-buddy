# src/desk_buddy/cc_signals.py
"""文件信号：Claude Code hook 与桌宠之间的「在等权限确认」通路。

约定目录 ~/.claude/data/desk-buddy/pending/ 下，每个等待确认的会话一个
<session_id>.json。写入原子（tempfile + os.replace），读取对缺失/损坏文件
容错。与 agent_pet 的 ~/.claude/data/... 习惯一致。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def data_dir() -> Path:
    return Path.home() / ".claude" / "data" / "desk-buddy"


def pending_dir() -> Path:
    return data_dir() / "pending"


def _safe_name(session_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", session_id)


def write_pending(session_id: str, message: str = "") -> None:
    d = pending_dir()
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{_safe_name(session_id)}.json"
    payload = {
        "session_id": session_id,
        "message": message,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    fd, tmp_path = tempfile.mkstemp(prefix=".cc-", suffix=".json", dir=str(d))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def clear_pending(session_id: str) -> None:
    target = pending_dir() / f"{_safe_name(session_id)}.json"
    try:
        target.unlink()
    except (FileNotFoundError, OSError):
        pass


def read_pending() -> set[str]:
    d = pending_dir()
    if not d.exists():
        return set()
    out: set[str] = set()
    for f in d.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        sid = data.get("session_id") if isinstance(data, dict) else None
        if sid:
            out.add(sid)
    return out


def prune_stale(max_age_seconds: int = 600) -> None:
    d = pending_dir()
    if not d.exists():
        return
    cutoff = time.time() - max_age_seconds
    for f in d.glob("*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass
