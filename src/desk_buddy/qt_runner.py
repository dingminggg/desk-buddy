"""Background runner for desk-buddy: runs a callable on a Qt worker thread and
delivers the result/exception back on the thread that owns the QtRunner (the
main/UI thread), so the GUI stays responsive during slow calls (e.g. the LLM)."""
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _WorkerSignals(QObject):
    done = Signal(object)
    error = Signal(object)


class _Worker(QRunnable):
    def __init__(self, fn, signals):
        super().__init__()
        self._fn = fn
        self._signals = signals

    def run(self):  # noqa: N802 (Qt naming)
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001
            self._signals.error.emit(exc)
        else:
            self._signals.done.emit(result)


class QtRunner:
    def __init__(self):
        self._pool = QThreadPool.globalInstance()
        self._live = set()  # keep signal objects alive until they fire

    def run(self, fn, on_done, on_error):
        signals = _WorkerSignals()
        self._live.add(signals)

        def _cleanup(*_):
            self._live.discard(signals)

        signals.done.connect(on_done)
        signals.error.connect(on_error)
        signals.done.connect(_cleanup)
        signals.error.connect(_cleanup)
        self._pool.start(_Worker(fn, signals))
