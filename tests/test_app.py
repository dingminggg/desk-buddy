# tests/test_app.py
from datetime import datetime

import pytest

from desk_buddy.app import App
from desk_buddy.brain import Brain
from desk_buddy.config import Config
from desk_buddy.llm.base import LLMProvider, LLMError
from desk_buddy.models import Intent, IntentAction, Reminder, ReminderStatus
from desk_buddy.store import ReminderStore


class FakePet:
    def __init__(self):
        self.said = []
        self.state = "idle"

    def say(self, text):
        self.said.append(text)

    def set_state(self, state):
        self.state = state


class FakeNotifier:
    def __init__(self):
        self.toasts = []
        self.sounds = 0

    def toast(self, title, message):
        self.toasts.append((title, message))

    def play_sound(self):
        self.sounds += 1


class StubBrain:
    def __init__(self, intent=None, error=False):
        self._intent = intent
        self._error = error

    def parse(self, text, now):
        if self._error:
            raise LLMError("offline")
        return self._intent


@pytest.fixture
def store():
    s = ReminderStore(":memory:")
    yield s
    s.close()


def _app(store, brain, config=None):
    return App(config or Config(sound_enabled=True), store, brain,
               FakePet(), FakeNotifier())


def test_add_intent_stores_reminder_and_confirms(store):
    brain = StubBrain(Intent(action=IntentAction.ADD,
                             time=datetime(2026, 6, 4, 15, 0), text="开会"))
    app = _app(store, brain)
    app.handle_user_text("明天3点开会")
    active = store.list_active()
    assert len(active) == 1
    assert active[0].text == "开会"
    assert app.pet.said  # spoke a confirmation


def test_add_without_time_asks_for_clarification(store):
    brain = StubBrain(Intent(action=IntentAction.ADD, time=None, text="开会"))
    app = _app(store, brain)
    app.handle_user_text("提醒我开会")
    assert store.list_active() == []
    assert app.pet.said


def test_query_lists_active(store):
    store.add(Reminder(text="买菜", due_at=datetime(2026, 6, 4, 18, 0),
                       created_at=datetime(2026, 6, 3, 10, 0)))
    brain = StubBrain(Intent(action=IntentAction.QUERY))
    app = _app(store, brain)
    app.handle_user_text("我有啥提醒")
    assert "买菜" in app.pet.said[-1]


def test_complete_marks_done(store):
    r = store.add(Reminder(text="跟老板开会", due_at=datetime(2026, 6, 4, 15, 0),
                           created_at=datetime(2026, 6, 3, 10, 0)))
    brain = StubBrain(Intent(action=IntentAction.COMPLETE, text="开会"))
    app = _app(store, brain)
    app.handle_user_text("开会做完了")
    assert store.get(r.id).status == ReminderStatus.DONE


def test_cancel_soft_deletes(store):
    r = store.add(Reminder(text="退订会员", due_at=datetime(2026, 6, 4, 15, 0),
                           created_at=datetime(2026, 6, 3, 10, 0)))
    brain = StubBrain(Intent(action=IntentAction.CANCEL, text="退订"))
    app = _app(store, brain)
    app.handle_user_text("取消退订那个")
    assert store.get(r.id).status == ReminderStatus.CANCELLED


def test_clarify_speaks_question(store):
    brain = StubBrain(Intent(action=IntentAction.CLARIFY, text="今天还是明天？"))
    app = _app(store, brain)
    app.handle_user_text("提醒我那个")
    assert app.pet.said[-1] == "今天还是明天？"


def test_llm_error_saves_draft_and_apologizes(store):
    app = _app(store, StubBrain(error=True))
    app.handle_user_text("明天提醒我退订")
    assert store.list_drafts() == ["明天提醒我退订"]
    assert app.pet.said  # apologized, did not crash


def test_reminder_due_bubbles_toasts_and_sounds(store):
    app = _app(store, StubBrain(), Config(sound_enabled=True))
    r = Reminder(text="喝水", due_at=datetime(2026, 6, 4, 15, 0),
                 created_at=datetime(2026, 6, 3, 10, 0))
    app.handle_reminder_due(r)
    assert app.pet.state == "walking"
    assert app.notifier.toasts and "喝水" in app.notifier.toasts[0][1]
    assert app.notifier.sounds == 1


def test_reminder_due_respects_sound_disabled(store):
    app = _app(store, StubBrain(), Config(sound_enabled=False))
    r = Reminder(text="喝水", due_at=datetime(2026, 6, 4, 15, 0),
                 created_at=datetime(2026, 6, 3, 10, 0))
    app.handle_reminder_due(r)
    assert app.notifier.sounds == 0
