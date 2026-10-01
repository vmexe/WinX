"""The change engine: inspect, apply, revert.

Nothing here knows about widgets — it just turns :class:`TweakDef` /
:class:`ActionDef` objects into reports, so the same code serves the GUI,
a CLI, and the self-test harness.
"""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

from PySide6.QtCore import QObject, Signal

from . import platform as pf
from . import registry, services
from .backup import BackupManager, BackupSession
from .model import (
    DELETE,
    ActionDef,
    Command,
    RegSet,
    Report,
    ServiceSet,
    TweakDef,
)
from .runner import run_stream, run_sync

# tweak states
ON = "on"
OFF = "off"
PARTIAL = "partial"
UNKNOWN = "unknown"


def values_match(actual, expected) -> bool:
    """Loose comparison that tolerates '1' vs 1 and lists vs tuples."""
    if actual is None:
        return False
    if isinstance(expected, (list, tuple)):
        return list(actual) == list(expected)
    if isinstance(actual, bool) or isinstance(expected, bool):
        return bool(actual) == bool(expected)
    if isinstance(actual, int) and isinstance(expected, int):
        return actual == expected
    try:
        if isinstance(expected, int) and isinstance(actual, str):
            return int(actual, 0) == expected
        if isinstance(actual, int) and isinstance(expected, str):
            return actual == int(expected, 0)
    except (ValueError, TypeError):
        pass
    return str(actual).strip() == str(expected).strip()


