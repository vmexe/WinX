"""Dashboard: the at-a-glance health of the machine."""

from __future__ import annotations

import time

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QFormLayout,
    QVBoxLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
)

from ...core import platform as pf
from ...core.format import human_duration, human_size
from ...core.workers import submit
from ...modules import cleaner, startup, systeminfo
from .. import sysicons
from ..context import AppContext
from ..widgets import ProgressRow, status_icon
from .base import Page


class DashboardPage(Page):
    key = "dashboard"
    title = "Dashboard"
    subtitle = "A health check of this PC. Everything here is read-only until you choose to act."

    #: the dashboard only needs an estimate, and a full walk of every browser
    #: cache and Windows.old can take minutes of disk I/O
    JUNK_SCAN_BUDGET = 20.0

    #: the health check walks the disk, so keep its answer for a few minutes
    cache_ttl = 300.0

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.checks: list[dict] = []
        self._build()

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._tick)
        # started by showEvent

    # -- ui --------------------------------------------------------------
    def _build(self) -> None:
        top = QHBoxLayout()
        top.setSpacing(12)

        # --- health score -------------------------------------------------
        score_box = QGroupBox("Health score")
        score_layout = QVBoxLayout(score_box)
        score_layout.setSpacing(6)

        self.lbl_score = QLabel("—")
        font = self.lbl_score.font()
        font.setPointSizeF(max(28.0, font.pointSizeF() * 2.6))
        font.setBold(True)
        self.lbl_score.setFont(font)
        self.lbl_score.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        score_layout.addWidget(self.lbl_score)

        self.bar_score = QProgressBar()
        self.bar_score.setRange(0, 100)
        self.bar_score.setValue(0)
        self.bar_score.setTextVisible(False)
        score_layout.addWidget(self.bar_score)

        self.lbl_verdict = QLabel("Running the first check…")
        self.lbl_verdict.setWordWrap(True)
        self.lbl_verdict.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        score_layout.addWidget(self.lbl_verdict)

        self.lbl_counts = QLabel("")
        self.lbl_counts.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.lbl_counts.setEnabled(False)
        score_layout.addWidget(self.lbl_counts)
        score_layout.addStretch(1)
        top.addWidget(score_box, 1)

        # --- this pc -------------------------------------------------------
        system_box = QGroupBox("This PC")
        system_form = QFormLayout(system_box)
        system_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        system_form.setHorizontalSpacing(14)
        system_form.setVerticalSpacing(8)
        self.lbl_os = QLabel("—")
        self.lbl_computer = QLabel("—")
        self.lbl_user = QLabel("—")
        self.lbl_uptime = QLabel("—")
        self.lbl_mode = QLabel("—")
        for label, widget in (
            ("Windows:", self.lbl_os),
            ("Computer:", self.lbl_computer),
            ("Signed in as:", self.lbl_user),
            ("Switched on for:", self.lbl_uptime),
            ("Running as:", self.lbl_mode),
        ):
            widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            widget.setWordWrap(True)
            system_form.addRow(label, widget)
        top.addWidget(system_box, 2)

        # --- live meters ----------------------------------------------------
        live_box = QGroupBox("Right now")
        live_form = QFormLayout(live_box)
        live_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        live_form.setHorizontalSpacing(14)
        live_form.setVerticalSpacing(8)
        self.bar_cpu = QProgressBar()
        self.bar_ram = QProgressBar()
        self.bar_disk = QProgressBar()
        for bar in (self.bar_cpu, self.bar_ram, self.bar_disk):
            bar.setMinimumWidth(220)
        live_form.addRow("Processor:", self.bar_cpu)
        live_form.addRow("Memory:", self.bar_ram)
        live_form.addRow("System drive:", self.bar_disk)
        self.lbl_junk = QLabel("—")
        self.lbl_startup = QLabel("—")
        live_form.addRow("Junk files:", self.lbl_junk)
        live_form.addRow("Starts with Windows:", self.lbl_startup)
        top.addWidget(live_box, 2)

        self.layout_.addLayout(top)

        # --- quick actions ---------------------------------------------------
        actions_box = QGroupBox("Quick actions")
        actions_layout = QHBoxLayout(actions_box)
        actions_layout.setSpacing(8)
        for label, page, tip in (
            ("Free up space", "cleaner", "Find and delete junk files"),
            ("Update everything", "updater", "Windows, your programs and Store apps"),
            ("Trim startup", "startup", "Stop programs launching at login"),
            ("Speed up Windows", "performance", "Reversible performance settings"),
            ("Check security", "security", "Defender, firewall and hardening"),
            ("Repair Windows", "repair", "SFC, DISM and the usual fixes"),
        ):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.setIcon(sysicons.page_icon(page))
            button.clicked.connect(lambda _checked=False, key=page: self.ctx.navigate(key))
            actions_layout.addWidget(button)
        actions_layout.addStretch(1)
        self.layout_.addWidget(actions_box)

        # --- checks -----------------------------------------------------------
        checks_box = QGroupBox("What needs attention")
        checks_layout = QVBoxLayout(checks_box)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Check", "What WinX found"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIconSize(QSize(20, 20))
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemActivated.connect(lambda *_: self._goto_fix())
        checks_layout.addWidget(self.tree)
        self.layout_.addWidget(checks_box, 1)

        self.progress = ProgressRow()
        self.layout_.addWidget(self.progress)

        buttons = QHBoxLayout()
        self.btn_refresh = QPushButton("Run the checks again")
        self.btn_refresh.clicked.connect(self.force_refresh)
        buttons.addWidget(self.btn_refresh)

        self.btn_fix = QPushButton("Fix selected…")
        self.btn_fix.setEnabled(False)
        self.btn_fix.clicked.connect(self._goto_fix)
        buttons.addWidget(self.btn_fix)

        buttons.addStretch(1)

        self.btn_elevate = QPushButton("Restart as administrator")
        self.btn_elevate.clicked.connect(self._elevate)
        if pf.is_admin() or not pf.IS_WINDOWS:
            self.btn_elevate.setEnabled(False)
        buttons.addWidget(self.btn_elevate)
        self.layout_.addLayout(buttons)

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self.btn_refresh.setEnabled(False)
        self.progress.start("Running health checks…")
        worker = submit(self._load)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m or "Checking…"))
        worker.signals.message.connect(lambda m: self.log(m))
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_failed)

    def _load(self, progress=None, emit=None):
        emit = emit or (lambda _m: None)
        progress = progress or (lambda *_a: None)
        junk = 0
        try:
            progress(1, 4, "measuring junk files")
            deadline = time.monotonic() + self.JUNK_SCAN_BUDGET
            results = cleaner.scan(
                progress=lambda d, t, m: progress(1, 4, f"junk: {m}"),
                is_cancelled=lambda: time.monotonic() > deadline,
            )
            junk = sum(r.size for r in results if not r.unmeasured)
            if time.monotonic() > deadline:
                emit("Junk estimate stopped at 20s — open the Cleaner for an exact figure.")
        except Exception as exc:  # noqa: BLE001 - never kill the dashboard
            emit(f"Junk scan skipped: {exc}")

        try:
            progress(2, 4, "enumerating startup entries")
            items = startup.enumerate_items()
            startup_count = sum(1 for i in items if i.enabled)
        except Exception:  # noqa: BLE001
            startup_count = None

        progress(3, 4, "collecting system information")
        info = systeminfo.snapshot()

        progress(4, 4, "evaluating health")
        checks = systeminfo.health_checks(junk_bytes=junk, startup_count=startup_count, emit=emit)
        return {"checks": checks, "junk": junk, "startup": startup_count, "info": info}

    def _on_loaded(self, payload: dict) -> None:
        self.btn_refresh.setEnabled(True)
        self.checks = payload["checks"]
        info = payload["info"]
        self.progress.stop(f"{len(self.checks)} checks complete")

        score = systeminfo.health_score(self.checks)
        self.lbl_score.setText(f"{score['score']}")
        self.bar_score.setValue(score["score"])
        self.lbl_verdict.setText(score["verdict"])
        self.lbl_counts.setText(
            f"{score['problems']} to fix · {score['suggestions']} suggestions · "
            f"{score['healthy']} fine"
        )

        boot = info.get("boot_time") or 0
        self.lbl_os.setText(info.get("os", "—"))
        self.lbl_computer.setText(info.get("computer", "—"))
        self.lbl_user.setText(info.get("user", "—"))
        self.lbl_uptime.setText(human_duration(time.time() - boot) if boot else "—")

        if pf.simulating():
            mode = "Simulation mode — nothing is changed"
        elif not pf.IS_WINDOWS:
            mode = "Non-Windows host — features are simulated"
        elif pf.is_admin():
            mode = "Administrator"
        else:
            mode = "Standard user"
        self.lbl_mode.setText(mode)

        junk = payload["junk"]
        self.lbl_junk.setText(human_size(junk) if junk else "nothing to clean")
        self.lbl_startup.setText(
            f"{payload['startup']} enabled" if payload["startup"] is not None else "—"
        )

        self._render_checks()
        self._tick()
        self.status("Health checks complete")
        self.mark_loaded()

    def _on_failed(self, message: str) -> None:
        self.btn_refresh.setEnabled(True)
        self.progress.stop("Health checks failed")
        self.on_error(message)

    #: status -> (heading, expanded by default)
    GROUPS = [
        ("fail", "Problems", True),
        ("warn", "Worth fixing", True),
        ("info", "Suggestions", True),
        ("ok", "Looking good", False),
    ]

    def _render_checks(self) -> None:
        """Three short, labelled sections instead of one long status list."""
        self.tree.clear()
        for status, heading, expanded in self.GROUPS:
            rows = [c for c in self.checks if c.get("status") == status]
            if not rows:
                continue
            parent = QTreeWidgetItem([f"{heading}  ({len(rows)})", ""])
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            parent.setIcon(0, status_icon(status))
            parent.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(parent)
            for check in rows:
                item = QTreeWidgetItem([check["name"], check.get("detail", "")])
                item.setIcon(0, status_icon(status))
                fix = check.get("fix")
                item.setData(0, Qt.ItemDataRole.UserRole, fix)
                if fix:
                    item.setToolTip(1, f"Double-click to open {fix[1]}")
                parent.addChild(item)
            parent.setExpanded(expanded)
        self.tree.resizeColumnToContents(0)

    def _selection_changed(self) -> None:
        item = self.tree.currentItem()
        fix = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        self.btn_fix.setEnabled(bool(fix))
        self.btn_fix.setText(f"{fix[0]}…" if fix else "Fix selected…")

    def _goto_fix(self) -> None:
        item = self.tree.currentItem()
        fix = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if fix:
            self.ctx.navigate(fix[1])

    # -- live meters -----------------------------------------------------
    def _tick(self) -> None:
        """Live meters.

        Everything here runs on the UI thread, so it must stay syscall cheap.
        This used to call ``disks.volumes()``, which shells out to PowerShell
        (``Get-PhysicalDisk``, then ``Get-Volume`` per drive) — seconds of
        blocking, every two seconds, which is what made the window stop
        responding.
        """
        stats = systeminfo.live_stats()
        self.bar_cpu.setValue(int(stats["cpu"]))
        self.bar_cpu.setFormat(f"%p%  ({stats['procs']} processes)")
        self.bar_ram.setValue(int(stats["ram"]))
        self.bar_ram.setFormat("%p% in use")
        usage = systeminfo.system_drive_usage()
        if usage:
            self.bar_disk.setValue(usage["percent"])
            self.bar_disk.setFormat(f"%p% used · {human_size(usage['free'])} free")
            self.bar_disk.setToolTip(f"{usage['drive']} — {human_size(usage['free'])} free")

    # The meters only matter while the page is on screen; polling psutil (and
    # repainting) behind a hidden page is pure overhead.
    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        self._tick()
        self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().hideEvent(event)
        self._timer.stop()

    def _elevate(self) -> None:
        if self.ctx.elevate():
            self.status("Relaunching with administrator rights…")
