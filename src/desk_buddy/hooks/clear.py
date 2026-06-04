# src/desk_buddy/hooks/clear.py
"""Stop / UserPromptSubmit hook：该会话不再等待确认，清掉它的 pending 文件。

被 Claude Code 以 `python -m desk_buddy.hooks.clear` 拉起。异常吞掉返回 0。
"""

from __future__ import annotations

import json
import sys
import traceback

from desk_buddy import cc_signals


def handle(payload: dict) -> None:
    session_id = payload.get("session_id")
    if session_id:
        cc_signals.clear_pending(session_id)


def main() -> int:
    try:
        raw = sys.stdin.read()
        if raw.strip():
            handle(json.loads(raw))
    except Exception:
        print("desk-buddy clear hook error:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
