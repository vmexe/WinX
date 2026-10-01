"""Backups, restore points and the undo ledger.

Backups are *optional* (the user can switch them off per run or globally), but
when they are on every registry value WinX touches is recorded — including the
fact that it did not exist before — so an undo restores the machine exactly.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .config import backups_dir
from . import platform as pf
from . import registry, services
from .model import Report, RegSet, ServiceSet
from .runner import run_script

UNDO_VERSION = 1


@dataclass
class RegEntry:
    hive: str
    path: str
    name: str
    existed: bool
    old_value: Any = None
    old_type: str = ""
    new_value: Any = None
    new_type: str = ""


@dataclass
class ServiceEntry:
    name: str
    old_start: str = ""
    new_start: str = ""
    old_state: str = ""
    new_state: str = ""


@dataclass
class BackupRecord:
    id: str
    label: str
    created: float
    simulated: bool
    entries: list[RegEntry] = field(default_factory=list)
    service_entries: list[ServiceEntry] = field(default_factory=list)
    restore_point: bool = False
    notes: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    @property
    def created_str(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.created))

    @property
    def size(self) -> int:
        return len(self.entries) + len(self.service_entries)


class BackupSession:
    """Collects pre-change state while a batch of changes is applied."""

    def __init__(self, label: str, with_restore_point: bool = False):
        self.label = label
        self.record = BackupRecord(
            id=time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4],
            label=label,
            created=time.time(),
            simulated=pf.simulating(),
        )
        self._with_restore_point = with_restore_point
        self._captured: set[tuple[str, str, str]] = set()

    # -- capture ---------------------------------------------------------
    def capture_registry(self, reg: RegSet) -> None:
        key = (reg.hive, reg.path, reg.name)
        if key in self._captured:
            return
        self._captured.add(key)
        exists, value, vtype = registry.get_value(reg.hive, reg.path, reg.name)
        self.record.entries.append(
            RegEntry(
                hive=reg.hive,
                path=reg.path,
                name=reg.name,
                existed=exists,
                old_value=value,
                old_type=vtype,
                new_value=registry.normalise(reg.value),
                new_type=reg.vtype if reg.vtype != "auto" else registry.infer_type(reg.value),
            )
        )

    def capture_service(self, svc: ServiceSet) -> None:
        info = services.query(svc.name)
        entry = ServiceEntry(
            name=svc.name, old_start=info.get("start", ""), old_state=info.get("state", "")
        )
        if svc.start:
            entry.new_start = services.normalise_start(svc.start)
        if svc.running is True:
            entry.new_state = "RUNNING"
        elif svc.running is False:
            entry.new_state = "STOPPED"
        self.record.service_entries.append(entry)

    def note(self, text: str) -> None:
        self.record.notes.append(text)

    def add_file(self, path: str) -> None:
        self.record.files.append(path)

    # -- lifecycle -------------------------------------------------------
    def create_restore_point(self) -> tuple[bool, str]:
        if not (self._with_restore_point and pf.IS_WINDOWS and not pf.simulating()):
            if not pf.IS_WINDOWS or pf.simulating():
                self.record.restore_point = True
                return (True, "simulated")
            return (False, "restore points unavailable")
        script = (
            "Checkpoint-Computer -Description 'WinX: " + self.label.replace("'", "") +
            "' -RestorePointType 'MODIFY_SETTINGS' -ErrorAction Stop"
        )
        rc, out, err = run_script(script, timeout=600)
        self.record.restore_point = rc == 0
        return (rc == 0, out.strip() or err.strip())

    def commit(self) -> BackupRecord | None:
        if not self.record.entries and not self.record.service_entries and not self.record.restore_point:
            return None
        path = backups_dir() / f"{self.record.id}.json"
        path.write_text(json.dumps(asdict(self.record), indent=1, default=str), encoding="utf-8")
        return self.record

    def abort(self) -> None:
        self.record = BackupRecord(self.record.id, self.label, self.record.created, pf.simulating())


class BackupManager:
    """Persistent store of :class:`BackupRecord` files with undo support."""

    def __init__(self) -> None:
        self.dir = backups_dir()

    def all(self) -> list[BackupRecord]:
        out: list[BackupRecord] = []
        for f in sorted(self.dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                out.append(
                    BackupRecord(
                        id=data["id"],
                        label=data["label"],
                        created=data["created"],
                        simulated=data.get("simulated", False),
                        entries=[RegEntry(**e) for e in data.get("entries", [])],
                        service_entries=[ServiceEntry(**s) for s in data.get("service_entries", [])],
                        restore_point=data.get("restore_point", False),
                        notes=data.get("notes", []),
                        files=data.get("files", []),
                    )
                )
            except Exception:
                continue
        return out

    def get(self, backup_id: str) -> BackupRecord | None:
        for rec in self.all():
            if rec.id == backup_id:
                return rec
        return None

    def delete(self, backup_id: str) -> bool:
        f = self.dir / f"{backup_id}.json"
        if f.exists():
            f.unlink()
            return True
        return False

    def clear(self) -> int:
        n = 0
        for f in self.dir.glob("*.json"):
            f.unlink()
            n += 1
        return n

    def undo(self, backup_id: str) -> Report:
        rec = self.get(backup_id)
        report = Report(f"Undo “{rec.label if rec else backup_id}”")
        if rec is None:
            report.add("locate backup", False, "backup record not found")
            return report

        for entry in reversed(rec.entries):
            label = rf"{entry.hive}\{entry.path}\{entry.name}"
            if entry.existed:
                ok, err = registry.set_value(
                    entry.hive, entry.path, entry.name, entry.old_value, entry.old_type or "auto"
                )
                report.add(f"restore {label}", ok, err)
            else:
                ok, err = registry.delete_value(entry.hive, entry.path, entry.name)
                report.add(f"remove {label}", ok, err)

        for entry in rec.service_entries:
            if entry.old_start:
                ok, err = services.set_start(entry.name, entry.old_start)
                report.add(f"service {entry.name} → {entry.old_start}", ok, err)
            if entry.old_state in ("RUNNING", "STOPPED"):
                want = "start" if entry.old_state == "RUNNING" else "stop"
                ok, err = services.control(entry.name, want)
                report.add(f"service {entry.name} → {entry.old_state.lower()}", ok, err)

        if rec.restore_point:
            report.add("restore point", True, "use System Restore to roll back completely")
        report.backup_id = backup_id
        return report

    def total_bytes(self) -> int:
        return sum(f.stat().st_size for f in self.dir.glob("*.json"))


def create_restore_point(description: str = "WinX") -> tuple[bool, str]:
    session = BackupSession(description, with_restore_point=True)
    return session.create_restore_point()
