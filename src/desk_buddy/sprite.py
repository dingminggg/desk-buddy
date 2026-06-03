"""Pixel-art fox sprite: one hand-drawn 16x16 matrix, the other frames derived
by shifting it. Rendered to QPixmap by build_pixmap. No external image assets."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap

GRID = 16

# Character -> color. "." means transparent (not drawn).
PALETTE = {
    "o": QColor("#e8772e"),  # orange body
    "l": QColor("#f6b26b"),  # light orange (inner ears)
    "w": QColor("#ffffff"),  # white muzzle
    "k": QColor("#3a2a1a"),  # dark brown (eyes / nose)
}

# Front-facing chibi fox face. Every row is exactly GRID chars.
FOX = [
    "................",
    "..o........o....",
    "..oo......oo....",
    ".oolo....oloo...",
    ".oooooooooooooo.",
    ".oooooooooooooo.",
    ".oookooooookooo.",
    ".oooooooooooooo.",
    ".oooowwwwwwoooo.",
    ".oooowwkkwwoooo.",
    ".ooooowwwwooooo.",
    "..oooooooooooo..",
    "...oooooooooo...",
    "....oooooooo....",
    ".....oooooo.....",
    "................",
]


def _shift(rows, dx, dy):
    """Return a new GRID×GRID frame shifted by (dx, dy), padding with '.'.
    Content pushed past an edge is clipped."""
    blank = "." * GRID
    out = []
    for y in range(GRID):
        src_y = y - dy
        if not (0 <= src_y < GRID):
            out.append(blank)
            continue
        row = rows[src_y]
        if dx == 0:
            shifted = row
        elif dx > 0:
            shifted = ("." * dx + row)[:GRID]
        else:
            shifted = (row[-dx:] + "." * (-dx))
        out.append(shifted)
    return out


FRAMES = {
    "idle": [FOX, _shift(FOX, 0, 1)],                 # gentle 1px bob
    "walking": [_shift(FOX, -1, 0), _shift(FOX, 1, 0)],  # left/right waddle
}


def build_pixmap(rows, scale):
    """Render a character-grid frame to a QPixmap, one scale×scale block per
    cell. '.' cells stay transparent. Requires a QApplication to exist."""
    pm = QPixmap(GRID * scale, GRID * scale)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            color = PALETTE.get(ch)
            if color is not None:
                painter.fillRect(x * scale, y * scale, scale, scale, color)
    painter.end()
    return pm
