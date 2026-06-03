# src/desk_buddy/app.py
from datetime import datetime

from .config import Config
from .llm.base import LLMError
from .models import IntentAction, Reminder


def _fmt(dt: datetime) -> str:
    return dt.strftime("%m-%d %H:%M")


class App:
    """Wires PetWidget input -> Brain -> ReminderStore -> bubble feedback,
    and Scheduler due events -> a persistent reminder alert (queued, one at a
    time, manually dismissed, nagged every 30s).

    `pet` needs `say(text)`, `set_state(state)`, `show_alert(text)`.
    `notifier` needs `toast(title, message)` and `play_sound()`.
    """

    def __init__(self, config: Config, store, brain, pet, notifier):
        self.config = config
        self.store = store
        self.brain = brain
        self.pet = pet
        self.notifier = notifier
        self._due_queue: list[Reminder] = []
        self._alert_active = False

    def handle_user_text(self, text: str) -> None:
        try:
            intent = self.brain.parse(text, datetime.now())
        except LLMError:
            self.store.save_draft(text)
            self.pet.say("我现在连不上脑子，先把你的话记下了，稍等再说～")
            return

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
        if not self._due_queue:
            return
        reminder = self._due_queue.pop(0)
        self._alert_active = True
        self.pet.show_alert(f"⏰ {reminder.text}")
        self.notifier.toast("desk-buddy 提醒", reminder.text)
        if self.config.sound_enabled:
            self.notifier.play_sound()

    def on_alert_dismissed(self) -> None:
        # User closed the current alert -> show the next queued one, if any.
        self._alert_active = False
        self._present_next_due()

    def on_alert_nag(self) -> None:
        # Re-sound every 30s while a reminder stays unacknowledged.
        if self.config.sound_enabled:
            self.notifier.play_sound()
