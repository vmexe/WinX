"""System information: a plain, copyable inventory of the machine."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
)

from ...core.format import human_size
from ...core.workers import submit
from ...modules import disks, systeminfo
from ..context import AppContext
from ..widgets import ProgressRow
from .base import Page


class SystemInfoPage(Page):
    key = "systeminfo"
    title = "System"
    subtitle = "Hardware, operating system and network details."
    cache_ttl = 900.0

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.info: dict = {}

        self.layout_.addLayout(self.cache_row("Re-read"))

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Item", "Value"])
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.layout_.addWidget(self.tree, 1)

        self.progress = ProgressRow()
        self.layout_.addWidget(self.progress)

        buttons = QHBoxLayout()
        # the "Refresh" button next to the "Updated …" line is the only one:
        # a second copy down here was just noise
        self.btn_refresh = self.refresh_button
        self.btn_copy = QPushButton("Copy report")
        self.btn_copy.clicked.connect(self._copy)
        buttons.addWidget(self.btn_copy)
        buttons.addStretch(1)
        self.layout_.addLayout(buttons)

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        self.btn_refresh.setEnabled(False)
        self.progress.start("Collecting system information…")
        worker = submit(self._load)
        worker.signals.progress.connect(lambda d, t, m: self.progress.set(d, t, m or "Querying…"))
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_failed)

    def _load(self, progress=None):
        info = systeminfo.snapshot(progress=progress)
        # snapshot() does not enumerate volumes; the Disks module does
        try:
            info["disks"] = [
                {
                    "name": f"{v.drive} {v.label}".strip(),
                    "detail": f"{v.fs} · {v.total_text} total · {v.free_text} free"
                    + (f" · {v.media}" if v.media else ""),
                }
                for v in disks.volumes()
            ]
        except Exception:  # noqa: BLE001 - inventory must still render
            info["disks"] = []
        return info

    def _on_failed(self, message: str) -> None:
        self.btn_refresh.setEnabled(True)
        self.progress.stop("Could not read system information")
        self.on_error(message)

    def _on_loaded(self, info: dict) -> None:
        self.btn_refresh.setEnabled(True)
        self.info = info
        self.progress.stop("")
        self.tree.clear()

        cpu = info.get("cpu") or {}
        memory = info.get("memory") or {}
        board = info.get("motherboard") or {}
        battery = info.get("battery") or {}

        self._group(
            "Operating system",
            [
                ("Edition", info.get("os", "")),
                ("Computer name", info.get("computer", "")),
                ("Signed in as", info.get("user", "")),
                ("Activation", info.get("activation", "")),
            ],
        )
        self._group(
            "Processor",
            [
                ("Model", cpu.get("name", "")),
                ("Cores / threads", f"{cpu.get('cores', '?')} / {cpu.get('threads', '?')}"),
                ("Base / current clock", f"{cpu.get('freq_max', 0)} GHz / {cpu.get('freq_cur', 0)} GHz"),
            ],
        )
        self._group(
            "Memory",
            [
                ("Installed", human_size(memory.get("total", 0))),
                ("In use", f"{human_size(memory.get('used', 0))} ({memory.get('percent', 0)}%)"),
                ("Available", human_size(memory.get("available", 0))),
            ],
        )
        self._group(
            "Motherboard",
            [
                ("Manufacturer", board.get("manufacturer", "")),
                ("Model", board.get("product", "")),
                ("BIOS", board.get("bios", "")),
                ("Serial", board.get("serial", "")),
            ],
        )

        gpus = info.get("gpu") or []
        self._group(
            "Graphics",
            [
                (gpu.get("name", f"GPU {i + 1}"),
                 " · ".join(x for x in (gpu.get("memory", ""), gpu.get("driver", ""), gpu.get("resolution", "")) if x))
                for i, gpu in enumerate(gpus)
            ],
        )

        self._group(
            "Disks",
            [
                (d.get("name", ""), d.get("detail", ""))
                for d in (info.get("disks") or [])
            ],
        )

        self._group(
            "Network",
            [
                (n.get("name", ""),
                 " · ".join(x for x in (n.get("type", ""), n.get("ip", ""), n.get("mac", ""), n.get("speed", "")) if x))
                for n in (info.get("network") or [])
            ],
        )

        if battery.get("present"):
            self._group(
                "Battery",
                [
                    ("Charge", f"{battery.get('percent', 0)}%"),
                    ("Power", "plugged in" if battery.get("plugged") else "on battery"),
                    ("Remaining", battery.get("remaining", "—")),
                ],
            )

        monitors = info.get("monitors") or []
        if monitors:
            self._group(
                "Monitors",
                [
                    (m.get("name", f"Display {i + 1}"),
                     " · ".join(x for x in (m.get("resolution", ""), m.get("refresh", "")) if x))
                    for i, m in enumerate(monitors)
                ],
            )

        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        self.status("System information updated")
        self.mark_loaded()

    def _group(self, title: str, rows: list[tuple[str, str]]) -> None:
        if not rows:
            return
        parent = QTreeWidgetItem([title, ""])
        for name, value in rows:
            parent.addChild(QTreeWidgetItem([str(name), str(value)]))
        self.tree.addTopLevelItem(parent)

    def _copy(self) -> None:
        lines: list[str] = []
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            lines.append(group.text(0))
            for j in range(group.childCount()):
                child = group.child(j)
                lines.append(f"    {child.text(0)}: {child.text(1)}")
            lines.append("")
        QApplication.clipboard().setText("\n".join(lines))
        self.status("Report copied to the clipboard")
