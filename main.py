#!/usr/bin/env python3
"""WinX — Windows all-in-one utility.

    python main.py                 run the GUI
    python main.py --simulate      dry-run: never change anything
    python main.py --selftest      exercise the engine without a GUI
    python main.py --version       print the version
"""

from __future__ import annotations

import sys

from winx.core.console import ensure_utf8_console


def main() -> int:
    # Windows consoles default to a legacy codepage; WinX prints → • ° “ ”.
    ensure_utf8_console()

    if "--selftest" in sys.argv:
        from winx.selftest import main as selftest_main

        return selftest_main()

    from winx.app import run

    return run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
