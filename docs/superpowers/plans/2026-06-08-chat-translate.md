# 桌宠翻译 + 简单问答 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让桌宠在"不是提醒操作"时直接回答用户（翻译、简单问答），结果显示在一张独立、手动关闭的答案卡上。

**Architecture:** 复用现有 Intent 管道，新增 `chat` 动作——一次 LLM 调用同时分类并给出答案。App 收到 `CHAT` 调 `pet.show_answer(text)`；答案卡是 PetWidget 里一张独立持久卡片，点 ✕ 关闭，不自动消失、不响铃，完全不碰提醒/CC 的告警卡仲裁状态机。

**Tech Stack:** Python 3.11、pydantic、PySide6、pytest。

---

### Task 1: `IntentAction` 增加 `chat`

**Files:**
- Modify: `src/desk_buddy/models.py:28-33`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

加到 `tests/test_models.py` 末尾：

```python
def test_intent_action_has_chat():
    from desk_buddy.models import IntentAction
    assert IntentAction("chat") == IntentAction.CHAT
    assert IntentAction.CHAT.value == "chat"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py::test_intent_action_has_chat -v`
Expected: FAIL — `AttributeError: CHAT`（或 `ValueError: 'chat' is not a valid IntentAction`）。

- [ ] **Step 3: Write minimal implementation**

`src/desk_buddy/models.py` 的 `IntentAction` 加一个成员：

```python
class IntentAction(str, Enum):
    ADD = "add"
    QUERY = "query"
    COMPLETE = "complete"
    CANCEL = "cancel"
    CHAT = "chat"
    CLARIFY = "clarify"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/desk_buddy/models.py tests/test_models.py
git commit -m "feat(models): add CHAT intent action"
```

---

### Task 2: Brain 提示词支持 chat

**Files:**
- Modify: `src/desk_buddy/brain.py:8-18`
- Test: `tests/test_brain.py`

`Brain.parse` 只是把 LLM 返回的 JSON 校验成 `Intent`；`CHAT` 现在已是合法 action，所以代码逻辑无需改动，只改 system 提示词，让模型在非提醒场景返回 chat。测试用 `ScriptedProvider`（已存在）喂一段 chat JSON。

- [ ] **Step 1: Write the failing test**

加到 `tests/test_brain.py` 末尾：

```python
def test_parses_chat_answer():
    p = ScriptedProvider(['{"action": "chat", "text": "Bonjour"}'])
    intent = Brain(p).parse("把“你好”翻译成法语", NOW)
    assert intent.action == IntentAction.CHAT
    assert intent.text == "Bonjour"


def test_system_prompt_mentions_chat():
    p = ScriptedProvider(['{"action": "chat", "text": "x"}'])
    Brain(p).parse("法国的首都是哪", NOW)
    assert "chat" in p.calls[0][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_brain.py::test_system_prompt_mentions_chat -v`
Expected: `test_parses_chat_answer` 其实会 PASS（CHAT 已合法）；`test_system_prompt_mentions_chat` FAIL —— 当前提示词里没有 "chat"。

- [ ] **Step 3: Write minimal implementation**

把 `src/desk_buddy/brain.py` 的 `SYSTEM_TEMPLATE` 整体替换为：

```python
SYSTEM_TEMPLATE = """你是桌面助手的解析器。当前时间是 {now}（请据此把相对时间换算成绝对时间）。
把用户的话解析为一个 JSON 对象，只输出 JSON，不要任何多余文字：
{{"action": "<add|query|complete|cancel|chat|clarify>", "time": "<ISO8601 本地时间或 null>", "text": "<字符串>"}}

规则：
- 用户要新建提醒 -> action=add，time 填绝对时间（如 2026-06-04T15:00:00），text 填事项内容。
- 用户问有哪些提醒 -> action=query。
- 用户说某事做完了 -> action=complete，text 填能匹配该提醒的关键词。
- 用户要取消某提醒 -> action=cancel，text 填关键词。
- 既不是提醒操作、但你能直接回答（让你翻译、问常识/简单问题、闲聊）-> action=chat，
  text 填你给用户的直接答案或译文；简洁明了，适合在小卡片里读完。
- 想记提醒但时间含糊，或完全听不懂、意图不明 -> action=clarify，text 填你要反问用户的话。
只返回 JSON。"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_brain.py -v`
Expected: 全部 PASS（含原有 add/query/clarify 用例）。

- [ ] **Step 5: Commit**

```bash
git add src/desk_buddy/brain.py tests/test_brain.py
git commit -m "feat(brain): prompt returns chat action for translation/Q&A"
```

---

### Task 3: App 处理 CHAT -> show_answer

**Files:**
- Modify: `src/desk_buddy/app.py:29-37`（类 docstring）、`app.py:67-78`（`_on_parsed`）、新增 `_do_chat`
- Test: `tests/test_app.py:14-33`（FakePet 加 `show_answer`）、文件末尾加用例

