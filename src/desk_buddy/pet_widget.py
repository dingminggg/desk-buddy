import random

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QWidget,
)

PET_SIZE = 96
ROAM_INTERVAL_MS = 4000
ROAM_STEP = 8
BUBBLE_TIMEOUT_MS = 6000
DRAG_THRESHOLD = 4  # px of movement before a press counts as a drag, not a click

_STATE_COLORS = {
    "idle": QColor(120, 180, 255),
    "walking": QColor(120, 220, 160),
}


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

        # Click-to-type input bar: a small frameless popup holding just the
        # text field and a ✕ close button.
        self._input_bar = QWidget(
            None,
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint,
        )
        self._input_bar.setStyleSheet(
            "QWidget { background:#ffffff; border:1px solid #d9c97a;"
            " border-radius:8px; }"
            " QPushButton { border:none; color:#888; font-weight:bold; }"
            " QPushButton:hover { color:#e05a5a; }")
        bar_layout = QHBoxLayout(self._input_bar)
        bar_layout.setContentsMargins(8, 6, 6, 6)
        bar_layout.setSpacing(4)
        self._input = QLineEdit()
        self._input.setPlaceholderText("跟我说点啥…")
        self._input.setFixedWidth(200)
        self._input.returnPressed.connect(self._on_input_return)
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedWidth(22)
        self._close_btn.clicked.connect(self._hide_input)
        bar_layout.addWidget(self._input)
        bar_layout.addWidget(self._close_btn)
        self._input_bar.hide()

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
        self._state = state
        self.update()

    def set_roaming(self, enabled: bool) -> None:
        if enabled:
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = _STATE_COLORS.get(self._state, _STATE_COLORS["idle"])
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(8, 8, PET_SIZE - 16, PET_SIZE - 16)

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

    def mouseReleaseEvent(self, event):  # noqa: N802
        was_click = self._drag_offset is not None and not self._moved
        self._drag_offset = None
        if was_click:  # a click, not a drag -> let the controller decide
            self.clicked.emit()

    # --- public API (cont.) ---------------------------------------------
    def prompt_input(self) -> None:
        """Show the click-to-type input bar just below the pet."""
        pos = self.pos()
        self._input_bar.move(pos.x(), pos.y() + PET_SIZE)
        self._input.clear()
        self._input_bar.show()
        self._input.setFocus()

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

    def _on_input_return(self) -> None:
        text = self._input.text().strip()
        self._input_bar.hide()
        if text:
            self.user_said.emit(text)

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
