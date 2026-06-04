# tests/test_app.py
from datetime import datetime

import pytest

from desk_buddy.app import App, CC_ALERT_TEXT
from desk_buddy.brain import Brain
from desk_buddy.config import Config
from desk_buddy.llm.base import LLMProvider, LLMError
from desk_buddy.models import Intent, IntentAction, Reminder, ReminderStatus
from desk_buddy.store import ReminderStore


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


class FakeNotifier:
    def __init__(self):
        self.sounds = 0
        self.sound_files = []

    def play_sound(self, sound_file=""):
        self.sounds += 1
        self.sound_files.append(sound_file)


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


def _mk(text, m=0):
    return Reminder(text=text, due_at=datetime(2026, 6, 4, 15, m),
                    created_at=datetime(2026, 6, 3, 10, 0))


def test_reminder_due_presents_persistent_alert(store):
    app = _app(store, StubBrain(), Config(sound_enabled=True))
    app.handle_reminder_due(_mk("喝水"))
    assert app.pet.alerts == ["⏰ 喝水"]
    assert app.notifier.sounds == 1
    assert app._alert_active is True


def test_reminder_due_respects_sound_disabled(store):
    app = _app(store, StubBrain(), Config(sound_enabled=False))
    app.handle_reminder_due(_mk("喝水"))
    assert app.pet.alerts == ["⏰ 喝水"]   # alert still shows
    assert app.notifier.sounds == 0


def test_only_one_alert_shown_at_a_time(store):
    app = _app(store, StubBrain(), Config(sound_enabled=True))
    app.handle_reminder_due(_mk("A", 0))
    app.handle_reminder_due(_mk("B", 1))
    app.handle_reminder_due(_mk("C", 2))
    assert app.pet.alerts == ["⏰ A"]  # B,C still queued
    assert len(app._due_queue) == 2


def test_dismiss_shows_next_until_empty(store):
    app = _app(store, StubBrain(), Config(sound_enabled=True))
    for t in ("A", "B", "C"):
        app.handle_reminder_due(_mk(t))
    app.on_alert_dismissed()  # -> B
    app.on_alert_dismissed()  # -> C
    assert app.pet.alerts == ["⏰ A", "⏰ B", "⏰ C"]
    app.on_alert_dismissed()  # queue empty
    assert app._alert_active is False
    assert app.pet.alerts == ["⏰ A", "⏰ B", "⏰ C"]  # nothing new


def test_nag_plays_sound_only(store):
    app = _app(store, StubBrain(), Config(sound_enabled=True))
    app.handle_reminder_due(_mk("喝水"))
    sounds_before = app.notifier.sounds
    app.on_alert_nag()
    assert app.notifier.sounds == sounds_before + 1
    assert app.pet.alerts == ["⏰ 喝水"]  # nag doesn't change the queue/alert
    assert app._alert_active is True


def test_nag_respects_sound_disabled(store):
    app = _app(store, StubBrain(), Config(sound_enabled=False))
    app.handle_reminder_due(_mk("喝水"))
    app.on_alert_nag()
    assert app.notifier.sounds == 0


class FakeRunner:
    """Captures the submitted job so the test can complete it manually."""

    def __init__(self):
        self.calls = 0
        self.fn = None
        self.on_done = None
        self.on_error = None

    def run(self, fn, on_done, on_error):
        self.calls += 1
        self.fn = fn
        self.on_done = on_done
        self.on_error = on_error


def test_thinking_bubble_then_reply(store):
    runner = FakeRunner()
    app = App(Config(sound_enabled=True), store,
              StubBrain(Intent(action=IntentAction.QUERY)),
              FakePet(), FakeNotifier(), runner=runner)
    app.handle_user_text("我有啥提醒")
    assert app.pet.said == ["让我想想…"]   # nothing dispatched yet
    assert runner.calls == 1
    runner.on_done(Intent(action=IntentAction.QUERY))  # API "returns"
    assert app.pet.said[-1] != "让我想想…"  # replied (query result)
    assert app._busy is False


def test_busy_ignores_second_message(store):
    runner = FakeRunner()
    app = App(Config(), store,
              StubBrain(Intent(action=IntentAction.QUERY)),
              FakePet(), FakeNotifier(), runner=runner)
    app.handle_user_text("第一句")
    app.handle_user_text("第二句")          # while first is in-flight
    assert runner.calls == 1                # second was ignored
    assert app.pet.said[-1] == "等我把上一句想完～"
    runner.on_done(Intent(action=IntentAction.QUERY))
    assert app._busy is False
    app.handle_user_text("第三句")          # free again
    assert runner.calls == 2


def test_async_llm_error_saves_draft(store):
    runner = FakeRunner()
    app = App(Config(), store, StubBrain(), FakePet(), FakeNotifier(),
              runner=runner)
    app.handle_user_text("明天提醒我退订")
    runner.on_error(LLMError("offline"))
    assert store.list_drafts() == ["明天提醒我退订"]
    assert app._busy is False


def test_async_generic_error_no_draft(store):
    runner = FakeRunner()
    app = App(Config(), store, StubBrain(), FakePet(), FakeNotifier(),
              runner=runner)
    app.handle_user_text("xxx")
    runner.on_error(ValueError("boom"))
    assert store.list_drafts() == []
    assert app._busy is False
    assert app.pet.said[-1] == "出了点小问题，稍后再说～"


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
    assert app.pet.alerts.count(CC_ALERT_TEXT) == 1


def test_configured_sound_file_is_passed_to_notifier(store):
    app = _app(store, StubBrain(),
               Config(sound_enabled=True, sound_file="C:/snd/guagua.mp3"))
    app.handle_reminder_due(_mk("喝水"))
    assert app.notifier.sound_files[-1] == "C:/snd/guagua.mp3"
