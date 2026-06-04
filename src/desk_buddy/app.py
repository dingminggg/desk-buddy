# src/desk_buddy/app.py
from datetime import datetime

from .config import Config
from .llm.base import LLMError
from .models import IntentAction, Reminder

CC_ALERT_TEXT = "🤖 Claude Code 在等你确认"
CC_MAX_RINGS = 3


def _fmt(dt: datetime) -> str:
    return dt.strftime("%m-%d %H:%M")


class SyncRunner:
    """Default runner: execute fn inline and call back directly. Lets App work
    and be tested without any threading."""

    def run(self, fn, on_done, on_error):
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001
            on_error(exc)
        else:
            on_done(result)


class App:
    """Wires PetWidget input -> Brain -> ReminderStore -> bubble feedback,
    and Scheduler due events -> a persistent reminder alert (queued, one at a
    time, manually dismissed, nagged every 30s).

    `pet` needs `say(text)`, `set_state(state)`, `show_alert(text)`.
    `notifier` needs `toast(title, message)` and `play_sound()`.
    """

    def __init__(self, config: Config, store, brain, pet, notifier, runner=None):
        self.config = config
        self.store = store
        self.brain = brain
        self.pet = pet
        self.notifier = notifier
        self.runner = runner or SyncRunner()
        self._busy = False
        self._due_queue: list[Reminder] = []
        self._alert_active = False
        self._alert_kind = None  # None | "reminder" | "cc"
        self._cc_pending = False
        self._cc_ring_count = 0

    def handle_user_text(self, text: str) -> None:
        if self._busy:
            self.pet.say("等我把上一句想完～")
            return
        self._busy = True
        self.pet.say("让我想想…")
        now = datetime.now()
        self.runner.run(
            lambda: self.brain.parse(text, now),
            lambda intent: self._on_parsed(intent, text),
            lambda exc: self._on_parse_error(exc, text),
        )

    def _on_parsed(self, intent, text: str) -> None:
        self._busy = False
        if intent.action == IntentAction.ADD:
            self._do_add(intent, text)
        elif intent.action == IntentAction.QUERY:
            self._do_query()
        elif intent.action == IntentAction.COMPLETE:
            self._do_complete(intent)
        elif intent.action == IntentAction.CANCEL:
            self._do_cancel(intent)
        else:  # CLARIFY
            self.pet.say(intent.text or "能再说清楚一点吗？")

    def _on_parse_error(self, exc: Exception, text: str) -> None:
        self._busy = False
        if isinstance(exc, LLMError):
            self.store.save_draft(text)
            self.pet.say("我现在连不上脑子，先把你的话记下了，稍等再说～")
        else:
            self.pet.say("出了点小问题，稍后再说～")

    def _do_add(self, intent, original_text: str) -> None:
        if intent.time is None:
            self.pet.say("这个提醒是什么时候呀？")
            return
        reminder = Reminder(text=intent.text or original_text,
                            due_at=intent.time, created_at=datetime.now())
        saved = self.store.add(reminder)
        self.pet.say(f"好的，{_fmt(saved.due_at)} 提醒你「{saved.text}」，记下啦！")

    def _do_query(self) -> None:
        items = self.store.list_active()
        if not items:
            self.pet.say("你现在没有待办提醒哦～")
            return
        lines = "\n".join(f"・{_fmt(i.due_at)} {i.text}" for i in items)
        self.pet.say("你的提醒：\n" + lines)

    def _do_complete(self, intent) -> None:
        matches = self.store.search_active(intent.text or "")
        if not matches:
            self.pet.say("没找到要完成的提醒～")
            return
        self.store.complete(matches[0].id)
        self.pet.say(f"「{matches[0].text}」已完成，棒！")

    def _do_cancel(self, intent) -> None:
        matches = self.store.search_active(intent.text or "")
        if not matches:
            self.pet.say("没找到要取消的提醒～")
            return
        self.store.cancel(matches[0].id)
        self.pet.say(f"「{matches[0].text}」已取消～")

    def handle_reminder_due(self, reminder: Reminder) -> None:
        # Queue the due reminder; show it now if nothing is on screen.
        self._due_queue.append(reminder)
        if not self._alert_active:
            self._present_next_due()

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
