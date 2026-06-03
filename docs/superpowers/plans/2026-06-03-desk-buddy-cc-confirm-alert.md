# Claude Code 权限确认提醒 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 当 Claude Code 需要权限确认时，桌面青蛙桌宠弹出提醒；人答复后 Claude 继续/回合结束，提醒自动收起。

**Architecture:** Claude Code 的 `Notification` hook 在权限确认时往 `~/.claude/data/desk-buddy/pending/<session_id>.json` 写文件，`Stop`/`UserPromptSubmit` hook 删除它；常驻桌宠每 ~1 秒轮询该目录，目录非空→弹 CC 提醒、变空→自动收起。CC 提醒复用现有持久提醒卡（单槽位），优先级低于定点提醒；铃声封顶 3 声。`python -m desk_buddy.install_hooks` 幂等把三条 hook 写进 `~/.claude/settings.json`。

**Tech Stack:** Python 3.11+、PySide6、pytest、stdlib（json/os/tempfile/re/time/pathlib）。

参考 spec：`docs/superpowers/specs/2026-06-03-desk-buddy-cc-confirm-alert-design.md`

---

## File Structure

| 文件 | 职责 |
|------|------|
| `src/desk_buddy/cc_signals.py` | 新增。pending 目录路径 + `write_pending`/`clear_pending`/`read_pending`/`prune_stale`/`_safe_name`。纯函数、可单测 |
| `src/desk_buddy/hooks/__init__.py` | 新增。空包标记 |
| `src/desk_buddy/hooks/notify.py` | 新增。`Notification` hook：仅权限通知时写 pending |
| `src/desk_buddy/hooks/clear.py` | 新增。`Stop`/`UserPromptSubmit` hook：清除该 session 的 pending |
| `src/desk_buddy/install_hooks.py` | 新增。幂等把三条 hook 写进 `~/.claude/settings.json` |
| `src/desk_buddy/pet_widget.py` | 改。`show_alert(text, kind=...)`、新增 `hide_alert()` |
| `src/desk_buddy/app.py` | 改。CC 提醒通道：`update_cc_pending` / `_show_cc` / 铃声封顶 / 与定点提醒优先级协调 |
| `src/desk_buddy/main.py` | 改。启动 `prune_stale()`；加 ~1s QTimer 轮询 |
| `README.md` | 改。「与 Claude Code 联动」安装说明 |
| `tests/test_cc_signals.py` | 新增 |
| `tests/test_cc_hooks.py` | 新增 |
| `tests/test_install_hooks.py` | 新增 |
| `tests/test_app.py` | 改。更新 FakePet（kind/hide_alert）+ CC 行为测试 |

约定常量（在 `app.py`）：`CC_ALERT_TEXT = "🤖 Claude Code 在等你确认"`，`CC_MAX_RINGS = 3`。

---

## Task 1: 信号层 cc_signals

