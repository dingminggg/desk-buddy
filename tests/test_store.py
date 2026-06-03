from datetime import datetime, timedelta

import pytest

from desk_buddy.models import Reminder, ReminderStatus, RepeatRule
from desk_buddy.store import ReminderStore


@pytest.fixture
def store():
    s = ReminderStore(":memory:")
    yield s
    s.close()


def _mk(text="开会", due=datetime(2026, 6, 4, 15, 0), repeat=RepeatRule.NONE):
    return Reminder(text=text, due_at=due, repeat=repeat,
                    created_at=datetime(2026, 6, 3, 10, 0))


def test_add_assigns_id_and_get_roundtrips(store):
    saved = store.add(_mk())
    assert saved.id is not None
    fetched = store.get(saved.id)
    assert fetched.text == "开会"
    assert fetched.due_at == datetime(2026, 6, 4, 15, 0)
    assert fetched.status == ReminderStatus.PENDING


def test_list_active_only_pending_sorted(store):
    store.add(_mk("晚饭", datetime(2026, 6, 4, 18, 0)))
    early = store.add(_mk("早会", datetime(2026, 6, 4, 9, 0)))
    done = store.add(_mk("已完成事"))
    store.complete(done.id)
    active = store.list_active()
    assert [r.text for r in active] == ["早会", "晚饭"]
    assert early.id == active[0].id


def test_cancel_is_soft_delete(store):
    r = store.add(_mk())
    store.cancel(r.id)
    assert store.get(r.id).status == ReminderStatus.CANCELLED
    assert store.list_active() == []


def test_list_due_returns_overdue_pending_not_notified(store):
    now = datetime(2026, 6, 4, 16, 0)
    due = store.add(_mk("到点了", datetime(2026, 6, 4, 15, 0)))
    store.add(_mk("还没到", datetime(2026, 6, 4, 17, 0)))
    result = store.list_due(now)
    assert [r.id for r in result] == [due.id]


def test_mark_notified_excludes_from_list_due(store):
    now = datetime(2026, 6, 4, 16, 0)
    r = store.add(_mk("到点了", datetime(2026, 6, 4, 15, 0)))
    store.mark_notified(r.id)
    assert store.list_due(now) == []


def test_search_active_substring(store):
    store.add(_mk("跟老板开会"))
    store.add(_mk("买菜"))
    matches = store.search_active("开会")
    assert len(matches) == 1
    assert matches[0].text == "跟老板开会"


def test_advance_daily_moves_past_now_and_resets_notified(store):
    now = datetime(2026, 6, 6, 8, 30)
    r = store.add(_mk("吃药", datetime(2026, 6, 4, 8, 0), repeat=RepeatRule.DAILY))
    store.mark_notified(r.id)
    store.advance_daily(r.id, now)
    updated = store.get(r.id)
    assert updated.due_at == datetime(2026, 6, 7, 8, 0)
    assert updated.notified is False


def test_drafts_saved_and_listed(store):
    store.save_draft("明天提醒我退订")
    assert store.list_drafts() == ["明天提醒我退订"]