- [ ] **Step 1: Write the failing test**

先给 `tests/test_app.py` 的 `FakePet` 加记录能力。把 `__init__` 与方法区改成（在现有基础上加 `self.answers` 和 `show_answer`）：

```python
class FakePet:
    def __init__(self):
        self.said = []
        self.alerts = []
        self.alert_kinds = []
        self.answers = []
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

    def show_answer(self, text):
        self.answers.append(text)
```

再加用例到文件末尾：

```python
def test_chat_intent_shows_answer_card(store):
    brain = StubBrain(Intent(action=IntentAction.CHAT, text="Bonjour"))
    app = _app(store, brain)
    app.handle_user_text("把“你好”翻译成法语")
    assert app.pet.answers[-1] == "Bonjour"
    # chat 不应碰提醒/CC 卡，也不入库
    assert app._alert_kind is None
    assert store.list_active() == []


def test_chat_empty_text_has_fallback(store):
    brain = StubBrain(Intent(action=IntentAction.CHAT, text=None))
    app = _app(store, brain)
    app.handle_user_text("???")
    assert app.pet.answers[-1]  # 非空兜底
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py::test_chat_intent_shows_answer_card -v`
Expected: FAIL —— 当前 `_on_parsed` 把 CHAT 落到 `else` 分支调 `pet.say`，`pet.answers` 为空。

- [ ] **Step 3: Write minimal implementation**

(a) `src/desk_buddy/app.py` 类 docstring 里把 pet 协议补上 `show_answer`：

```python
    `pet` needs `say(text)`, `set_state(state)`, `show_alert(text)`,
    `show_answer(text)`.
    `notifier` needs `play_sound(sound_file="")`.
```

(b) `_on_parsed` 增加 CHAT 分支（放在 CANCEL 与 else 之间）：

```python
        elif intent.action == IntentAction.CANCEL:
            self._do_cancel(intent)
        elif intent.action == IntentAction.CHAT:
            self._do_chat(intent)
        else:  # CLARIFY
            self.pet.say(intent.text or "能再说清楚一点吗？")
```

(c) 新增方法（放在 `_do_cancel` 之后）：

```python
    def _do_chat(self, intent) -> None:
        self.pet.show_answer(intent.text or "我好像没什么可说的～")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app.py -v`
Expected: 全部 PASS（含原有 add/query/complete/cancel/cc 用例，无回归）。

- [ ] **Step 5: Commit**

```bash
git add src/desk_buddy/app.py tests/test_app.py
git commit -m "feat(app): route CHAT intent to pet.show_answer"
```

---

### Task 4: PetWidget 答案卡（show_answer / hide_answer）

**Files:**
- Modify: `src/desk_buddy/pet_widget.py`（`__init__` 末尾加答案卡构造；public API 区加方法；internals 区加定位）
- Test: `tests/test_pet_alert.py`（复用其 `qapp` fixture）

答案卡仿照告警卡构造，但：在宠物**下方**显示（避开上方的告警卡）、带一个 ✕ 关闭按钮（点击仅本地 `hide`，不发信号）、**无 nag 定时器、不自动消失**、文本可选中。

- [ ] **Step 1: Write the failing test**

加到 `tests/test_pet_alert.py` 末尾：

```python
def test_show_answer_visible_with_text(qapp):
    pet = PetWidget()
    pet.show_answer("Bonjour le monde")
    assert not pet._answer.isHidden()
    assert pet.answer_text() == "Bonjour le monde"


def test_hide_answer_hides(qapp):
    pet = PetWidget()
    pet.show_answer("hi")
    pet.hide_answer()
    assert pet._answer.isHidden()


def test_answer_card_independent_of_alert(qapp):
    pet = PetWidget()
    pet.show_alert("⏰ 喝水")
    pet.show_answer("42")
    # 显示答案卡不得影响告警卡，也不碰 nag 定时器
    assert not pet._alert.isHidden()
    assert not pet._answer.isHidden()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pet_alert.py::test_show_answer_visible_with_text -v`
Expected: FAIL —— `AttributeError: 'PetWidget' object has no attribute 'show_answer'`。

- [ ] **Step 3: Write minimal implementation**

(a) 在 `src/desk_buddy/pet_widget.py` 的 `__init__` 中，紧接 `self._alert.hide()` 之后、`# Re-sound timer` 之前，插入答案卡构造：

