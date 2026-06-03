import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desk_buddy.qt_runner import QtRunner  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _pump_until(pred, timeout=2.0):
    start = time.monotonic()
    while not pred() and time.monotonic() - start < timeout:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    return bool(pred())


def test_qt_runner_delivers_result_on_done(qapp):
    runner = QtRunner()
    got = []
    runner.run(lambda: 6 * 7, got.append, got.append)
    assert _pump_until(lambda: got) is True
    assert got == [42]


def test_qt_runner_delivers_exception_on_error(qapp):
    runner = QtRunner()
    errs = []

    def boom():
        raise RuntimeError("boom")

    runner.run(boom, lambda r: errs.append(("unexpected", r)), errs.append)
    assert _pump_until(lambda: errs) is True
    assert isinstance(errs[0], RuntimeError)
