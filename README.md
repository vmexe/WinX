# WinX — Windows All‑in‑One Utility

A single PySide6 application that **cleans, tunes, repairs and reports on** a Windows
machine: 85 reversible tweaks, 59 scripted repair/network/security tasks, a junk cleaner
with 30 target locations, a startup + services manager, a Store‑app uninstaller with
bloatware detection, disk/driver tooling and a live health dashboard.

Every mutating operation is *declarative*: it is described before it is executed, so
WinX can show you a preview, back up the previous value, and undo it later.

```
python main.py              # run the GUI
python main.py --simulate   # dry run: never change anything
python main.py --selftest   # exercise the whole engine headlessly
python main.py --version
```

---

## Why it is built this way

| Concern | How WinX handles it |
| --- | --- |
| **Trust** | Nothing runs before you see it. Every tweak has a *Preview* listing the exact registry values, service changes and commands. Repair tasks stream their real output into the activity log. |
| **Reversibility** | Before a value is written, WinX records what was there — including *“nothing”*. Backups are listed in **Settings → History** and can be undone, individually or wholesale. Backups are **optional**; switch them off per run (the checkbox on the Apply bar) or globally. |
| **Honesty about risk** | Each change is rated *Safe*, *Moderate* or *Advanced*, tagged *Admin* where elevation is required, and flagged when it needs a reboot or restarts Explorer. Advanced changes get their own confirmation. |
| **Responsiveness** | Scans, repairs and enumerations run on a `QThreadPool`; the UI never blocks and long tasks can be cancelled. `tools/uicheck.py` measures UI-thread block time in CI. |
| **Native look** | Standard Qt widgets only — no stylesheet, no custom palette, no bundled fonts and no hand-drawn icons. WinX uses the platform style, so it follows the system theme and the user's font and scaling settings. Icons come from the shell (real program icons in the Uninstaller) and from the style's standard pixmaps. |
| **Light or dark, your choice** | *Settings → Appearance* (or *View → Appearance*) switches between **Follow Windows / Light / Dark** using Qt's own colour scheme, so the native style simply redraws itself — there is still no WinX theme. |
| **Finding things** | One search box in the toolbar (**Ctrl+F**) covers pages, all 85 tweaks and all 59 tasks; picking a result opens the page with its own filter already applied. The navigation is a collapsible tree — no disabled rows. |
| **Not re-scanning** | Each page keeps its last result and shows *“Updated 3 minutes ago”* with a Refresh button; re-opening the Uninstaller, Disks or Drivers is instant. `tools/uicheck.py` fails the build if a page re-scans on re-open. |
| **Staying current** | The **Updater** page updates Windows, your programs (winget) and Store apps from one list; *Help → Check for updates* does the same for WinX itself, and the packaged `WinX.exe` can install its own update and relaunch. |
| **Fits your eyes** | *Settings → Appearance* has an **interface size** slider (80–180%) that scales every window, button and row by resizing the system font WinX inherits — no custom font, no stylesheet. |
| **Testability** | The engine has no widget dependencies, so `python main.py --selftest` applies real changes, verifies them, undoes them and checks every module — on Windows *and* on Linux/macOS in simulation mode. |

---

## What it does

### Dashboard
A **health score out of 100** with a plain-English verdict, quick-action buttons
(*Free up space*, *Update everything*, *Trim startup*, *Speed up Windows*, *Check
security*, *Repair Windows*) and findings grouped into **Problems / Worth fixing /
Suggestions / Looking good**. Built from live checks (disk space, SMART, memory pressure, uptime, junk
size, startup count, telemetry, SmartScreen, Remote Desktop, Defender, firewall),
live CPU/RAM/disk meters, and “what needs attention” rows that jump straight to the
page that fixes them.

### Cleaner — 30 targets
Windows temp, `%TEMP%`, Windows Update cache, Delivery Optimisation, prefetch,
thumbnail/icon cache, font cache, WER reports, crash dumps, CBS/DISM/Panther logs,
shader caches (D3DS/NVIDIA/AMD), IIS logs, Defender scan history, Recycle Bin,
`Windows.old`… plus browser caches (Chrome, Edge, Firefox, Brave, Opera/Vivaldi),
app caches (Discord, Slack, Teams, Spotify, Steam, Office) and developer caches
(npm/yarn/pnpm, pip, NuGet, VS, Chocolatey).

Two rules are never broken: only the listed locations are touched, and **locked files
are skipped, never forced**.

