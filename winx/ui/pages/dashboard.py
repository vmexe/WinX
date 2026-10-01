"""Dashboard: the at-a-glance health of the machine."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core import platform as pf
from ...core.format import human_duration, human_size
from ...core.workers import submit
from ...modules import cleaner, disks, startup, systeminfo
from ..context import AppContext
from ..icons import icon
from ..widgets import Badge, ProgressRow, StatCard
from .base import Page

_CHECK_COLOR = {
    "fail": "#ff6b6b",
    "warn": "#f5c451",
    "info": "#8b98a9",
    "ok": "#3ecf8e",
}
_CHECK_ICON = {"fail": "warning", "warn": "warning", "info": "spark", "ok": "check"}

QUICK_ACTIONS = [
    ("Scan for junk", "trash", "cleaner", "Measure removable files"),
    ("Repair system files", "wrench", "repair", "SFC + DISM"),
    ("Fix the network", "globe", "network", "Full network reset"),
    ("Trim startup", "power", "startup", "Disable what you don't need"),
]


class DashboardPage(Page):
    key = "dashboard"
    title = "Dashboard"
    subtitle = ""
    icon_name = "dashboard"

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.checks: list[dict] = []
        self._build()
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # -- ui --------------------------------------------------------------
    def _build(self) -> None:
        layout = self.content_layout
        layout.setSpacing(12)

        self.hero = QFrame()
        self.hero.setObjectName("HeroCard")
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(20, 18, 20, 18)
        hero_layout.setSpacing(16)

        logo = QLabel()
        logo.setPixmap(icon("spark", "#0b0e14", 44).pixmap(44, 44))
        hero_layout.addWidget(logo)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.hero_title = QLabel("WinX")
        f = QFont()
        f.setPointSize(20)
        f.setWeight(QFont.Weight.Bold)
        self.hero_title.setFont(f)
        self.hero_title.setStyleSheet("color:#0b0e14;")
        texts.addWidget(self.hero_title)
        self.hero_sub = QLabel("Checking your system…")
        self.hero_sub.setStyleSheet("color:#0b0e14;")
        texts.addWidget(self.hero_sub)
        self.hero_meta = QLabel("")
        self.hero_meta.setStyleSheet("color:#0b0e14;")
        self.hero_meta.setProperty("muted", True)
        texts.addWidget(self.hero_meta)
        hero_layout.addLayout(texts, 1)

        right = QVBoxLayout()
        right.setSpacing(6)
        right.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.score_label = QLabel("—")
        sf = QFont()
        sf.setPointSize(30)
        sf.setWeight(QFont.Weight.Bold)
        self.score_label.setFont(sf)
        self.score_label.setStyleSheet("color:#0b0e14;")
        right.addWidget(self.score_label, 0, Qt.AlignmentFlag.AlignRight)
        self.score_caption = QLabel("health score")
        self.score_caption.setStyleSheet("color:#0b0e14;")
        right.addWidget(self.score_caption, 0, Qt.AlignmentFlag.AlignRight)
        hero_layout.addLayout(right)

        self.btn_elevate = QPushButton("Run as Administrator")
        self.btn_elevate.setStyleSheet(
            "QPushButton { background:#0b0e14; color:#ffffff; border:1px solid #0b0e14; border-radius:8px; padding:8px 14px; }"
            "QPushButton:hover { background:#1b2230; }"
        )
        self.btn_elevate.clicked.connect(self._elevate)
        hero_layout.addWidget(self.btn_elevate, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.hero)

        self.stats_row = QHBoxLayout()
        self.stats_row.setSpacing(10)
        self.stat_cpu = StatCard("CPU", "—", "", "bolt")
        self.stat_ram = StatCard("Memory", "—", "", "spark")
        self.stat_disk = StatCard("Free space", "—", "", "drive")
        self.stat_junk = StatCard("Junk found", "—", "", "trash")
        self.stat_startup = StatCard("Startup apps", "—", "", "power")
        for card in (self.stat_cpu, self.stat_ram, self.stat_disk, self.stat_junk, self.stat_startup):
            self.stats_row.addWidget(card)
        layout.addLayout(self.stats_row)

        quick = QHBoxLayout()
        quick.setSpacing(10)
        for title, icon_name, page_key, hint in QUICK_ACTIONS:
            button = QPushButton(f"  {title}")
            button.setIcon(icon(icon_name, self.ctx.accent, 18))
            button.setMinimumHeight(46)
            button.setToolTip(hint)
            button.clicked.connect(lambda _c=False, p=page_key: self.ctx.navigate(p))
            quick.addWidget(button)
        layout.addLayout(quick)

        checks_label = QLabel("What needs attention")
        cf = QFont()
        cf.setPointSize(13)
        cf.setWeight(QFont.Weight.DemiBold)
        checks_label.setFont(cf)
        layout.addWidget(checks_label)

        self.checks_widget = QWidget()
        self.checks_layout = QVBoxLayout(self.checks_widget)
        self.checks_layout.setContentsMargins(0, 0, 0, 0)
        self.checks_layout.setSpacing(8)
        layout.addWidget(self.checks_widget, 1)

        self.progress = ProgressRow()
        layout.addWidget(self.progress)

        footer = QHBoxLayout()
        self.btn_refresh = QPushButton(" Run checks again")
        self.btn_refresh.setIcon(icon("refresh", self.ctx.accent, 16))
        self.btn_refresh.clicked.connect(self.refresh)
        footer.addWidget(self.btn_refresh)
        footer.addStretch(1)
        self.status_note = QLabel("")
        self.status_note.setProperty("muted", True)
        footer.addWidget(self.status_note)
        layout.addLayout(footer)

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self.progress.start("Running health checks…")
        worker = submit(self._load)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m or "Checking…"))
        worker.signals.message.connect(lambda m: self.ctx.log(m, "info"))
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_error)

    def _load(self, progress=None, emit=None):
        emit = emit or (lambda _m: None)
        junk = 0
        try:
            if progress:
                progress(1, 4, "measuring junk files")
            results = cleaner.scan(
                progress=lambda d, t, m: progress(1, 4, f"junk: {m}") if progress else None,
            )
            junk = sum(r.size for r in results if not r.unmeasured)
        except Exception as exc:
            emit(f"junk scan skipped: {exc}")

        try:
            if progress:
                progress(2, 4, "enumerating startup entries")
            items = startup.enumerate_items()
            startup_count = sum(1 for i in items if i.enabled)
        except Exception:
            startup_count = None

        if progress:
            progress(3, 4, "collecting system info")
        info = systeminfo.snapshot()

        if progress:
            progress(4, 4, "evaluating health")
        checks = systeminfo.health_checks(junk_bytes=junk, startup_count=startup_count, emit=emit)
        return {"checks": checks, "junk": junk, "startup": startup_count, "info": info}

    def _on_loaded(self, payload: dict) -> None:
        self.checks = payload["checks"]
        info = payload["info"]
        self.progress.stop(f"{len(self.checks)} checks complete")

        boot = info.get("boot_time") or 0
        uptime = human_duration((info.get("boot_time") and (__import__("time").time() - boot)) or 0)
        self.hero_sub.setText(info.get("os", ""))
        state = f"{info.get('computer','')} · {info.get('user','')} · up {uptime}"
        if pf.simulating():
            state += " · SIMULATION MODE"
        self.hero_meta.setText(state)

        if pf.is_admin():
            self.btn_elevate.hide()
        elif not pf.IS_WINDOWS:
            self.btn_elevate.setText("Windows-only features are simulated")
            self.btn_elevate.setEnabled(False)

        self.stat_junk.set_value(
            human_size(payload["junk"]) if payload["junk"] else "0 B",
            "removable junk" if payload["junk"] else "nothing to clean",
        )
        self.stat_startup.set_value(
            str(payload["startup"]) if payload["startup"] is not None else "—", "launch at logon"
        )
        self._render_checks()
        self._tick()
        self.status("Health checks complete")

    def _render_checks(self) -> None:
        while self.checks_layout.count():
            item = self.checks_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        score = 100
        for check in self.checks:
            status = check["status"]
            score -= {"fail": 22, "warn": 9, "info": 2}.get(status, 0)
        score = max(0, min(100, score))
        self.score_label.setText(str(score))
        self.score_caption.setText(
            "excellent" if score >= 90 else "good" if score >= 75 else "needs work" if score >= 55 else "poor"
        )

        for check in self.checks[:14]:
            row = QFrame()
            row.setObjectName("Card")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(12, 9, 12, 9)
            layout.setSpacing(10)

            dot = QLabel()
            dot.setPixmap(icon(_CHECK_ICON[check["status"]], _CHECK_COLOR[check["status"]], 18).pixmap(18, 18))
            layout.addWidget(dot)

            text = QVBoxLayout()
            text.setSpacing(1)
            name = QLabel(check["name"])
            nf = QFont()
            nf.setWeight(QFont.Weight.DemiBold)
            name.setFont(nf)
            text.addWidget(name)
            detail = QLabel(check.get("detail", ""))
            detail.setProperty("muted", True)
            detail.setWordWrap(True)
            text.addWidget(detail)
            layout.addLayout(text, 1)

            if check.get("fix"):
                label, page_key = check["fix"]
                button = QPushButton(label)
                button.setFixedWidth(130)
                button.clicked.connect(lambda _c=False, p=page_key: self.ctx.navigate(p))
                layout.addWidget(button)
            layout.addWidget(Badge(check["status"].upper(), _CHECK_COLOR[check["status"]]))
            self.checks_layout.addWidget(row)
        self.checks_layout.addStretch(1)

    # -- live ------------------------------------------------------------
    def _tick(self) -> None:
        stats = systeminfo.live_stats()
        self.stat_cpu.set_value(f"{stats['cpu']:.0f}%", f"{stats['procs']} processes", percent=int(stats["cpu"]))
        self.stat_ram.set_value(f"{stats['ram']:.0f}%", "in use", percent=int(stats["ram"]))
        try:
            volumes = disks.volumes()
            if volumes:
                vol = volumes[0]
                self.stat_disk.set_value(vol.free_text, f"{vol.drive} {vol.used_pct}% used", percent=vol.used_pct)
        except Exception:
            pass

    def _elevate(self) -> None:
        if self.ctx.elevate():
            self.status("Relaunching with administrator rights…")

    def _on_error(self, message: str) -> None:
        self.progress.stop("checks failed")
        self.ctx.log(message, "error")
