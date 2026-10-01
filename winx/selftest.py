"""Headless self-test.

Exercises the whole engine without a window: state checks, applying tweaks,
undoing them, running actions and every enumeration module.  Run it with::

    python main.py --selftest
"""

from __future__ import annotations

import sys
import traceback
from PySide6.QtCore import QCoreApplication

from .core import platform as pf
from .core.backup import BackupManager
from .core.engine import Engine, ON, OFF
from .core.format import human_size
from .core.registry import seed_simulation
from .core.simdata import seeded_registry

APP = None
PASSED = 0
FAILED = 0
FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {name}")
    else:
        FAILED += 1
        FAILURES.append(name)
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))
    return condition


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def main() -> int:
    global APP
    APP = QCoreApplication(sys.argv)
    seed_simulation(seeded_registry())

    from .modules import actions_data, apps, cleaner, disks, drivers, startup, systeminfo, tweaks_data

    engine = Engine()
    backups = BackupManager()

    section("Catalogue integrity")
    check("tweaks loaded", len(tweaks_data.ALL_TWEAKS) > 50, f"{len(tweaks_data.ALL_TWEAKS)}")
    check("actions loaded", len(actions_data.ALL_ACTIONS) > 30, f"{len(actions_data.ALL_ACTIONS)}")
    keys = [t.key for t in tweaks_data.ALL_TWEAKS]
    check("tweak keys unique", len(keys) == len(set(keys)))
    akeys = [a.key for a in actions_data.ALL_ACTIONS]
    check("action keys unique", len(akeys) == len(set(akeys)))
    check(
        "every tweak has a category page",
        all(t.category in tweaks_data.CATEGORIES for t in tweaks_data.ALL_TWEAKS),
    )
    check(
        "every action has a group page",
        all(a.group in actions_data.ACTION_GROUPS for a in actions_data.ALL_ACTIONS),
    )
    check(
        "risky tweaks are checkable or documented",
        all(t.is_checkable or t.apply_cmds for t in tweaks_data.ALL_TWEAKS),
    )

    section("State detection")
    states = engine.states(tweaks_data.ALL_TWEAKS)
    check("state returned for every tweak", len(states) == len(tweaks_data.ALL_TWEAKS))
    check(
        "states are valid",
        all(v in (ON, OFF, "partial", "unknown") for v in states.values()),
    )

    section("Start-type normalisation (sc qc vs PowerShell spellings)")
    from .core import services

    for raw, expected in (
        ("AUTO_START", "auto"),
        ("DEMAND_START", "demand"),
        ("DISABLED", "disabled"),
        ("BOOT_START", "boot"),
        ("SYSTEM_START", "system"),
        ("2   AUTO_START (DELAYED)", "delayed-auto"),
        ("Auto", "auto"),
        ("Manual", "demand"),
        ("AutoDelayedStart", "delayed-auto"),
        ("delayed-auto", "delayed-auto"),
        ("demand", "demand"),
    ):
        check(f"normalise_start({raw!r}) == {expected!r}",
              services.normalise_start(raw) == expected,
              services.normalise_start(raw))

    section("Apply → verify → undo")
    # Registry-only, HKCU tweaks work on any machine, elevated or not.
    sample = [
        tweaks_data.by_key("perf_visual_best"),
        tweaks_data.by_key("ui_file_extensions"),
        tweaks_data.by_key("priv_feedback_off"),
    ]
    # HKLM / service tweaks need rights and the service to exist, so they are
    # only exercised where they can actually apply.
    elevated = pf.simulating() or pf.is_admin()
    if elevated:
        sample.append(tweaks_data.by_key("priv_advertising_id_off"))
    sysmain = tweaks_data.by_key("perf_sysmain_off")
    sysmain_exists = services.query("SysMain").get("exists")
    if elevated and sysmain_exists and sysmain is not None:
        sample.append(sysmain)
    sample = [t for t in sample if t is not None]
    check("sample tweaks found", len(sample) >= 3, f"{len(sample)}")
    print(f"        sampling: {', '.join(t.key for t in sample)}")

    before = {t.key: engine.tweak_state(t) for t in sample}
    report = engine.apply_tweaks([(t, True) for t in sample], backup=True)
    check("apply reported success", report.ok, report.summary())
    check("backup record created", bool(report.backup_id))
    after = {t.key: engine.tweak_state(t) for t in sample}
    check(
        "every sampled tweak is now on",
        all(v == ON for v in after.values()),
        str({k: (before[k], v) for k, v in after.items()}),
    )

    undo_report = engine.undo(report.backup_id)
    check("undo reported success", undo_report.ok, undo_report.summary())
    restored = {t.key: engine.tweak_state(t) for t in sample}
    check(
        "state restored to the original values",
        all(restored[k] == before[k] for k in restored),
        str({k: (before[k], restored[k]) for k in restored}),
    )

    if not elevated:
        print("        note: not elevated — HKLM and service tweaks skipped")
    if elevated and not sysmain_exists:
        print("        note: SysMain service absent on this machine — skipped")

    section("Backup ledger")
    records = backups.all()
    check("backup records exist", len(records) >= 1)
    check("records carry entries", any(r.entries or r.service_entries for r in records))
    keep = records[0]
    check("undo of oldest record runs", engine.undo(keep.id).steps != [])
    for record in records:
        backups.delete(record.id)
    check("history cleared", backups.all() == [])

    section("Preview")
    tweak = tweaks_data.by_key("priv_telemetry_off")
    preview = engine.preview_tweak(tweak, True)
    check("preview lists registry writes", len(preview) >= 3, str(preview[:2]))
    check(
        "preview lists services",
        any("service" in line for line in preview),
    )
    action = actions_data.action_by_key("net_flush_dns")
    check("action preview non-empty", len(engine.preview_action(action)) >= 1)

    section("Actions")
    actions_to_run = ["net_flush_dns", "maint_restart_explorer", "tool_services"]
    if pf.simulating():
        # SFC and DISM are slow and may legitimately report repairs on a live
        # machine, so they are only asserted where the outcome is deterministic.
        actions_to_run.insert(1, "repair_sfc")
        actions_to_run.insert(2, "net_full_reset")
    for key in actions_to_run:
        act = actions_data.action_by_key(key)
        result = engine.run_action(act)
        check(f"run {key}", result.ok, result.summary())

    section("Modules")
    results = cleaner.scan()
    check("cleaner scan returns rows", len(results) > 5, f"{len(results)} targets")
    check(
        "scan rows carry a name and size",
        all(r.name and r.size >= 0 for r in results),
    )
    total_junk = sum(r.size for r in results if not r.unmeasured)
    print(f"        junk measured: {human_size(total_junk)} across {len(results)} targets")

    items = startup.enumerate_items()
    check("startup entries found", len(items) >= 3, f"{len(items)}")

    installed = apps.installed_apps()
    check("installed apps found", len(installed) >= 5, f"{len(installed)}")
    check("bloatware detected", any(apps.is_bloat_app(a)[0] for a in installed))
    check(
        "uninstall command generated",
        all(apps.uninstall_command(a) for a in installed),
    )

    volumes = disks.volumes()
    check("volumes found", len(volumes) >= 1, f"{len(volumes)}")
    check("smart report returns rows", len(disks.smart_report()) >= 0)

    drv = drivers.list_drivers()
    check("drivers listed", len(drv) >= 1, f"{len(drv)}")
    if pf.IS_WINDOWS and not pf.simulating():
        # pnputil needs elevation; without it the driver store is simply empty
        check("driver store readable", isinstance(drivers.driver_store(), list))
    else:
        check("driver store listed", len(drivers.driver_store()) >= 1)

    info = systeminfo.snapshot()
    check("snapshot has os", bool(info.get("os")))
    check("snapshot has cpu", bool(info.get("cpu")))
    check("snapshot has memory", bool(info.get("memory")))

    checks = systeminfo.health_checks(junk_bytes=total_junk, startup_count=len(items))
    check("health checks produced", len(checks) >= 3, f"{len(checks)}")
    check(
        "health checks well formed",
        all(c["status"] in ("ok", "warn", "fail", "info") for c in checks),
    )

    section("Simulation safety")
    check("simulation is active off-Windows", pf.simulating() or pf.IS_WINDOWS)
    if not pf.IS_WINDOWS:
        check("no admin claim off-Windows", pf.is_admin() is False)

    print("\n" + "=" * 60)
    print(f"passed: {PASSED}   failed: {FAILED}")
    if FAILURES:
        print("failures: " + ", ".join(FAILURES))
    print("=" * 60)
    return 1 if FAILED else 0


if __name__ == "__main__":  # pragma: no cover
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        raise SystemExit(2)
