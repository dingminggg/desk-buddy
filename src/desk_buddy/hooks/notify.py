# src/desk_buddy/hooks/notify.py
"""Notification hook：仅当 Claude Code 因权限确认而通知时，记下「在等确认」。

被 Claude Code 以 `python -m desk_buddy.hooks.notify` 拉起，hook 负载 JSON
从 stdin 读入。任何异常都吞掉并返回 0，绝不阻断 Claude Code。
"""

from __future__ import annotations

import json
import sys
import traceback

from desk_buddy import cc_signals


def handle(payload: dict) -> None:
    session_id = payload.get("session_id")
    message = payload.get("message", "") or ""
    if session_id and "permission" in message.lower():
        cc_signals.write_pending(session_id, message)


def main() -> int:
    try:
        raw = sys.stdin.read()
        if raw.strip():
            handle(json.loads(raw))
    except Exception:
        print("desk-buddy notify hook error:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
