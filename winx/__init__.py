"""WinX - Windows All-in-One Utility.

A PySide6 desktop application that cleans, tunes, repairs and reports on a
Windows installation.  Every mutating operation is expressed declaratively so
that it can be inspected, backed up and undone from a single code path.

The package is import-safe on non-Windows machines: the platform layer flips
the app into *simulation mode*, where commands are echoed instead of executed
and the registry is backed by a JSON file.  That keeps the whole UI testable
(and demoable) on Linux/macOS.
"""

__version__ = "1.0.0"
__app_name__ = "WinX"
__app_id__ = "io.github.vmexe.WinX"
