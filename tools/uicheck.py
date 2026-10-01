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

    if failures:
        print("\nUI thread blocked for too long:")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("\nok    every UI-thread operation stayed within budget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