```python
        # Persistent answer card (translation / Q&A). Manual close only,
        # no auto-hide, no sound. Deliberately separate from the reminder/CC
        # alert card so it never touches that arbitration. Shown BELOW the pet
        # to avoid overlapping the alert card (which sits above).
        self._answer = QWidget(
            None,
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint,
        )
        self._answer.setAttribute(Qt.WA_TranslucentBackground)
        self._answer.setStyleSheet(
            "#answerCard { background:#ffffff; border:1px solid #cfe3d0;"
            " border-radius:14px; }"
            " QLabel { color:#3a3a3a; font-size:15px; }"
            " #ansCloseBtn { border:none; background:transparent; color:#b7ae98;"
            " font-size:13px; border-radius:11px; }"
            " #ansCloseBtn:hover { background:#f3ecda; color:#e2685f; }")
        answer_outer = QVBoxLayout(self._answer)
        answer_outer.setContentsMargins(14, 12, 14, 14)
        answer_outer.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        answer_card = QFrame()
        answer_card.setObjectName("answerCard")
        answer_box = QVBoxLayout(answer_card)
        answer_box.setContentsMargins(10, 7, 10, 7)
        answer_box.setSpacing(6)
        ans_top = QHBoxLayout()
        ans_top.setContentsMargins(0, 0, 0, 0)
        self._answer_close_btn = QPushButton("✕")
        self._answer_close_btn.setObjectName("ansCloseBtn")
        self._answer_close_btn.setFixedSize(22, 22)
        self._answer_close_btn.setCursor(Qt.PointingHandCursor)
        self._answer_close_btn.clicked.connect(self.hide_answer)
        ans_top.addStretch(1)
        ans_top.addWidget(self._answer_close_btn)
        self._answer_label = QLabel()
        self._answer_label.setWordWrap(True)
        self._answer_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        answer_box.addLayout(ans_top)
        answer_box.addWidget(self._answer_label)
        answer_outer.addWidget(answer_card)
        answer_shadow = QGraphicsDropShadowEffect(self._answer)
        answer_shadow.setBlurRadius(20)
        answer_shadow.setXOffset(0)
        answer_shadow.setYOffset(3)
        answer_shadow.setColor(QColor(0, 0, 0, 80))
        answer_card.setGraphicsEffect(answer_shadow)
        self._answer.hide()
```

(b) 在 public API 区（紧接 `hide_alert` 方法之后）加：

```python
    def show_answer(self, text: str) -> None:
        """Show a persistent answer card (translation / Q&A). Manual close
        only — no auto-hide, no sound. Independent of the alert card."""
        self._answer_label.setText(text)
        # 与 show_alert 同样的折行策略：按单行宽度定宽（上限 ALERT_TEXT_MAX_W），
        # 再用 heightForWidth 固定折行后的高度，让卡片精确贴合内容。
        natural = self._answer_label.fontMetrics().horizontalAdvance(text)
        width = min(natural + 8, ALERT_TEXT_MAX_W)
        self._answer_label.setFixedWidth(width)
        self._answer_label.setFixedHeight(
            self._answer_label.heightForWidth(width))
        self._answer.adjustSize()
        self._position_answer()
        self._answer.show()

    def hide_answer(self) -> None:
        """Hide the answer card (local only; App holds no chat state)."""
        self._answer.hide()

    def answer_text(self) -> str:
        return self._answer_label.text()
```

(c) 在 internals 区（紧接 `_position_alert` 之后）加：

```python
    def _position_answer(self) -> None:
        # 宠物正下方、水平居中（告警卡在上方，二者错开不重叠）。
        pos = self.pos()
        x = pos.x() + PET_SIZE // 2 - self._answer.width() // 2
        y = pos.y() + PET_SIZE - ALERT_GAP_FUDGE
        self._answer.move(x, y)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pet_alert.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/desk_buddy/pet_widget.py tests/test_pet_alert.py
git commit -m "feat(pet): persistent answer card for chat replies"
```

---

### Task 5: 版本 bump 到 0.3.0 + 全量校验

**Files:**
- Modify: `src/desk_buddy/__init__.py:3`

- [ ] **Step 1: 跑全量测试**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: 全绿（约 119 passed）。若有红，回到对应 Task 修复，勿改测试迁就实现。

- [ ] **Step 2: bump 版本**

把 `src/desk_buddy/__init__.py` 的版本改为：

```python
__version__ = "0.3.0"
```

- [ ] **Step 3: 校验版本一致**

Run: `.venv\Scripts\python.exe -m pytest tests/test_version.py -q`
Expected: PASS。

- [ ] **Step 4: Commit + tag**

```bash
git add src/desk_buddy/__init__.py
git commit -m "chore: bump version to 0.3.0 (chat translate + Q&A)"
git tag -a v0.3.0 -m "desk-buddy 0.3.0 — pet translation + simple Q&A"
```

- [ ] **Step 5（可选，由用户决定）：重新打包 exe**

停掉运行实例后：
```powershell
& .venv\Scripts\python.exe -m PyInstaller --noconfirm --clean desk_buddy.spec
```
产物：`dist\desk-buddy.exe`。

---

## 验收

- 对桌宠说"把你好翻译成法语" -> 弹出答案卡显示译文，点 ✕ 才关闭。
- 对桌宠说"法国的首都是哪" -> 答案卡显示答案。
- 对桌宠说"明天下午3点提醒我开会" -> 仍走提醒流程（气泡确认 + 入库），不弹答案卡。
- 提醒/CC 告警卡的现有行为无回归。