**Files:**
- Create: `src/desk_buddy/cc_signals.py`
- Test: `tests/test_cc_signals.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cc_signals.py
import json
import os
import time

import pytest

from desk_buddy import cc_signals


@pytest.fixture
def pending(tmp_path, monkeypatch):
    d = tmp_path / "pending"
    monkeypatch.setattr(cc_signals, "pending_dir", lambda: d)
    return d


def test_write_then_read_roundtrip(pending):
    cc_signals.write_pending("sess-1", "needs your permission to use Bash")
    assert cc_signals.read_pending() == {"sess-1"}
    data = json.loads((pending / "sess-1.json").read_text("utf-8"))
    assert data["session_id"] == "sess-1"
    assert "permission" in data["message"]


def test_clear_removes_only_that_session(pending):
    cc_signals.write_pending("a")
    cc_signals.write_pending("b")
    cc_signals.clear_pending("a")
    assert cc_signals.read_pending() == {"b"}


def test_clear_missing_is_silent(pending):
    cc_signals.clear_pending("nope")  # must not raise


def test_read_missing_dir_is_empty(pending):
    assert cc_signals.read_pending() == set()


def test_read_tolerates_corrupt_file(pending):
    pending.mkdir(parents=True, exist_ok=True)
    (pending / "broken.json").write_text("{ not json", encoding="utf-8")
    cc_signals.write_pending("good")
    assert cc_signals.read_pending() == {"good"}


def test_safe_name_filters_illegal_chars(pending):
    cc_signals.write_pending("a/b\\c:d")
    files = list(pending.glob("*.json"))
    assert len(files) == 1
    assert files[0].name == "a_b_c_d.json"


def test_prune_stale_drops_old_keeps_fresh(pending):
    cc_signals.write_pending("old")
    cc_signals.write_pending("fresh")
    old = pending / "old.json"
    past = time.time() - 7200
    os.utime(old, (past, past))
    cc_signals.prune_stale(max_age_seconds=600)
    assert cc_signals.read_pending() == {"fresh"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc_signals.py -v`
Expected: FAIL（`ModuleNotFoundError: desk_buddy.cc_signals` 或 `AttributeError`）

- [ ] **Step 3: 实现 cc_signals**

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc_signals.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git add src/desk_buddy/cc_signals.py tests/test_cc_signals.py
git commit -m "feat(cc): file-signal layer for Claude Code pending-confirmation"
```

---

## Task 2: hook 脚本 notify / clear

**Files:**
- Create: `src/desk_buddy/hooks/__init__.py`
- Create: `src/desk_buddy/hooks/notify.py`
- Create: `src/desk_buddy/hooks/clear.py`
- Test: `tests/test_cc_hooks.py`

- [ ] **Step 1: 写失败测试**

```python
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
    assert cc_signals.read_pending() == {"s1"}


def test_notify_ignores_non_permission_message(pending):
    notify_hook.handle({
        "session_id": "s1",
        "message": "Claude is waiting for your input",
    })
    assert cc_signals.read_pending() == set()


def test_notify_ignores_missing_session(pending):
    notify_hook.handle({"message": "needs your permission"})
    assert cc_signals.read_pending() == set()


def test_clear_removes_session(pending):
    cc_signals.write_pending("s1", "needs permission")
    clear_hook.handle({"session_id": "s1"})
    assert cc_signals.read_pending() == set()


def test_clear_missing_session_is_silent(pending):
    clear_hook.handle({})  # must not raise
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc_hooks.py -v`
Expected: FAIL（`ModuleNotFoundError: desk_buddy.hooks`）

- [ ] **Step 3: 实现三个文件**

```python
# src/desk_buddy/hooks/__init__.py
```

```python
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
```

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc_hooks.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add src/desk_buddy/hooks tests/test_cc_hooks.py
git commit -m "feat(cc): Notification/Stop/UserPromptSubmit hook scripts"
```

---

## Task 3: pet_widget 支持 kind + hide_alert

**Files:**
- Modify: `src/desk_buddy/pet_widget.py:264-270`（`show_alert`）、其后新增 `hide_alert`
- Test: `tests/test_pet_alert.py`（新增，offscreen）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_pet_alert.py
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from desk_buddy.pet_widget import PetWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_show_alert_accepts_kind_and_is_visible(qapp):
    pet = PetWidget()
    pet.show_alert("🤖 Claude Code 在等你确认", kind="cc")
    assert not pet._alert.isHidden()
    assert pet._alert_label.text() == "🤖 Claude Code 在等你确认"


def test_hide_alert_hides_and_stops_nag(qapp):
    pet = PetWidget()
    pet.show_alert("⏰ 喝水")
    assert pet._alert_nag_timer.isActive()
    pet.hide_alert()
    assert pet._alert.isHidden()
    assert not pet._alert_nag_timer.isActive()


