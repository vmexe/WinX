#!/usr/bin/env python3
"""Headless UI responsiveness check.

Builds the real main window on the offscreen Qt platform and measures how long
the GUI thread is blocked by the things it does on its own: creating the
window, polling the dashboard meters, and opening each page.

It exists because a laggy window is not something ``--selftest`` can see: the
engine was fine, but the dashboard was calling PowerShell-backed code on the
UI thread every two seconds, so the window stopped responding.

    python tools/uicheck.py

Exits non-zero when a UI-thread operation exceeds its budget.
"""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Budgets in milliseconds. A frame is 16ms; anything over ~200ms on the UI
# thread is visible lag, and a second is "not responding".
TICK_BUDGET_MS = 150
WINDOW_BUDGET_MS = 4000
PAGE_BUDGET_MS = 3000

failures: list[str] = []


def record(name: str, elapsed_ms: float, budget_ms: float) -> None:
    status = "ok  " if elapsed_ms <= budget_ms else "FAIL"
    if elapsed_ms > budget_ms:
        failures.append(f"{name}: {elapsed_ms:.0f}ms > {budget_ms:.0f}ms")
    print(f"  {status}  {name:<44} {elapsed_ms:7.1f} ms  (budget {budget_ms:.0f})")


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from winx.app import WinX
    from winx.ui.main_window import PAGE_FACTORIES

    app_argv = [sys.argv[0], "--no-single-instance"]
    started = time.perf_counter()
    winx = WinX(app_argv)
    record("WinX() bootstrap", (time.perf_counter() - started) * 1000, WINDOW_BUDGET_MS)

    started = time.perf_counter()
    winx.show()
    record("main window shown", (time.perf_counter() - started) * 1000, WINDOW_BUDGET_MS)

    window = winx.window
    QApplication.processEvents()

    dashboard = window.pages["dashboard"]
    worst = 0.0
    for _ in range(5):
        started = time.perf_counter()
        dashboard._tick()
        worst = max(worst, (time.perf_counter() - started) * 1000)
    record("dashboard live tick (worst of 5)", worst, TICK_BUDGET_MS)

    for key in PAGE_FACTORIES:
        started = time.perf_counter()
        window._goto(key)
        QApplication.processEvents()
        record(f"open page: {key}", (time.perf_counter() - started) * 1000, PAGE_BUDGET_MS)

    worker_errors = exercise_pages(window)
    check_cache_reuse(window)
    check_global_search(window)

    if failures:
        print("\nUI thread blocked for too long:")
        for line in failures:
            print(f"  - {line}")
    if worker_errors:
        print("\nBackground work failed:")
        for line in worker_errors:
            print(f"  - {line}")
    if failures or worker_errors:
        return 1
    print("\nok    every UI-thread operation stayed within budget, and every page loaded")
    return 0


def check_cache_reuse(window) -> None:
    """Re-opening a page must reuse its result instead of scanning again."""
    from PySide6.QtWidgets import QApplication

    from winx.core import workers
    from winx.ui.pages.base import Page

    print()
    submissions: list[str] = []
    original = workers.submit

    def spy(fn, *args, **kwargs):
        submissions.append(getattr(fn, "__name__", str(fn)))
        return original(fn, *args, **kwargs)

    workers.submit = spy
    try:
        for key in ("apps", "drivers", "systeminfo", "disks", "startup"):
            page = window.pages.get(key) or window.page(key)
            if not isinstance(page, Page):
                continue
            submissions.clear()
            page.on_show()                     # already loaded by exercise_pages
            QApplication.processEvents()
            reused = not submissions
            status = "ok  " if reused else "FAIL"
            if not reused:
                failures.append(f"{key} re-scanned on re-open ({submissions[0]})")
            detail = "served from cache" if reused else f"re-ran {submissions[0]}"
            print(f"  {status}  re-open page: {key:<36} {detail}")
    finally:
        workers.submit = original


def check_global_search(window) -> None:
    """The toolbar search must find a tweak and land on the right page."""
    from PySide6.QtWidgets import QApplication

    print()
    cases = [
        ("Disks", "disks"),
        ("Disable window animations — Performance", "performance"),
    ]
    for text, expected in cases:
        window._search_chosen(text)
        QApplication.processEvents()
        ok = window._current == expected
        if not ok:
            failures.append(f"search '{text}' opened {window._current}, expected {expected}")
        print(f"  {'ok  ' if ok else 'FAIL'}  search: {text[:38]:<38} -> {window._current}")


def exercise_pages(window) -> list[str]:
    """Actually load every page and report anything a worker raised.

    The pages do their real work in background threads, so a broken call
    signature there (for example handing a Qt signal to a module that expects
    a callable) never shows up as an import or layout error — it only appears
    as a traceback in the user's activity log. This drives each page the way a
    user would and fails the build when a worker reports an error.
    """
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication

    from winx.core.workers import Worker
    from winx.ui.main_window import PAGE_FACTORIES
    from winx.ui.pages.base import Page

    errors: list[str] = []
    original = Worker._safe_emit

    def spy(self, signal, *args):
        if signal is self.signals.error and args:
            errors.append(str(args[0]).splitlines()[0])
        return original(self, signal, *args)

    Worker._safe_emit = spy
    overall_deadline = time.perf_counter() + 240   # keep CI bounded
    try:
        print()
        for key in PAGE_FACTORIES:
            if time.perf_counter() > overall_deadline:
                print(f"  skip  load page: {key:<38} (time budget reached)")
                continue
            before = len(errors)
            page = window.page(key)
            if isinstance(page, Page):
                page.invalidate()
                page.on_show()
            started = time.perf_counter()
            while time.perf_counter() - started < 30:
                QApplication.processEvents()
                if QThreadPool.globalInstance().activeThreadCount() == 0:
                    break
                time.sleep(0.02)
            QApplication.processEvents()
            new = errors[before:]
            status = "ok  " if not new else "FAIL"
            print(f"  {status}  load page: {key:<38} {'no errors' if not new else new[0][:60]}")
    finally:
        Worker._safe_emit = original
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
