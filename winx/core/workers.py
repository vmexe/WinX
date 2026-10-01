"""Threadpool helpers so long scans and repairs never block the UI."""

from __future__ import annotations

import traceback
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class WorkerSignals(QObject):
    started = Signal()
    finished = Signal()
    result = Signal(object)
    error = Signal(str)
    progress = Signal(int, int)      # done, total
    message = Signal(str)            # log line
    data = Signal(object)            # streaming partial results


class Worker(QRunnable):
    """Run ``fn`` in the global thread pool and forward its output."""

    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @Slot()
    def run(self) -> None:
        self.signals.started.emit()
        try:
            kwargs = dict(self.kwargs)
            if "progress" in self.fn.__code__.co_varnames[: self.fn.__code__.co_argcount]:
                kwargs.setdefault("progress", self.signals.progress)
            if "emit" in self.fn.__code__.co_varnames[: self.fn.__code__.co_argcount]:
                kwargs.setdefault("emit", self.signals.message)
            if "is_cancelled" in self.fn.__code__.co_varnames[: self.fn.__code__.co_argcount]:
                kwargs.setdefault("is_cancelled", lambda: self._cancelled)
            result = self.fn(*self.args, **kwargs)
            if not self._cancelled:
                self.signals.result.emit(result)
        except Exception as exc:  # noqa: BLE001 - reported to UI
            self.signals.error.emit(f"{exc}\n{traceback.format_exc(limit=4)}")
        finally:
            self.signals.finished.emit()


_POOL: QThreadPool | None = None


def pool() -> QThreadPool:
    global _POOL
    if _POOL is None:
        _POOL = QThreadPool.globalInstance()
        _POOL.setMaxThreadCount(max(4, _POOL.maxThreadCount()))
    return _POOL


def submit(fn: Callable, *args, **kwargs) -> Worker:
    """Start ``fn`` in the background and return the worker handle."""
    worker = Worker(fn, *args, **kwargs)
    pool().start(worker)
    return worker


def run_later(fn: Callable, delay_ms: int = 0) -> None:
    from PySide6.QtCore import QTimer

    QTimer.singleShot(delay_ms, fn)