def test_show_alert_defaults_to_reminder_kind(qapp):
    pet = PetWidget()
    pet.show_alert("⏰ 喝水")  # no kind kwarg -> still works
    assert not pet._alert.isHidden()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pet_alert.py -v`
Expected: FAIL（`show_alert() got an unexpected keyword argument 'kind'` 及 `hide_alert` 不存在）

- [ ] **Step 3: 改 show_alert 并新增 hide_alert**

把 `src/desk_buddy/pet_widget.py` 中现有的 `show_alert` 方法（约 264-270 行）：

```python
    def show_alert(self, text: str) -> None:
        """Show a persistent reminder alert; stays until the user clicks 知道了."""
        self._alert_label.setText(text)
        self._alert.adjustSize()
        self._position_alert()
        self._alert.show()
        self._alert_nag_timer.start()
```

替换为（加 `kind` 形参 + 新增 `hide_alert`）：

```python
    def show_alert(self, text: str, kind: str = "reminder") -> None:
        """Show a persistent alert card; stays until dismissed.

        kind: "reminder" (定点提醒) 或 "cc" (Claude Code 等确认)。当前用于
        归属判定，预留样式区分；图标已包含在调用方传入的 text 里。
        """
        self._alert_kind = kind
        self._alert_label.setText(text)
        self._alert.adjustSize()
        self._position_alert()
        self._alert.show()
        self._alert_nag_timer.start()

    def hide_alert(self) -> None:
        """Programmatically dismiss the alert card (no alert_dismissed signal)."""
        self._alert_nag_timer.stop()
        self._alert.hide()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pet_alert.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add src/desk_buddy/pet_widget.py tests/test_pet_alert.py
git commit -m "feat(pet): show_alert kind param + programmatic hide_alert"
```

---

## Task 4: App CC 提醒通道

**Files:**
- Modify: `src/desk_buddy/app.py`（`__init__`、`_present_next_due`、`on_alert_dismissed`、`on_alert_nag`；新增 `update_cc_pending`、`_show_cc`、常量）
- Modify: `tests/test_app.py`（更新 `FakePet`；新增 CC 测试）

- [ ] **Step 1: 更新 FakePet 并写失败测试**

把 `tests/test_app.py` 顶部的 `FakePet` 替换为（接受 `kind`、记录 `hide_alert`）：

```python
class FakePet:
    def __init__(self):
        self.said = []
        self.alerts = []
        self.alert_kinds = []
        self.hidden = 0
        self.state = "idle"

    def say(self, text):
        self.said.append(text)

    def set_state(self, state):
        self.state = state

    def show_alert(self, text, kind="reminder"):
        self.alerts.append(text)
        self.alert_kinds.append(kind)

    def hide_alert(self):
        self.hidden += 1
```

在 `tests/test_app.py` 末尾追加 CC 测试：

```python
from desk_buddy.app import CC_ALERT_TEXT  # noqa: E402  (放文件顶部 import 区亦可)


def test_cc_pending_shows_alert_and_rings_once(store):
    app = _app(store, StubBrain(), Config(sound_enabled=True))
    app.update_cc_pending(True)
    assert app.pet.alerts[-1] == CC_ALERT_TEXT
    assert app.pet.alert_kinds[-1] == "cc"
    assert app.notifier.sounds == 1
    assert app._alert_kind == "cc"


def test_cc_resolved_hides_alert(store):
    app = _app(store, StubBrain(), Config(sound_enabled=True))
    app.update_cc_pending(True)
    app.update_cc_pending(False)
    assert app.pet.hidden == 1
    assert app._alert_kind is None


def test_cc_pending_idempotent_no_double_show(store):
    app = _app(store, StubBrain(), Config(sound_enabled=True))
    app.update_cc_pending(True)
    app.update_cc_pending(True)  # poll fires again, same state
    assert app.pet.alerts.count(CC_ALERT_TEXT) == 1
    assert app.notifier.sounds == 1


