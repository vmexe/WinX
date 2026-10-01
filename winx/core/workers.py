"""Threadpool helpers so long scans and repairs never block the UI."""

from __future__ import annotations

import inspect
import traceback
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class WorkerSignals(QObject):
    started = Signal()
    finished = Signal()
    result = Signal(object)
    error = Signal(str)
    #: done, total, message — the message is "" for callers that don't send one
    progress = Signal(int, int, str)
    message = Signal(str)            # log line
    data = Signal(object)            # streaming partial results


def _accepts(fn: Callable, name: str) -> bool:
    """True when ``fn`` takes a keyword argument called ``name``.

    ``inspect`` is used rather than poking at ``__code__`` so bound methods,
    functools.partial objects and callables defined in C don't blow up.
    """
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    if name in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


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

    # Signals are not callables: handing ``self.signals.progress`` to a module
    # that calls ``progress(done, total, name)`` raised "native Qt signal
    # instance 'progress' is not callable" and killed the scan. These adapters
    # emit instead, and absorb the two different shapes used in the codebase:
    # engine's ``progress(done, total)`` and the modules' three-argument form.
    def _emit_progress(self, done: int = 0, total: int = 0, message: str = "") -> None:
        if not self._cancelled:
            self._safe_emit(self.signals.progress, int(done), int(total), str(message or ""))

    def _emit_message(self, message: str = "") -> None:
        if not self._cancelled:
            self._safe_emit(self.signals.message, str(message))

    def _safe_emit(self, signal, *args) -> None:
        """Emit unless the receiver (or the whole app) is already gone."""
        try:
            signal.emit(*args)
        except RuntimeError:
            pass

    @Slot()
    def run(self) -> None:
        self._safe_emit(self.signals.started)
        try:
            kwargs = dict(self.kwargs)
            if _accepts(self.fn, "progress"):
                kwargs.setdefault("progress", self._emit_progress)
            if _accepts(self.fn, "emit"):
                kwargs.setdefault("emit", self._emit_message)
            if _accepts(self.fn, "is_cancelled"):
                kwargs.setdefault("is_cancelled", lambda: self._cancelled)
            if _accepts(self.fn, "cancel"):
                kwargs.setdefault("cancel", lambda: self._cancelled)
            result = self.fn(*self.args, **kwargs)
            if not self._cancelled:
                self._safe_emit(self.signals.result, result)
        except Exception as exc:  # noqa: BLE001 - reported to UI
            self._safe_emit(self.signals.error, f"{exc}\n{traceback.format_exc(limit=4)}")
        finally:
            self._safe_emit(self.signals.finished)


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
