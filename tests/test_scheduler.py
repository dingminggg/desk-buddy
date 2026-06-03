from datetime import datetime

import pytest

from desk_buddy.models import Reminder, RepeatRule
from desk_buddy.scheduler import Scheduler
from desk_buddy.store import ReminderStore


@pytest.fixture
def store():
    s = ReminderStore(":memory:")
    yield s
    s.close()


def _mk(text, due, repeat=RepeatRule.NONE):
    return Reminder(text=text, due_at=due, repeat=repeat,
                    created_at=datetime(2026, 6, 3, 10, 0))


def test_tick_fires_due_reminder_once(store):
    fired = []
    sched = Scheduler(store, fired.append)
    store.add(_mk("到点", datetime(2026, 6, 4, 15, 0)))
    now = datetime(2026, 6, 4, 16, 0)
    sched.tick(now)
    sched.tick(now)  # second tick must NOT re-fire
    assert [r.text for r in fired] == ["到点"]


def test_tick_ignores_future_reminder(store):
    fired = []
    sched = Scheduler(store, fired.append)
    store.add(_mk("未来", datetime(2026, 6, 4, 17, 0)))
    sched.tick(datetime(2026, 6, 4, 16, 0))
    assert fired == []


def test_daily_reminder_reschedules_and_fires_next_day(store):
    fired = []
    sched = Scheduler(store, fired.append)
    store.add(_mk("吃药", datetime(2026, 6, 4, 8, 0), repeat=RepeatRule.DAILY))
    sched.tick(datetime(2026, 6, 4, 8, 30))      # fires day 1
    sched.tick(datetime(2026, 6, 4, 23, 0))      # same day, no re-fire
    sched.tick(datetime(2026, 6, 5, 8, 30))      # fires day 2
    assert len(fired) == 2
