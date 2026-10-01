#!/usr/bin/env python3
"""Render every page to a PNG (used for visual QA in a headless sandbox).

    QT_QPA_PLATFORM=offscreen python tools/screenshot.py [out_dir]
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from winx.app import WinX  # noqa: E402
from winx.core.registry import seed_simulation  # noqa: E402
from winx.core.simdata import seeded_registry  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "screenshots"
PAGES = [
    "dashboard",
    "cleaner",
    "performance",
    "startup",
    "repair",
    "network",
    "privacy",
    "security",
    "apps",
    "disks",
    "drivers",
    "systeminfo",
    "interface",
    "gaming",
    "tools",
    "settings",
]


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    winx = WinX(["winx", "--no-single-instance"])
    seed_simulation(seeded_registry())

    from winx.ui.main_window import MainWindow

    window = MainWindow(winx.ctx)
    winx.window = window
    window.resize(1400, 900)
    window.show()
    pump(winx.app, 0.6)

    for key in PAGES:
        if not window.has_page(key):
            print(f"skip {key}")
            continue
        window._goto(key)          # builds the page on first visit
        pump(winx.app, 0.4)
        page = window.pages[key]
        if hasattr(page, "on_show"):
            page.on_show()
        pump(winx.app, 2.2)
        pixmap = window.grab()
        path = os.path.join(OUT, f"{key}.png")
        pixmap.save(path)
        print(f"wrote {path}")

    window.grab().save(os.path.join(OUT, "_last.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
