import random

from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QColor, QMovie, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

PET_SIZE = 128
ROAM_INTERVAL_MS = 4000
ROAM_STEP = 8
BUBBLE_TIMEOUT_MS = 6000
DRAG_THRESHOLD = 4  # px of movement before a press counts as a drag, not a click
ALERT_NAG_MS = 30000  # re-sound an unacknowledged reminder every 30s
ALERT_GAP_FUDGE = 34  # px: cancel the alert window's margin + frog head padding so it hugs the pet

GIF_PATH = Path(__file__).parent / "assets" / "frog.gif"


class PetWidget(QWidget):
    """Frameless, translucent, always-on-top desktop pet.

    Public API used by the App controller:
      - say(text): show a speech bubble above the pet
      - set_state(state): 'idle' | 'walking' (changes appearance)
      - set_roaming(enabled): toggle autonomous wandering
      - prompt_input(): show the click-to-type input bar
      - signal user_said(str): emitted when the user submits the input bar
      - signal clicked(): emitted on a left-click that isn't a drag
      - signal settings_requested(): emitted when the user picks 设置 in the
        right-click menu
      - signal quit_requested(): emitted when the user picks 退出 in the
        right-click menu
    """

    user_said = Signal(str)
    clicked = Signal()
    settings_requested = Signal()
    quit_requested = Signal()
    alert_dismissed = Signal()
    alert_nag = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(PET_SIZE, PET_SIZE)

        self._state = "idle"
        self._drag_offset = None
        self._press_global = None
        self._moved = False
        self._roam_enabled = False

        # Animated GIF body, scaled to the pet size.
        self._movie = QMovie(str(GIF_PATH))
        self._movie.setScaledSize(QSize(PET_SIZE, PET_SIZE))
        self._movie.frameChanged.connect(self.update)
        if self._movie.isValid():
            self._movie.jumpToFrame(0)  # ensure currentPixmap is valid at once
            self._movie.start()

        # Speech bubble (separate frameless window so it can overflow the pet).
        self._bubble = QLabel(None, Qt.ToolTip)
        self._bubble.setStyleSheet(
            "background:#fffbe6; border:1px solid #d9c97a; border-radius:8px;"
            " padding:6px; color:#333;")
        self._bubble.setWordWrap(True)
        self._bubble.hide()
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self._bubble.hide)

        # Click-to-type input bar: a small frameless popup. A translucent
        # top-level window holds an inner white "card" (rounded + soft shadow)
        # with just the text field and a ✕ close button.
        self._input_bar = QWidget(
            None,
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint,
        )
        self._input_bar.setAttribute(Qt.WA_TranslucentBackground)
        self._input_bar.setStyleSheet(
            "#card { background:#ffffff; border:1px solid #ece4d3;"
            " border-radius:12px; }"
            " QLineEdit { border:none; background:transparent; color:#3a3a3a;"
            " font-size:13px; padding:4px 2px; }"
            " QLineEdit:focus { outline:none; }"
            " #closeBtn { border:none; background:transparent; color:#b7ae98;"
            " font-size:13px; border-radius:11px; }"
            " #closeBtn:hover { background:#f3ecda; color:#e2685f; }")

        outer = QVBoxLayout(self._input_bar)
        outer.setContentsMargins(14, 12, 14, 14)  # room for the drop shadow

        card = QFrame()
        card.setObjectName("card")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(12, 6, 8, 6)
        card_layout.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText("跟我说点啥…")
        self._input.setFixedWidth(210)
        self._input.returnPressed.connect(self._on_input_return)
        self._close_btn = QPushButton("✕")
        self._close_btn.setObjectName("closeBtn")
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.clicked.connect(self._hide_input)
        card_layout.addWidget(self._input)
        card_layout.addWidget(self._close_btn)
        outer.addWidget(card)

        shadow = QGraphicsDropShadowEffect(self._input_bar)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(3)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)

        self._input_bar.hide()

        # Persistent reminder alert: a card with the reminder text and a
        # "知道了" button. Does NOT auto-hide; re-sounds every 30s until closed.
        self._alert = QWidget(
            None,
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint,
        )
        self._alert.setAttribute(Qt.WA_TranslucentBackground)
        self._alert.setStyleSheet(
            "#alertCard { background:#ffffff; border:1px solid #ece4d3;"
            " border-radius:12px; }"
            " QLabel { color:#3a3a3a; font-size:13px; }"
            " #ackBtn { border:none; background:#7ec488; color:#ffffff;"
            " border-radius:8px; padding:4px 12px; font-size:12px; }"
            " #ackBtn:hover { background:#6bb377; }")
        alert_outer = QVBoxLayout(self._alert)
        alert_outer.setContentsMargins(14, 12, 14, 14)
        alert_card = QFrame()
        alert_card.setObjectName("alertCard")
        alert_box = QVBoxLayout(alert_card)
        alert_box.setContentsMargins(12, 10, 12, 10)
        alert_box.setSpacing(8)
        self._alert_label = QLabel()
        self._alert_label.setWordWrap(True)
        self._alert_label.setMaximumWidth(220)
        self._alert_ack_btn = QPushButton("知道了")
        self._alert_ack_btn.setObjectName("ackBtn")
        self._alert_ack_btn.setCursor(Qt.PointingHandCursor)
        self._alert_ack_btn.clicked.connect(self._dismiss_alert)
        alert_box.addWidget(self._alert_label)
        alert_box.addWidget(self._alert_ack_btn, alignment=Qt.AlignRight)
        alert_outer.addWidget(alert_card)
        alert_shadow = QGraphicsDropShadowEffect(self._alert)
        alert_shadow.setBlurRadius(20)
        alert_shadow.setXOffset(0)
        alert_shadow.setYOffset(3)
        alert_shadow.setColor(QColor(0, 0, 0, 80))
        alert_card.setGraphicsEffect(alert_shadow)
        self._alert.hide()

        # Re-sound timer for an unacknowledged reminder (no auto-hide).
        self._alert_nag_timer = QTimer(self)
        self._alert_nag_timer.setInterval(ALERT_NAG_MS)
        self._alert_nag_timer.timeout.connect(self.alert_nag.emit)

        # Roaming.
        self._roam_timer = QTimer(self)
        self._roam_timer.timeout.connect(self._roam_tick)


    # --- public API -----------------------------------------------------
    def say(self, text: str) -> None:
        self._bubble.setText(text)
        self._bubble.adjustSize()
        self._position_bubble()
        self._bubble.show()
        self._bubble_timer.start(BUBBLE_TIMEOUT_MS)

    def bubble_text(self) -> str:
        return self._bubble.text()

    def set_state(self, state: str) -> None:
        # One animation for all states; keep the attribute for callers/future use.
        self._state = state

    def set_roaming(self, enabled: bool) -> None:
        self._roam_enabled = enabled
        self._apply_roaming()

    def _apply_roaming(self) -> None:
        # Roam only when enabled AND the input bar is closed — wandering while
        # the user types would drag the input away and ruin the experience.
        if self._roam_enabled and self._input_bar.isHidden():
            self._roam_timer.start(ROAM_INTERVAL_MS)
        else:
            self._roam_timer.stop()

    def is_roaming(self) -> bool:
        return self._roam_timer.isActive()

    def submit_input(self, text: str) -> None:
        """Programmatic equivalent of pressing Enter in the input bar."""
        text = text.strip()
        if text:
            self.user_said.emit(text)

    # --- painting -------------------------------------------------------
    def paintEvent(self, event):  # noqa: N802 (Qt naming)
        if not self._movie.isValid():
            return
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._movie.currentPixmap())

    # --- mouse: drag + click-to-open-input ------------------------------
    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._drag_offset = self._press_global - self.pos()
            self._moved = False
        elif event.button() == Qt.RightButton:
            self._show_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_offset is not None:
            current = event.globalPosition().toPoint()
            if (current - self._press_global).manhattanLength() > DRAG_THRESHOLD:
                self._moved = True
            self.move(current - self._drag_offset)
            self._position_bubble()
            if not self._input_bar.isHidden():
                self._position_input()
            if not self._alert.isHidden():
                self._position_alert()

    def mouseReleaseEvent(self, event):  # noqa: N802
        was_click = self._drag_offset is not None and not self._moved
        self._drag_offset = None
        if was_click:  # a click, not a drag -> let the controller decide
            self.clicked.emit()

    # --- public API (cont.) ---------------------------------------------
    def prompt_input(self) -> None:
        """Show the click-to-type input bar just below the pet."""
        self._position_input()
        self._input.clear()
        self._input_bar.show()
        self._input.setFocus()
        self._apply_roaming()  # pause roaming while the user types

    def show_alert(self, text: str, kind: str = "reminder") -> None:
        """Show a persistent alert card; stays until dismissed.

        kind: "reminder" (定点提醒) 或 "cc" (Claude Code 等确认)。当前用于
        归属判定，预留样式区分；图标已包含在调用方传入的 text 里。
        """
        self._alert_kind = kind
        self._alert_label.setText(text)
        self._alert.adjustSize()
        self._position_alert()
        self._alert.show()
        self._alert_nag_timer.start()

    def hide_alert(self) -> None:
        """Programmatically dismiss the alert card (no alert_dismissed signal)."""
        self._alert_nag_timer.stop()
        self._alert.hide()

    def request_settings(self) -> None:
        """Ask the controller to open the settings dialog."""
        self.settings_requested.emit()

    # --- internals ------------------------------------------------------
    def _show_menu(self, global_pos) -> None:
        menu = QMenu(self)
        menu.addAction("设置").triggered.connect(self.request_settings)
        menu.addAction("退出").triggered.connect(self.quit_requested.emit)
        menu.exec(global_pos)

    def _hide_input(self) -> None:
        self._input_bar.hide()
        self._apply_roaming()  # resume roaming if it was enabled

    def _dismiss_alert(self) -> None:
        self._alert_nag_timer.stop()
        self._alert.hide()
        self.alert_dismissed.emit()

    def _position_alert(self) -> None:
        # Centered over the pet and tucked right against its head so the alert
        # reads as attached to the frog. ALERT_GAP_FUDGE cancels the alert
        # window's transparent margin (+ a few px of overlap).
        pos = self.pos()
        x = pos.x() + PET_SIZE // 2 - self._alert.width() // 2
        y = pos.y() - self._alert.height() + ALERT_GAP_FUDGE
        if y < 0:  # no room above -> tuck it against the pet's bottom instead
            y = pos.y() + PET_SIZE - ALERT_GAP_FUDGE
        self._alert.move(x, y)

    def _on_input_return(self) -> None:
        text = self._input.text().strip()
        self._input_bar.hide()
        self._apply_roaming()  # resume roaming if it was enabled
        if text:
            self.user_said.emit(text)

    def _position_input(self) -> None:
        pos = self.pos()
        self._input_bar.move(pos.x(), pos.y() + PET_SIZE)

    def _position_bubble(self) -> None:
        pos = self.pos()
        self._bubble.move(pos.x(), max(0, pos.y() - self._bubble.height()))

    def _roam_tick(self) -> None:
        screen = self.screen().availableGeometry() if self.screen() else None
        dx = random.randint(-ROAM_STEP, ROAM_STEP)
        dy = random.randint(-ROAM_STEP, ROAM_STEP)
        new_x = self.x() + dx
        new_y = self.y() + dy
        if screen is not None:
            new_x = min(max(new_x, screen.left()), screen.right() - PET_SIZE)
            new_y = min(max(new_y, screen.top()), screen.bottom() - PET_SIZE)
        self.move(new_x, new_y)
        self._position_bubble()