class Engine(QObject):
    """Applies declarative changes and reports on them."""

    message = Signal(str)
    progress = Signal(int, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.backups = BackupManager()

    # ------------------------------------------------------------------
    # inspection
    # ------------------------------------------------------------------
    def tweak_state(self, tweak: TweakDef) -> str:
        if not tweak.is_checkable:
            return UNKNOWN
        checks: list[bool] = []
        for reg in tweak.sets:
            exists, value, _ = registry.get_value(reg.hive, reg.path, reg.name)
            checks.append(exists and values_match(value, reg.value))
        for svc in tweak.services:
            info = services.query(svc.name)
            if not info.get("exists"):
                checks.append(False)
                continue
            if svc.start:
                checks.append(
                    services.normalise_start(info.get("start", "")) == services.normalise_start(svc.start)
                )
            if svc.running is not None:
                checks.append((info.get("state", "").upper() == "RUNNING") == bool(svc.running))
        if not checks:
            return UNKNOWN
        if all(checks):
            return ON
        if not any(checks):
            return OFF
        return PARTIAL

    def states(self, tweaks: Iterable[TweakDef]) -> dict[str, str]:
        return {t.key: self.tweak_state(t) for t in tweaks}

    # ------------------------------------------------------------------
    # preview
    # ------------------------------------------------------------------
    def preview_tweak(self, tweak: TweakDef, enable: bool = True) -> list[str]:
        lines: list[str] = []
        for reg in tweak.sets:
            if enable:
                vtype = reg.vtype if reg.vtype != "auto" else registry.infer_type(reg.value)
                lines.append(f"set {reg.location} = {registry.normalise(reg.value)} ({vtype})")
            elif reg.off_value is DELETE:
                lines.append(f"delete {reg.location}")
            else:
                lines.append(f"set {reg.location} = {registry.normalise(reg.off_value)}")
        for svc in tweak.services:
            if enable:
                if svc.start:
                    lines.append(f"service {svc.name}: start type → {svc.start}")
                if svc.running is True:
                    lines.append(f"service {svc.name}: start")
                elif svc.running is False:
                    lines.append(f"service {svc.name}: stop")
            else:
                target = svc.off_start or ("demand" if svc.start == "disabled" else "auto")
                lines.append(f"service {svc.name}: start type → {target}")
                if svc.running is False:
                    lines.append(f"service {svc.name}: start")
        for cmd in (tweak.apply_cmds if enable else tweak.revert_cmds):
            lines.append("run: " + cmd.display())
        return lines

    def preview_action(self, action: ActionDef) -> list[str]:
        return [step.display() for step in action.steps] or [action.description]

    # ------------------------------------------------------------------
    # tweaks
    # ------------------------------------------------------------------
    def apply_tweaks(
        self,
        items: Sequence[tuple[TweakDef, bool]],
        backup: bool = True,
        restore_point: bool = False,
        emit: Callable[[str], None] | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> Report:
        label = (
            items[0][0].name if len(items) == 1 else f"{len(items)} changes"
        )
        report = Report(label)
        report.simulated = pf.simulating()
        emit = emit or (lambda _msg: None)
        progress = progress or (lambda _d, _t: None)

        total = sum(
            len(t.sets) + len(t.services) + len(t.apply_cmds if on else t.revert_cmds)
            for t, on in items
        )
        total = max(total, 1)
        done = 0

        session = BackupSession(label, with_restore_point=restore_point)
        if restore_point:
            ok, detail = session.create_restore_point()
            report.add("system restore point", ok, detail)
            emit(("Restore point created" if ok else "Restore point skipped") + f" {detail}".rstrip())

        applied_any = False
        need_explorer_restart = False

        for tweak, enable in items:
            emit(f"{'Applying' if enable else 'Reverting'}: {tweak.name}")
            if tweak.admin and pf.IS_WINDOWS and not pf.is_admin():
                report.add(tweak.name, False, "requires administrator rights")
                emit("  ! needs administrator — skipped")
                continue

            # registry
            for reg in tweak.sets:
                done += 1
                progress(done, total)
                if backup:
                    session.capture_registry(reg)
                ok, err = self._write_reg(reg, enable)
                report.add(f"{reg.location} → {self._target_text(reg, enable)}", ok, err)
                emit(("  ok  " if ok else "  ERR ") + reg.location + (f" ({err})" if err else ""))
                applied_any = applied_any or ok

            # services
            for svc in tweak.services:
                done += 1
                progress(done, total)
                if backup:
                    session.capture_service(svc)
                ok, err = self._write_service(svc, enable)
                target = svc.start if enable else (svc.off_start or "default")
                report.add(f"service {svc.name} → {target}", ok, err)
                emit(("  ok  " if ok else "  ERR ") + f"service {svc.name}" + (f" ({err})" if err else ""))
                applied_any = applied_any or ok

            # extra commands
            for cmd in (tweak.apply_cmds if enable else tweak.revert_cmds):
                done += 1
                progress(done, total)
                ok, detail = self._run_command(cmd, emit)
                report.add(cmd.display(), ok, detail)
                applied_any = applied_any or ok

            if tweak.restart == "explorer" and enable:
                need_explorer_restart = True

        if backup and applied_any:
            rec = session.commit()
            if rec:
                report.backup_id = rec.id
                emit(f"Backup saved: {rec.id} ({rec.size} change(s) — undo from History)")

        if need_explorer_restart:
            self.restart_explorer(emit)

        progress(total, total)
        return report

    # -- primitives ------------------------------------------------------
    def _write_reg(self, reg: RegSet, enable: bool) -> tuple[bool, str]:
        if enable:
            return registry.set_value(reg.hive, reg.path, reg.name, reg.value, reg.vtype)
        if reg.off_value is DELETE:
            return registry.delete_value(reg.hive, reg.path, reg.name)
        vtype = reg.vtype if reg.vtype != "auto" else registry.infer_type(reg.off_value)
        return registry.set_value(reg.hive, reg.path, reg.name, reg.off_value, vtype)

    def _write_service(self, svc: ServiceSet, enable: bool) -> tuple[bool, str]:
        target = svc.start if enable else (svc.off_start or ("demand" if svc.start == "disabled" else "auto"))
        ok, err = (True, "")
        if target:
            ok, err = services.set_start(svc.name, target)
        if not ok:
            return (ok, err)
        if enable and svc.running is not None:
            ok2, err2 = services.control(svc.name, "start" if svc.running else "stop")
            return (ok2, err2)
        if not enable and svc.running is False:
            ok2, err2 = services.control(svc.name, "start")
            return (ok2, err2)
        return (ok, err)

    def _target_text(self, reg: RegSet, enable: bool) -> str:
        value = reg.value if enable else reg.off_value
        return "<removed>" if value is DELETE else str(registry.normalise(value))

    def _run_command(self, cmd: Command, emit: Callable[[str], None]) -> tuple[bool, str]:
        from .runner import build_command

        argv = build_command(cmd)
        rc, err = run_stream(argv, on_line=lambda line: emit("  | " + line), timeout=cmd.timeout)
        return (rc == 0, err)

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def run_action(
        self,
        action: ActionDef,
        emit: Callable[[str], None] | None = None,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> Report:
        emit = emit or (lambda _m: None)
        progress = progress or (lambda _d, _t: None)
        report = Report(action.name)
        report.simulated = pf.simulating()

        if action.admin and pf.IS_WINDOWS and not pf.is_admin():
            report.add(action.name, False, "requires administrator rights")
            emit("This task needs administrator rights — relaunch WinX as Administrator.")
            return report

        steps = list(action.steps)
        total = max(len(steps), 1)
        emit(f"Starting: {action.name}")
        for i, step in enumerate(steps, 1):
            if cancel is not None and cancel():
                report.add("cancelled", False, "stopped by user")
                break
            progress(i, total)
            emit("> " + step.display())
            if step.kind == "py" and action.handler is not None:
                try:
                    detail = action.handler(emit=emit) or ""
                    report.add(step.display(), True, str(detail))
                except Exception as exc:  # noqa: BLE001
                    report.add(step.display(), False, str(exc))
                    emit(f"  ! {exc}")
                continue
            rc, err = run_stream(
                step,
                on_line=lambda line: emit("  " + line),
                timeout=step.timeout,
                cancel=cancel,
            )
            report.add(step.display(), rc == 0, err)
        progress(total, total)
        emit(report.summary())
        return report

    # ------------------------------------------------------------------
    # misc
    # ------------------------------------------------------------------
    def restart_explorer(self, emit: Callable[[str], None] | None = None) -> bool:
        """Restart explorer.exe so visual tweaks take effect immediately."""
        emit = emit or (lambda _m: None)
        if not pf.IS_WINDOWS or pf.simulating():
            emit("  (simulated) explorer restarted")
            return True
        rc, out, err = run_sync(
            [
                pf.powershell_exe(),
                "-NoProfile",
                "-Command",
                "Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue; "
                "Start-Sleep -Milliseconds 500; "
                "if (-not (Get-Process explorer -ErrorAction SilentlyContinue)) { Start-Process explorer }",
            ],
            timeout=60,
        )
        emit("  explorer restarted" if rc == 0 else f"  explorer restart failed: {err}")
        return rc == 0

    def undo(self, backup_id: str, emit: Callable[[str], None] | None = None) -> Report:
        report = self.backups.undo(backup_id)
        if emit:
            for step in report.steps:
                emit(str(step))
            emit(report.summary())
        return report