### Tweaks — 85 switches, all reversible

| Page | Examples |
| --- | --- |
| **Performance** (28) | Best‑performance visual effects, instant menus, no animations/transparency, background apps off, remove the 10 s startup delay, auto‑close hung apps, SysMain/Superfetch off, Windows Search off, hibernation off, Fast Startup off, disable NTFS last‑access timestamps, foreground‑app priority, remove network throttling, hardware‑accelerated GPU scheduling, Storage Sense, mouse acceleration off, Sticky Keys prompt off, plus **power plans** (Ultimate / High / Balanced / Power saver, USB selective suspend) |
| **Privacy** (19) | Telemetry → 0 + DiagTrack disabled, advertising ID, activity history, location tracking, feedback requests, tailored experiences, web search in Start, Cortana, typing/inking personalisation, Wi‑Fi Sense, app diagnostics, camera/microphone policy, Copilot, Recall snapshots, telemetry scheduled tasks, cloud clipboard, voice activation, recent‑document tracking |
| **Security** (13) | Force SmartScreen, Remote Desktop off, Remote Registry off, AutoPlay/AutoRun off, SMBv1 off, LLMNR/mDNS off, LSA protection (RunAsPPL), UAC secure desktop, hide last user, Guest account off, Defender tamper protection, Windows Script Host off, PowerShell script‑block logging |
| **Network** (5) | IPv6 off, Nagle off, QoS reservation off, TCP auto‑tuning off, hotspot auto‑join off |
| **Interface** (14) | Dark mode, file extensions, hidden files, This PC on launch, taskbar left/small/hide Widgets/Chat/Task View, classic context menu, hide Start recommendations, seconds in the clock, no Explorer ads, no lock‑screen tips |
| **Gaming** (6) | Game Mode on, Game DVR + background recording off, Game Bar overlay off, fullscreen optimisations off, no game power throttling, notifications suppressed while gaming |

### Repair — 17 scripted fixes
SFC, DISM `ScanHealth` / `RestoreHealth` / `StartComponentCleanup` (+ `/ResetBase`),
a **full DISM→SFC stack repair**, `chkdsk /scan` and scheduled `/F /R`, Windows Update
reset (services + `SoftwareDistribution` + `Catroot2`), Store cache reset, re‑register
all AppX packages, rebuild icon/thumbnail cache, rebuild the search index, time sync
fix, hosts‑file restore, driver‑store listing, and `powercfg /energy` + `perfmon /report`.

### Network — 13 fixes
Flush DNS, release/renew, Winsock reset, TCP/IP reset, **full network reset**, clear
proxy (system + WinHTTP), firewall reset, DNS presets (Cloudflare / Google / AdGuard /
automatic), ARP cache clear, restart all adapters.

### Startup
Registry Run/RunOnce keys (HKCU+HKLM+WOW6432Node), Startup folders, and logon/boot
**scheduled tasks** — with an impact rating. Disabling renames the entry (never
deletes), so it can always be restored; a second tab manages auto‑starting services.

### Uninstaller
Win32 + MSI + AppX inventory with the program's **real icon**, size and publisher,
filters (everything / bloatware / desktop programs / Store apps / removable), a
minimum-size slider and sorting by name, size, publisher or source, bloatware detection against a
curated pattern list (Candy Crush, TikTok, Spotify, Disney+, Clipchamp, Xbox extras…),
batch uninstall, and generated silent uninstall commands (`msiexec /X{ guid } /qn`,
`Remove-AppxPackage`, provisioned‑package cleanup, winget as a fallback).

### Updater
One list for everything that is out of date: **Windows Update** (read and installed
through the same COM API the Settings app uses), **programs** via `winget upgrade`,
and a **Microsoft Store** update scan — with sizes, "needs a restart" and "needs
administrator" notes, a recently-installed history tab, and a button to check for a
new WinX.

### Disks & drivers
Volume usage + media type + health, SMART reliability counters, TRIM/defrag per volume,
folder‑size analysis, large‑file finder, MD5 duplicate finder (with reclaimable total),
driver inventory with problem devices highlighted, one‑click **driver backup**
(`pnputil /export-driver`), hardware rescan, and driver‑store management.

