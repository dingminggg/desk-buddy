# src/desk_buddy/app.py
from datetime import datetime

from .config import Config
from .llm.base import LLMError
from .models import IntentAction, Reminder


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

    `pet` needs `say(text)`, `set_state(state)`, `show_alert(text)`,
    `show_answer(text)`.
    `notifier` needs `play_sound(sound_file="")`.
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
        self._alert_active = False  # True only while a *reminder* owns the card
        self._alert_kind = None  # None | "reminder" | "chat"
        self._current_reminder = None  # 当前占用卡片的定点提醒（供 chat 抢占时回退）

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
        elif intent.action == IntentAction.CHAT:
            self._do_chat(intent)
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

    def _do_chat(self, intent) -> None:
        # 答案与提醒/CC 共用同一张卡：当成"一条手动关、不响铃的临时提醒"。
        text = intent.text or "我好像没什么可说的～"
        # 若此刻正显示定点提醒，把它放回队首，关掉答案后会重新弹出（不丢提醒）。
        if self._alert_kind == "reminder" and self._current_reminder is not None:
            self._due_queue.insert(0, self._current_reminder)
            self._current_reminder = None
        self._alert_kind = "chat"
        self._alert_active = True  # 占用卡片：新到点的提醒排队，等答案关闭再弹
        self.pet.show_alert(text, kind="chat")  # 不响铃、不唠叨

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
            self._current_reminder = reminder
            self.pet.show_alert(f"⏰ {reminder.text}")
            if self.config.sound_enabled:
                self.notifier.play_sound(self.config.sound_file)
            return
        # 没有更多定点提醒：让出卡片
        self._alert_active = False
        self._alert_kind = None
        self._current_reminder = None

    def on_alert_dismissed(self) -> None:
        # 用户手动点「知道了」：清当前卡，推进定点提醒队列。
        self._alert_active = False
        self._alert_kind = None
        self._present_next_due()

    def on_alert_nag(self) -> None:
        if self._alert_kind == "chat":
            return  # 答案不响铃
        # 定点提醒：每 30s 持续响，直到手动关闭
        if self.config.sound_enabled:
            self.notifier.play_sound(self.config.sound_file)
