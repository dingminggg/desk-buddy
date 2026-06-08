# tests/test_pet_alert.py
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from desk_buddy.pet_widget import PetWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_show_alert_accepts_kind_and_is_visible(qapp):
    pet = PetWidget()
    pet.show_alert("🤖 Claude Code 在等你确认", kind="cc")
    assert not pet._alert.isHidden()
    assert pet._alert_label.text() == "🤖 Claude Code 在等你确认"


def test_hide_alert_hides_and_stops_nag(qapp):
    pet = PetWidget()
    pet.show_alert("⏰ 喝水")
    assert pet._alert_nag_timer.isActive()
    pet.hide_alert()
    assert pet._alert.isHidden()
    assert not pet._alert_nag_timer.isActive()


def test_show_alert_defaults_to_reminder_kind(qapp):
    pet = PetWidget()
    pet.show_alert("⏰ 喝水")  # no kind kwarg -> still works
    assert not pet._alert.isHidden()


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
    # showing the answer must not affect the alert card or its nag timer
    assert not pet._alert.isHidden()
    assert not pet._answer.isHidden()
