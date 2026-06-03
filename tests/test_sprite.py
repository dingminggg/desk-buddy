import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from desk_buddy.sprite import FRAMES, GRID, PALETTE, build_pixmap  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_frames_have_idle_and_walking_two_each():
    assert {"idle", "walking"} <= set(FRAMES)
    assert len(FRAMES["idle"]) == 2
    assert len(FRAMES["walking"]) == 2


def test_every_frame_is_16x16_with_valid_chars():
    valid = set(PALETTE) | {"."}
    for frames in FRAMES.values():
        for frame in frames:
            assert len(frame) == GRID, "frame must have GRID rows"
            for row in frame:
                assert len(row) == GRID, f"row not {GRID} wide: {row!r}"
                assert set(row) <= valid, f"bad chars in {row!r}"


def test_build_pixmap_size_and_nonnull(qapp):
    pm = build_pixmap(FRAMES["idle"][0], 6)
    assert pm.isNull() is False
    assert pm.width() == GRID * 6
    assert pm.height() == GRID * 6


def test_transparent_corner_and_body_color(qapp):
    pm = build_pixmap(FRAMES["idle"][0], 6)
    img = pm.toImage()
    # FOX[0] is all '.' -> top-left cell fully transparent
    assert img.pixelColor(3, 3).alpha() == 0
    # FOX[5] == ".oooooooooooooo." -> col 5 is body 'o'; sample its cell center
    c = img.pixelColor(5 * 6 + 3, 5 * 6 + 3)
    o = PALETTE["o"]
    assert (c.red(), c.green(), c.blue()) == (o.red(), o.green(), o.blue())
