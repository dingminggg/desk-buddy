import os

import pytest

# Run Qt without a display/GPU so this works in CI and headless shells.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402

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


def _left_click_at(pet, gx, gy):
    """合成一次左键按下+释放（同一坐标 = 点击，非拖拽）。"""
    press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0),
                        QPointF(gx, gy), Qt.LeftButton, Qt.LeftButton,
                        Qt.NoModifier)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(0, 0),
                          QPointF(gx, gy), Qt.LeftButton, Qt.NoButton,
                          Qt.NoModifier)
    pet.mousePressEvent(press)
    pet.mouseReleaseEvent(release)


def test_left_click_without_drag_emits_clicked(qapp):
    pet = PetWidget()
    pet.move(100, 100)
    received = []
    pet.clicked.connect(lambda: received.append(True))
    _left_click_at(pet, 100, 100)  # 按下与释放同点 -> 视为点击
    assert received == [True]


def _drag(pet, gx, gy, to_x, to_y):
    """合成一次左键拖动（按下 -> 移动超过阈值 -> 释放）。"""
    press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0),
                        QPointF(gx, gy), Qt.LeftButton, Qt.LeftButton,
                        Qt.NoModifier)
    move = QMouseEvent(QEvent.Type.MouseMove, QPointF(0, 0),
                       QPointF(to_x, to_y), Qt.NoButton, Qt.LeftButton,
                       Qt.NoModifier)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(0, 0),
                          QPointF(to_x, to_y), Qt.LeftButton, Qt.NoButton,
                          Qt.NoModifier)
    pet.mousePressEvent(press)
    pet.mouseMoveEvent(move)
    pet.mouseReleaseEvent(release)


def test_drag_does_not_emit_clicked(qapp):
    pet = PetWidget()
    pet.move(100, 100)
    received = []
    pet.clicked.connect(lambda: received.append(True))
    _drag(pet, 100, 100, 200, 200)  # 移动远超阈值 -> 拖动，不应发 clicked
    assert received == []


def test_prompt_input_shows_input_bar(qapp):
    pet = PetWidget()
    pet.prompt_input()
    assert pet._input_bar.isHidden() is False


def test_close_button_hides_input_bar(qapp):
    pet = PetWidget()
    pet.prompt_input()
    assert pet._input_bar.isHidden() is False
    pet._close_btn.click()  # ✕ 关闭按钮只收起输入条，不退出程序
    assert pet._input_bar.isHidden() is True


def test_request_settings_emits_signal(qapp):
    pet = PetWidget()
    received = []
    pet.settings_requested.connect(lambda: received.append(True))
    pet.request_settings()
    assert received == [True]
