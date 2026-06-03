from datetime import datetime
from desk_buddy.models import (
    Reminder, ReminderStatus, RepeatRule, Intent, IntentAction,
)


def test_reminder_defaults():
    r = Reminder(text="开会", due_at=datetime(2026, 6, 4, 15, 0),
                 created_at=datetime(2026, 6, 3, 10, 0))
    assert r.id is None
    assert r.status == ReminderStatus.PENDING
    assert r.repeat == RepeatRule.NONE
    assert r.notified is False


def test_intent_parses_iso_time():
    intent = Intent(action="add", time="2026-06-04T15:00:00", text="开会")
    assert intent.action == IntentAction.ADD
    assert intent.time == datetime(2026, 6, 4, 15, 0)
    assert intent.text == "开会"


def test_intent_time_optional():
    intent = Intent(action="query")
    assert intent.time is None
    assert intent.text is None
