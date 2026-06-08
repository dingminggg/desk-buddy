from collections.abc import Callable
from datetime import datetime

from .models import Reminder, RepeatRule
from .store import ReminderStore

# Real-time tick interval used by the app's QTimer (milliseconds).
TICK_INTERVAL_MS = 1_000


class Scheduler:
    """Pure-Python due checker. The app drives `tick` from a QTimer."""

    def __init__(self, store: ReminderStore, on_due: Callable[[Reminder], None]):
        self._store = store
        self._on_due = on_due

    def tick(self, now: datetime) -> None:
        for reminder in self._store.list_due(now):
            self._on_due(reminder)
            if reminder.repeat == RepeatRule.DAILY:
                self._store.advance_daily(reminder.id, now)
            else:
                self._store.mark_notified(reminder.id)
