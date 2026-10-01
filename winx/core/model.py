"""Declarative data model for changes.

Everything WinX can *do* to a machine is described as data before it is
executed.  That gives us, for free:

* a preview of the exact commands/registry writes,
* automatic "is this already applied?" state checks,
* automatic revert (old registry values are captured before writing),
* a single place to attach a risk rating and an admin requirement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

# Risk levels ---------------------------------------------------------------
SAFE = "safe"           # reversible, no functional loss
MODERATE = "moderate"   # changes behaviour a user may notice
RISKY = "risky"         # can break features; always warned about

RISK_LABEL = {
    SAFE: "Safe",
    MODERATE: "Moderate",
    RISKY: "Advanced",
}
RISK_COLOR = {
    SAFE: "#3ecf8e",
    MODERATE: "#f5c451",
    RISKY: "#ff6b6b",
}


# Registry ------------------------------------------------------------------
class _Delete:
    """Sentinel: turning a tweak off means removing the value entirely."""

    def __repr__(self) -> str:  # pragma: no cover
        return "<delete>"

    def __bool__(self) -> bool:
        return False


DELETE = _Delete()


@dataclass
class RegSet:
    """A single registry value we want to end up at ``value``."""

    hive: str  # HKCU | HKLM | HKU | HKCR
    path: str
    name: str
    value: Any
    vtype: str = "auto"  # auto | REG_SZ | REG_EXPAND_SZ | REG_DWORD | REG_MULTI_SZ | REG_BINARY
    #: value written when the tweak is switched off (DELETE by default, which
    #: removes the override and lets Windows fall back to its default)
    off_value: Any = DELETE

    @property
    def location(self) -> str:
        return rf"{self.hive}\{self.path}\{self.name}".replace("\\\\", "\\")


@dataclass
class ServiceSet:
    """Desired start-up type / running state of a Windows service."""

    name: str
    start: str | None = None   # auto | delayed-auto | demand(manual) | disabled
    running: bool | None = None  # True=start, False=stop, None=leave
    #: start-up type restored when the tweak is switched off
    off_start: str = ""

    @property
    def location(self) -> str:
        return f"service:{self.name}"


@dataclass
class Command:
    """A shell/PowerShell command run as part of an action."""

    kind: str  # powershell | cmd | proc
    args: list[str] = field(default_factory=list)
    script: str = ""
    timeout: int = 900
    #: printable text shown in the preview / log
    label: str = ""

    def display(self) -> str:
        if self.label:
            return self.label
        if self.kind == "powershell":
            return f"powershell -Command {self.script}"
        if self.kind == "cmd":
            return "cmd /c " + " ".join(self.args)
        return " ".join(self.args)


# Tweaks --------------------------------------------------------------------
@dataclass
class TweakDef:
    """A reversible, stateful setting (rendered as a switch in the UI)."""

    key: str
    name: str
    description: str
    category: str
    risk: str = SAFE
    admin: bool = False
    sets: Sequence[RegSet] = ()
    services: Sequence[ServiceSet] = ()
    apply_cmds: Sequence[Command] = ()
    revert_cmds: Sequence[Command] = ()
    #: explorer = restart Explorer, pc = needs reboot to take effect
    restart: str = ""
    tags: tuple[str, ...] = ()

    @property
    def is_checkable(self) -> bool:
        """True when we can determine (and therefore toggle) the current state."""
        return bool(self.sets) or bool(self.services)

    def locations(self) -> list[str]:
        return [s.location for s in self.sets] + [s.location for s in self.services]

    def registry_paths(self) -> list[tuple[str, str]]:
        seen: dict[tuple[str, str], None] = {}
        for s in self.sets:
            seen[(s.hive, s.path)] = None
        return list(seen.keys())


# One-shot actions ----------------------------------------------------------
@dataclass
class ActionDef:
    """A one-shot maintenance/repair task (rendered as a button)."""

    key: str
    name: str
    description: str
    group: str
    steps: Sequence[Command] = ()
    risk: str = SAFE
    admin: bool = False
    #: rough duration hint in seconds, used for the progress UI
    eta: int = 20
    note: str = ""
    #: optional python callable used instead of / in addition to commands
    handler: Callable | None = None


# Results -------------------------------------------------------------------
@dataclass
class StepResult:
    label: str
    ok: bool
    detail: str = ""

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        mark = "OK  " if self.ok else "FAIL"
        return f"[{mark}] {self.label}" + (f" — {self.detail}" if self.detail else "")


@dataclass
class Report:
    title: str
    steps: list[StepResult] = field(default_factory=list)
    backup_id: str | None = None
    simulated: bool = False

    def add(self, label: str, ok: bool, detail: str = "") -> StepResult:
        r = StepResult(label, ok, detail)
        self.steps.append(r)
        return r

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps)

    @property
    def failed(self) -> list[StepResult]:
        return [s for s in self.steps if not s.ok]

    def summary(self) -> str:
        total = len(self.steps)
        good = sum(1 for s in self.steps if s.ok)
        state = "simulated" if self.simulated else "completed"
        if total == 0:
            return f"{self.title}: nothing to do"
        if good == total:
            return f"{self.title} {state} — {good}/{total} steps OK"
        return f"{self.title} {state} — {good}/{total} steps OK, {total - good} failed"


def dedupe(items: Iterable[Any]) -> list[Any]:
    out: list[Any] = []
    for i in items:
        if i not in out:
            out.append(i)
    return out
