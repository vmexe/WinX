"""Command execution.

Two flavours:

``run_sync``
    Blocking helper used from worker threads.  Returns ``(rc, stdout, stderr)``.

``ProcRunner``
    A :class:`QProcess` wrapper that streams output into the UI and can be
    cancelled.  Used by the repair/network pages where a task can run for
    minutes and the user wants live output.

Both honour simulation mode: nothing is executed, a plausible transcript is
emitted instead.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, QProcess, Signal

from . import platform as pf

PS_PREFIX = ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"]


def build_command(cmd) -> list[str]:
    """Turn a :class:`~winx.core.model.Command` into an argv list."""
    from .model import Command

    if isinstance(cmd, Command):
        if cmd.kind == "powershell":
            return [pf.powershell_exe(), *PS_PREFIX, "-Command", cmd.script]
        if cmd.kind == "cmd":
            return [pf.powershell_exe(), *PS_PREFIX, "-Command", " ".join(cmd.args)]
        return list(cmd.args)
    return list(cmd)


def run_sync(argv, timeout: int = 300, kind: str = "raw", cwd: str | None = None):
    """Run ``argv`` and return ``(returncode, stdout, stderr)``."""
    argv = build_command(argv)
    if not pf.IS_WINDOWS or pf.simulating():
        from .simdata import simulate_run

        return simulate_run(argv)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            cwd=cwd,
            creationflags=pf.no_window_flags(),
            startupinfo=pf.startupinfo(),
            shell=False,
        )
        return (proc.returncode, proc.stdout or "", proc.stderr or "")
    except FileNotFoundError as exc:
        return (127, "", f"not found: {exc}")
    except subprocess.TimeoutExpired:
        return (124, "", f"timed out after {timeout}s")
    except OSError as exc:
        return (1, "", str(exc))


def run_script(script: str, timeout: int = 300):
    """Run a PowerShell script and return ``(rc, stdout, stderr)``."""
    if not pf.IS_WINDOWS or pf.simulating():
        from .simdata import simulate_run

        return simulate_run([pf.powershell_exe(), "-Command", script])
    return run_sync(
        [pf.powershell_exe(), *PS_PREFIX, "-Command", script], timeout=timeout
    )


def run_stream(argv, on_line=None, timeout: int = 1800, cancel=None):
    """Run ``argv`` calling ``on_line(str)`` for every output line.

    Thread-safe (plain :mod:`subprocess`), which is what the worker pool needs —
    :class:`QProcess` needs an event loop and therefore stays in the GUI layer.
    """
    argv = build_command(argv)
    if not pf.IS_WINDOWS or pf.simulating():
        import time

        from .simdata import simulate_transcript

        for line in simulate_transcript(argv):
            if cancel is not None and cancel():
                return (-1, "cancelled")
            if on_line:
                on_line(line)
            time.sleep(0.03)
        return (0, "")

    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
            creationflags=pf.no_window_flags(),
            startupinfo=pf.startupinfo(),
        )
    except FileNotFoundError as exc:
        if on_line:
            on_line(f"command not found: {exc}")
        return (127, str(exc))
    except OSError as exc:
        if on_line:
            on_line(f"could not start: {exc}")
        return (1, str(exc))

    import threading

    def _reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            if on_line:
                on_line(line.rstrip("\r\n"))

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return (124, f"timed out after {timeout}s")
    finally:
        thread.join(timeout=5)
    return (int(rc), "")


@dataclass
class Transcript:
    rc: int
    lines: list[str]


class ProcRunner(QObject):
    """Streams a command's output through Qt signals."""

    output = Signal(str)
    finished = Signal(int, str)  # exit code, error text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc: QProcess | None = None
        self._cancelled = False

    # -- control ---------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning

    def cancel(self) -> None:
        self._cancelled = True
        if self._proc is not None:
            self._proc.kill()

    def start(self, argv, timeout: int = 0) -> None:
        argv = build_command(argv)
        self._cancelled = False
        self.output.emit("> " + " ".join(argv))
        if not pf.IS_WINDOWS or pf.simulating():
            from .simdata import simulate_transcript

            for line in simulate_transcript(argv):
                if self._cancelled:
                    break
                self.output.emit(line)
                time.sleep(0.02)
            self.finished.emit(0, "cancelled" if self._cancelled else "")
            return

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyReadStandardOutput.connect(self._on_output)
        proc.finished.connect(self._on_finished)
        if hasattr(proc, "errorOccurred"):
            proc.errorOccurred.connect(self._on_error)
        self._proc = proc
        proc.start(argv[0], argv[1:])

    def _on_output(self) -> None:
        if self._proc is None:
            return
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in data.replace("\r\n", "\n").splitlines():
            if line.strip():
                self.output.emit(line)

    def _on_finished(self, code: int, status) -> None:
        if self._cancelled:
            self.finished.emit(-1, "cancelled by user")
        else:
            self.finished.emit(int(code), "")

    def _on_error(self, err) -> None:
        self.finished.emit(1, f"process error: {err}")
