"""Console encoding safety.

WinX's log lines and reports use typographic characters (→ • ° “ ”).  On a
Windows console the default encoding is still a legacy codepage (cp1252,
cp437…), so printing them raises ``UnicodeEncodeError`` and kills the
process — the classic "it works on my machine, it crashes in cmd.exe" bug.

``ensure_utf8_console()`` is therefore called before anything is printed.
It is deliberately defensive: if the stream cannot be reconfigured the app
must carry on regardless (it is a GUI program; the console is a bonus).
"""

from __future__ import annotations

import io
import sys


def ensure_utf8_console() -> bool:
    """Force UTF-8 (with replacement) on stdout/stderr.  Never raises."""
    ok = False
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            # Windowed (pythonw / PyInstaller --windowed) builds have no
            # console at all; print() is then a no-op, which is fine.
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
                ok = True
                continue
            except Exception:
                pass
        # Fall back to wrapping the underlying buffer.
        try:
            buffer = getattr(stream, "buffer", None)
            if buffer is None:
                continue
            wrapper = io.TextIOWrapper(
                buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            )
            setattr(sys, name, wrapper)
            ok = True
        except Exception:
            continue
    return ok