def test_cc_nag_caps_at_three_rings(store):
    app = _app(store, StubBrain(), Config(sound_enabled=True))
    app.update_cc_pending(True)   # ring 1
    app.on_alert_nag()            # ring 2
    app.on_alert_nag()            # ring 3
    app.on_alert_nag()            # capped, silent
    assert app.notifier.sounds == 3


def test_reminder_priority_blocks_cc_until_dismissed(store):
    app = _app(store, StubBrain(), Config(sound_enabled=True))
    app.handle_reminder_due(_mk("会议"))  # reminder occupies the card
    app.update_cc_pending(True)           # cc pending, must NOT show yet
    assert app._alert_kind == "reminder"
    assert CC_ALERT_TEXT not in app.pet.alerts
    app.on_alert_dismissed()              # reminder closed -> cc fills the slot
    assert app._alert_kind == "cc"
    assert app.pet.alerts[-1] == CC_ALERT_TEXT


def test_reminder_preempts_onscreen_cc(store):
    app = _app(store, StubBrain(), Config(sound_enabled=True))
    app.update_cc_pending(True)           # cc showing
    app.handle_reminder_due(_mk("会议"))  # reminder preempts the card
    assert app._alert_kind == "reminder"
    assert app.pet.alerts[-1] == "⏰ 会议"
    app.on_alert_dismissed()              # back to still-pending cc
    assert app._alert_kind == "cc"
    assert app.pet.alerts[-1] == CC_ALERT_TEXT


def test_cc_manual_dismiss_does_not_reshow(store):
    app = _app(store, StubBrain(), Config(sound_enabled=True))
    app.update_cc_pending(True)
    app.on_alert_dismissed()              # user clicked 知道了 on the cc card
    assert app._alert_kind is None
    # still pending on disk, but we don't auto-reshow until it toggles
    assert app.pet.alerts.count(CC_ALERT_TEXT) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -v`
Expected: FAIL（`ImportError: CC_ALERT_TEXT`、`update_cc_pending` 不存在等）

- [ ] **Step 3: 实现 App CC 通道**

在 `src/desk_buddy/app.py` 顶部 `_fmt` 前加常量：

```python
CC_ALERT_TEXT = "🤖 Claude Code 在等你确认"
CC_MAX_RINGS = 3
```

`__init__` 末尾（现 `self._alert_active = False` 之后）补三个状态：

```python
        self._alert_active = False
        self._alert_kind = None  # None | "reminder" | "cc"
        self._cc_pending = False
        self._cc_ring_count = 0
```

把现有 `_present_next_due` 整体替换为（队列空时回落到 CC）：

```python
    def _present_next_due(self) -> None:
        if self._due_queue:
            reminder = self._due_queue.pop(0)
            self._alert_active = True
            self._alert_kind = "reminder"
            self.pet.show_alert(f"⏰ {reminder.text}")
            self.notifier.toast("desk-buddy 提醒", reminder.text)
            if self.config.sound_enabled:
                self.notifier.play_sound()
            return
        # 没有更多定点提醒：让出卡片，若 Claude Code 仍在等确认则补弹 CC
        self._alert_active = False
        self._alert_kind = None
        if self._cc_pending:
            self._show_cc()
```

把现有 `on_alert_dismissed` 替换为（区分 CC / 定点提醒）：

```python
    def on_alert_dismissed(self) -> None:
        # 用户手动点「知道了」：清当前卡。定点提醒 -> 推进队列/回落 CC；
        # CC -> 就地消除，不在仍 pending 时自动重弹（等下次状态翻转）。
        prev = self._alert_kind
        self._alert_active = False
        self._alert_kind = None
        if prev == "cc":
            self._cc_ring_count = 0
            return
        self._present_next_due()