### System, Security & Tools
Full hardware/OS inventory with copy/save report; Defender quick/full/offline scans,
signature update, firewall, BitLocker and activation status; 16 one‑click launchers for
services.msc, devmgmt.msc, diskmgmt.msc, msconfig, taskschd.msc, eventvwr, msinfo32,
resmon, optionalfeatures, rstrui, dxdiag, sysdm.cpl, appwiz.cpl, firewall.cpl, ncpa.cpl
and powercfg.cpl.

---

## Safety model

1. **Preview** — every dialog can show the exact values/commands (`Preview` buttons).
2. **Optional backup** — the Apply bar has a *“Back up (undoable)”* checkbox that
   defaults to your global setting. Turning it off is a supported choice; you just
   lose one‑click undo. Registry backups are re‑importable JSON snapshots of the
   affected values, and a Windows **System Restore point** can be created first
   (admin, opt‑in).
3. **Undo** — `Settings → History` lists every batch with its timestamp, change count
   and restore‑point flag; *Undo selected* puts everything back, including values that
   did not exist before.
4. **Risk labels** — Safe / Moderate / Advanced, plus Admin, “needs reboot” and
   “restarts Explorer” badges. Advanced changes get an explicit confirmation.
5. **Simulation mode** — `python main.py --simulate` (or the Settings toggle) shows
   everything and changes nothing.

---

## Project layout

```
main.py                     CLI entry point (GUI / --selftest / --simulate / --version)
winx/
  core/
    model.py                RegSet, ServiceSet, Command, TweakDef, ActionDef, Report
    engine.py               inspect → preview → apply → revert (the change engine)
    runner.py               synchronous + streaming command execution, cancellation
    registry.py             winreg wrapper with a JSON-backed offline implementation
    services.py             sc / PowerShell service control
    backup.py               backup sessions, restore points, the undo ledger
    platform.py             Windows detection, elevation, simulation flag
    winquery.py             structured PowerShell (CIM) queries
    workers.py              QThreadPool workers with progress/log signals
    updates.py              GitHub release check, download and self-update
    simdata.py              plausible machine data for simulation mode
  modules/
    tweaks_data.py          the 85 tweak definitions
    actions_data.py         the 59 one-shot tasks
    cleaner.py  startup.py  apps.py  disks.py  drivers.py  systeminfo.py
    updater.py              winget upgrades, Windows Update, Store update scan
  ui/
    main_window.py          navigation tree, global search, page stack, menus,
                            status bar, log dock, update checker
    appearance.py           light / dark / follow-Windows + interface size
    sysicons.py             shell icons (SHGetFileInfoW / ExtractIconExW), the
                            icons Windows uses for its own tools, chunked loading
    widgets.py              progress row + log console (plain Qt, no styling)
    pages/                  dashboard, cleaner, tweaks, repair, network, startup,
                            privacy, security, interface, gaming, apps, disks,
                            drivers, systeminfo, tools, settings
  selftest.py               headless end-to-end verification
build/                      PyInstaller spec, version info, build.bat / build.ps1
tools/                      make_icon.py, screenshot.py (visual QA),
                            check_imports.py, uicheck.py (UI responsiveness + load)
.github/workflows/ci.yml    self-test on Windows + Linux, then build WinX.exe
```

---

## Building the executable

```powershell
pwsh ./build/build.ps1          # or: build\build.bat
# → dist\WinX.exe   (single file, no console window, ~100 MB unpacked at runtime)
```

Or manually:

```bash
pip install -r requirements.txt pyinstaller
python tools/make_icon.py
pyinstaller build/WinX.spec --noconfirm --clean
```

CI (`.github/workflows/ci.yml`) runs the self‑test on Windows **and** Linux on every
push, then builds `WinX.exe` on Windows, uploads it as an artifact, and attaches it
plus a portable zip to the release when you push a `v*` tag:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

WinX starts un‑elevated and asks for elevation only when a specific task needs it —
the executable is deliberately **not** marked `requireAdministrator`, so the whole
non‑admin half of the app always works.

---

## Running from source

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Outside Windows the app starts in **simulation mode**: scans and previews are real
(it measures your actual `~/.cache`, lists your real disks and processes), nothing is
executed, and the registry is a local sandbox file. That is how the UI is developed
and tested, and it makes the app safe to demo anywhere.

---

## Requirements

* Windows 10 1809+ or Windows 11 (some tweaks are version‑specific and simply do
  nothing on older builds)
* Python 3.10+ with **PySide6 ≥ 6.6** and **psutil ≥ 5.9**
* Administrator rights only for the tasks that need them

## License

Apache‑2.0 — see [LICENSE](LICENSE).
