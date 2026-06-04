import os

import pytest

# Run Qt without a display/GPU so this works in CI and headless shells.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402

from desk_buddy.pet_widget import PetWidget, PET_SIZE  # noqa: E402


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


def test_input_bar_follows_pet_on_drag(qapp):
    pet = PetWidget()
    pet.move(100, 100)
    pet.prompt_input()
    _drag(pet, 100, 100, 300, 300)  # drag pet to a new spot
    assert pet.x() == 300 and pet.y() == 300
    # 右对齐：输入框右边缘对齐宠物右边缘，垂直永远在正下方
    ib = pet._input_bar
    assert ib.x() + ib.width() == 300 + PET_SIZE
    assert ib.pos().y() == 300 + PET_SIZE


def test_roaming_paused_while_input_open(qapp):
    pet = PetWidget()
    pet.prompt_input()        # input open
    pet.set_roaming(True)     # user enables roaming...
    assert pet.is_roaming() is False  # ...but it's paused while typing
    pet._close_btn.click()    # close the input bar
    assert pet.is_roaming() is True   # roaming resumes


def test_request_settings_emits_signal(qapp):
    pet = PetWidget()
    received = []
    pet.settings_requested.connect(lambda: received.append(True))
    pet.request_settings()
    assert received == [True]


def test_pet_size_is_128(qapp):
    assert PET_SIZE == 128
    pet = PetWidget()
    assert pet.width() == 128
    assert pet.height() == 128


def test_movie_loaded(qapp):
    pet = PetWidget()
    assert pet._movie.isValid() is True
    assert pet._movie.frameCount() > 0
    assert pet._movie.currentPixmap().isNull() is False


def test_paint_and_set_state_do_not_crash(qapp):
    pet = PetWidget()
    pet.set_state("walking")
    pet.set_state("idle")
    pet.show()
    pet.repaint()  # paints current GIF frame; must not raise


def test_show_alert_visible_and_nag_timer_running(qapp):
    pet = PetWidget()
    pet.show_alert("⏰ 喝水")
    assert pet._alert.isHidden() is False
    assert pet._alert_label.text() == "⏰ 喝水"
    # persistent: a 30s nag timer is running (no auto-hide timer involved)
    assert pet._alert_nag_timer.isActive() is True
    from desk_buddy.pet_widget import ALERT_NAG_MS
    assert pet._alert_nag_timer.interval() == ALERT_NAG_MS


def test_alert_ack_button_dismisses_and_signals(qapp):
    pet = PetWidget()
    received = []
    pet.alert_dismissed.connect(lambda: received.append(True))
    pet.show_alert("⏰ 喝水")
    pet._alert_ack_btn.click()
    assert pet._alert.isHidden() is True
    assert received == [True]
    assert pet._alert_nag_timer.isActive() is False


def test_alert_nag_timer_emits_alert_nag(qapp):
    pet = PetWidget()
    received = []
    pet.alert_nag.connect(lambda: received.append(True))
    pet.show_alert("⏰ 喝水")
    pet._alert_nag_timer.timeout.emit()  # simulate a 30s tick
    assert received == [True]