```

把现有 `on_alert_nag` 替换为（CC 封顶 3 声；定点提醒维持持续响）：

```python
    def on_alert_nag(self) -> None:
        if self._alert_kind == "cc":
            if self._cc_ring_count < CC_MAX_RINGS:
                if self.config.sound_enabled:
                    self.notifier.play_sound()
                self._cc_ring_count += 1
            return
        # 定点提醒：每 30s 持续响，直到手动关闭
        if self.config.sound_enabled:
            self.notifier.play_sound()
```

在 `on_alert_nag` 之后新增 CC 通道方法：

```python
    def update_cc_pending(self, pending: bool) -> None:
        """由 main 的轮询调用：pending = pending 目录是否非空。"""
        if pending == self._cc_pending:
            return
        self._cc_pending = pending
        if pending:
            # 卡片空闲才弹；定点提醒占用时排队，待其关闭后回落
            if self._alert_kind is None:
                self._show_cc()
        else:
            # 已解决：只有当前显示的就是 CC 卡才自动收起
            if self._alert_kind == "cc":
                self.pet.hide_alert()
                self._alert_kind = None
                self._cc_ring_count = 0

    def _show_cc(self) -> None:
        self._alert_kind = "cc"
        self._cc_ring_count = 1
        self.pet.show_alert(CC_ALERT_TEXT, kind="cc")
        self.notifier.toast("desk-buddy", "Claude Code 在等你确认")
        if self.config.sound_enabled:
            self.notifier.play_sound()
```

> 注意：`on_alert_nag` 第一句的 `_cc_ring_count` 计数与 `_show_cc` 里初始 `=1` 配合——初次展示响 1 声（ring#1），两次 nag 再响 2 声（ring#2、#3），第 3 次 nag 起静默，合计 3 声。

- [ ] **Step 4: 跑测试确认通过（含既有用例不回归）**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -v`
Expected: PASS（既有 reminder/async 用例 + 7 个新 CC 用例全过）

- [ ] **Step 5: 提交**

```bash
git add src/desk_buddy/app.py tests/test_app.py
git commit -m "feat(cc): App CC-confirmation alert channel (priority + 3-ring cap + auto-clear)"
```

---

## Task 5: 一键安装 install_hooks

**Files:**
- Create: `src/desk_buddy/install_hooks.py`
- Test: `tests/test_install_hooks.py`

- [ ] **Step 1: 写失败测试**

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_install_hooks.py -v`
Expected: FAIL（`ModuleNotFoundError: desk_buddy.install_hooks`）

- [ ] **Step 3: 实现 install_hooks**

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_install_hooks.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add src/desk_buddy/install_hooks.py tests/test_install_hooks.py
git commit -m "feat(cc): idempotent install_hooks writer for ~/.claude/settings.json"
```

---

## Task 6: main 接线（轮询 + 启动清理）

**Files:**
- Modify: `src/desk_buddy/main.py`

- [ ] **Step 1: 加 import**

`src/desk_buddy/main.py` 顶部 import 区（与其它 `from .xxx` 并列）加：

```python
from . import cc_signals
```

- [ ] **Step 2: 启动清理 + 轮询计时器**

在 `main()` 中、`scheduler` 那段计时器之后（现 `timer.start(TICK_INTERVAL_MS)` 之后、`pet.show()` 之前）插入：

```python
    # Claude Code「等你确认」轮询：启动清掉陈旧信号，再每秒扫一次
    cc_signals.prune_stale()
    cc_timer = QTimer()
    cc_timer.timeout.connect(
        lambda: controller.update_cc_pending(bool(cc_signals.read_pending()))
    )
    cc_timer.start(1000)
```

> `QTimer` 已在 `main()` 顶部 `from PySide6.QtCore import QTimer` 导入；`cc_timer` 为局部变量，`app.exec()` 期间一直存活，无需额外持有。

- [ ] **Step 3: 离屏冒烟验证（不卡、能弹能收）**

