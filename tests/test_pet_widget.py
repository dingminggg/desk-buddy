import os

import pytest

# Run Qt without a display/GPU so this works in CI and headless shells.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from desk_buddy.pet_widget import PetWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_widget_constructs_and_speaks(qapp):
    pet = PetWidget()
    pet.show()
    pet.say("你好")           # must not raise
    pet.set_state("walking")  # must not raise
    pet.set_state("idle")
    assert pet.bubble_text() == "你好"


def test_set_roaming_toggles_timer(qapp):
    pet = PetWidget()
    pet.set_roaming(True)
    assert pet.is_roaming() is True
    pet.set_roaming(False)
    assert pet.is_roaming() is False


def test_user_said_signal_emits(qapp):
    pet = PetWidget()
    received = []
    pet.user_said.connect(received.append)
    pet.submit_input("提醒我喝水")  # internal hook the input bar calls on Enter
    assert received == ["提醒我喝水"]


def test_roam_tick_moves_without_error(qapp):
    pet = PetWidget()
    pet.set_roaming(True)
    pet._roam_tick()  # one autonomous step; must not raise
