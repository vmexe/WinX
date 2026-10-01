"""System Information page — a hardware and OS inventory with export."""

from __future__ import annotations

import datetime as dt
import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ...core.format import human_duration, human_size
from ...core.workers import submit
from ...modules import systeminfo
from ..context import AppContext
from ..icons import icon
from ..widgets import LogConsole, ProgressRow, StatCard
from .base import Page


class SystemInfoPage(Page):
    key = "systeminfo"
    title = "System"
    subtitle = "A full inventory of the machine you are sitting in front of."
    icon_name = "monitor"

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.info: dict = {}
        self._build()

    def _build(self) -> None:
        layout = self.content_layout
        header = QHBoxLayout()
        heading = QLabel("System")
        font = QFont()
        font.setPointSize(18)
        font.setWeight(QFont.Weight.Bold)
        heading.setFont(font)
        header.addWidget(heading)
        header.addStretch(1)
        self.btn_refresh = QPushButton(" Refresh")
        self.btn_refresh.setIcon(icon("refresh", self.ctx.accent, 16))
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_copy = QPushButton("Copy report")
        self.btn_copy.clicked.connect(self._copy)
        self.btn_save = QPushButton("Save report…")
        self.btn_save.clicked.connect(self._save)
        header.addWidget(self.btn_refresh)
        header.addWidget(self.btn_copy)
        header.addWidget(self.btn_save)
        layout.addLayout(header)

        sub = QLabel(self.subtitle)
        sub.setProperty("muted", True)
        layout.addWidget(sub)

        self.stats_row = QHBoxLayout()
        self.stats_row.setSpacing(10)
        layout.addLayout(self.stats_row)

        self.grid = QGridLayout()
        self.grid.setSpacing(10)
        layout.addLayout(self.grid, 1)

        self.progress = ProgressRow()
        layout.addWidget(self.progress)
        self.console = LogConsole(placeholder="Hardware queries are logged here…")
        self.console.setFixedHeight(100)
        layout.addWidget(self.console)

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self.progress.start("Collecting system information…")
        worker = submit(self._load)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m or "Querying…"))
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_error)

    def _load(self, progress=None):
        return systeminfo.snapshot(progress=progress)

    def _on_loaded(self, info: dict) -> None:
        self.info = info
        self.progress.stop("System information collected")
        self._render(info)
        self.status("System information refreshed")

    def _render(self, info: dict) -> None:
        self._clear(self.stats_row)
        self._clear(self.grid)

        cpu = info.get("cpu") or {}
        mem = info.get("memory") or {}
        uptime = human_duration(dt.datetime.now().timestamp() - (info.get("boot_time") or dt.datetime.now().timestamp()))

        stats = [
            ("Processor", (cpu.get("name") or "Unknown")[:34], f"{cpu.get('cores', '?')} cores / {cpu.get('threads', '?')} threads", "chip"),
            ("Memory", human_size(mem.get("total", 0)), f"{mem.get('percent', 0):.0f}% used", "spark"),
            ("Uptime", uptime, "since last boot", "clock"),
            ("Graphics", (info.get("gpu") or [{}])[0].get("name", "Unknown") or "Unknown", (info.get("gpu") or [{}])[0].get("driver", ""), "monitor"),
        ]
        for label, value, sub, icon_name in stats:
            card = StatCard(label, value, sub, icon_name)
            self.stats_row.addWidget(card)

        sections: list[tuple[str, list[tuple[str, str]]]] = []

        sections.append(
            (
                "Operating system",
                [
                    ("Edition", info.get("os", "")),
                    ("Activation", info.get("activation", "")),
                    ("Computer name", info.get("computer", "")),
                    ("Signed-in user", info.get("user", "")),
                    ("Last boot", _boot_text(info.get("boot_time"))),
                ],
            )
        )

        cpu_rows = [
            ("CPU", cpu.get("name", "")),
            ("Cores / threads", f"{cpu.get('cores', '?')} / {cpu.get('threads', '?')}"),
            ("Base / current clock", f"{cpu.get('freq_max', 0)} GHz" + (f" / {cpu.get('freq_cur', 0)} GHz" if cpu.get("freq_cur") else "")),
        ]
        sections.append(("Processor", cpu_rows))

        mem_rows = [
            ("Installed RAM", human_size(mem.get("total", 0))),
            ("Available", human_size(mem.get("available", 0))),
            ("In use", f"{mem.get('percent', 0):.0f}%"),
        ]
        sections.append(("Memory", mem_rows))

        board = info.get("motherboard") or {}
        sections.append(
            (
                "Motherboard",
                [
                    ("Manufacturer", board.get("manufacturer", "")),
                    ("Model", board.get("product", "")),
                    ("BIOS", board.get("bios", "")),
                    ("Serial", board.get("serial", "")),
                ],
            )
        )

        gpu_rows = []
        for gpu in info.get("gpu") or []:
            gpu_rows.append((gpu.get("name", "Unknown"), f"{gpu.get('driver','')}  {gpu.get('memory','')}".strip()))
        sections.append(("Graphics", gpu_rows or [("—", "no display adapter reported")]))

        net_rows = []
        for adapter in info.get("network") or []:
            net_rows.append((adapter.get("name", ""), f"{adapter.get('ip','')} · {adapter.get('mac','')} · {adapter.get('speed','')}".strip(" ·")))
        sections.append(("Network", net_rows or [("—", "no active adapter")]))

        battery = info.get("battery") or {}
        if battery.get("present"):
            sections.append(
                (
                    "Battery",
                    [
                        ("Charge", f"{battery.get('percent', 0)}%"),
                        ("Status", "Charging" if battery.get("plugged") else "On battery"),
                        ("Time remaining", str(battery.get("remaining", "—"))),
                    ],
                )
            )

        row = 0
        col = 0
        for title, rows in sections:
            card = QFrame()
            card.setObjectName("Card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            cl.setSpacing(6)
            label = QLabel(title.upper())
            lf = QFont()
            lf.setPointSize(8)
            lf.setWeight(QFont.Weight.Bold)
            label.setFont(lf)
            label.setProperty("muted", True)
            cl.addWidget(label)
            for key, value in rows:
                hl = QHBoxLayout()
                hl.setSpacing(8)
                k = QLabel(str(key))
                k.setProperty("muted", True)
                k.setMinimumWidth(130)
                v = QLabel(str(value) or "—")
                v.setWordWrap(True)
                v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                hl.addWidget(k)
                hl.addWidget(v, 1)
                cl.addLayout(hl)
            cl.addStretch(1)
            self.grid.addWidget(card, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

    def _clear(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                self._clear(item.layout())

    # -- export ----------------------------------------------------------
    def report_text(self) -> str:
        lines = ["WinX system report", "=" * 60, ""]
        for key, value in self.info.items():
            if isinstance(value, (list, dict)):
                value = json.dumps(value, indent=2, default=str)
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.report_text())
        self.status("Report copied to clipboard")

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save system report", "winx-system-report.txt", "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.report_text())
            self.status(f"Report saved to {path}")

    def _on_error(self, message: str) -> None:
        self.progress.stop("failed")
        self.log(message, "error")


def _boot_text(ts: float | None) -> str:
    if not ts:
        return "—"
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