Run（PowerShell，临时 HOME 隔离真实配置；写一个 pending 文件→应弹，删掉→应收）:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.venv\Scripts\python.exe -c @"
import os, time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from desk_buddy import cc_signals
from desk_buddy.app import App, CC_ALERT_TEXT
from desk_buddy.config import Config
from desk_buddy.pet_widget import PetWidget
from desk_buddy.store import ReminderStore
from desk_buddy import notify

app = QApplication([])
pet = PetWidget()
ctl = App(Config(sound_enabled=False), ReminderStore(':memory:'), None, pet, notify)
cc_signals.prune_stale()
t = QTimer(); t.timeout.connect(lambda: ctl.update_cc_pending(bool(cc_signals.read_pending()))); t.start(200)

cc_signals.write_pending('smoke', 'needs your permission')
QTimer.singleShot(600, lambda: print('after write, kind =', ctl._alert_kind))
QTimer.singleShot(900, lambda: cc_signals.clear_pending('smoke'))
QTimer.singleShot(1400, lambda: print('after clear, kind =', ctl._alert_kind))
QTimer.singleShot(1700, app.quit)
app.exec()
"@
```

Expected: 打印 `after write, kind = cc` 然后 `after clear, kind = None`（验证轮询→弹出→自动收起闭环）。

- [ ] **Step 4: 提交**

```bash
git add src/desk_buddy/main.py
git commit -m "feat(cc): poll pending dir each second; prune stale on startup"
```

---

## Task 7: README 文档 + 全量回归

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 加「与 Claude Code 联动」一节**

在 `README.md` 合适位置（用法之后）新增：

```markdown
## 与 Claude Code 联动（权限确认提醒）

让 Claude Code 需要你批准某个操作时，桌宠青蛙弹出提醒把你喊回来；你在终端
答复、Claude 继续或本回合结束后，提醒自动收起。

1. 先装好本包（开发模式）：`pip install -e .`
2. 注册 hooks：`python -m desk_buddy.install_hooks`
   - 幂等地把三条 hook 写进 `~/.claude/settings.json`
     （`Notification`/`Stop`/`UserPromptSubmit`），不影响你已有配置。
   - 命令里写的是当前 venv 的 Python 绝对路径。
3. 重启 Claude Code 使 hooks 生效。
4. 保持 desk-buddy 运行即可。仅在「权限确认」时提醒；铃声最多响 3 次。

信号文件位于 `~/.claude/data/desk-buddy/pending/`，按会话分文件，支持同时开多个
Claude Code 会话。桌宠未运行时 hook 静默退出，不影响 Claude Code。
```

- [ ] **Step 2: 全量测试回归**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: PASS（全绿；既有 72 项 + 本次新增）

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs: Claude Code confirmation-alert setup in README"
```

---

## 自检（写计划者已核对）

- **Spec 覆盖**：①触发=仅权限(notify.py 过滤 "permission")✓ ②强度=持久卡+3声封顶(Task4 _show_cc/on_alert_nag)✓ ③自动收起=Stop/UserPromptSubmit→clear+轮询hide(Task2/4/6)✓ ④IPC=文件信号(Task1)✓ ⑤安装=install_hooks(Task5)✓ ⑥优先级=定点>CC(Task4)✓ ⑦启动清陈旧+多会话(Task1 prune_stale/Task6)✓ ⑧README(Task7)✓
- **占位符**：无 TBD/TODO；每个改代码步骤均给出完整代码。
- **类型/签名一致**：`show_alert(text, kind="reminder")`、`hide_alert()`、`update_cc_pending(bool)`、`_show_cc()`、`CC_ALERT_TEXT`/`CC_MAX_RINGS`、`cc_signals.{write_pending,clear_pending,read_pending,prune_stale,pending_dir}`、`install_hooks.{add_hook_entries,install}` 在各任务中前后一致；FakePet 在 Task4 同步加 `kind`/`hide_alert`，与 Task3 真实 PetWidget 对齐。
```
