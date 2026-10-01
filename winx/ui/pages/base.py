"""Base class shared by the content pages."""

from __future__ import annotations

import time

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget

from ..context import AppContext


def age_text(seconds: float) -> str:
    """``90`` -> ``'1 minute ago'``."""
    seconds = int(max(0, seconds))
    if seconds < 10:
        return "just now"
    if seconds < 90:
        return f"{seconds} seconds ago"
    minutes = seconds // 60
    if minutes < 90:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    return f"{hours} hour{'s' if hours != 1 else ''} ago"


class Page(QWidget):
    """Common plumbing: a description line, lazy refresh and page metadata."""

    key = "page"
    title = "Page"
    subtitle = ""
    #: seconds a scan stays usable before the page reloads it on its own.
    #: 0 keeps the cached result until something invalidates it.
    cache_ttl = 600.0

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self._loaded = False
        self._dirty = True
        self._loaded_at = 0.0
        self.updated_label: QLabel | None = None

        self.layout_ = QVBoxLayout(self)
        if self.subtitle:
            caption = QLabel(self.subtitle)
            caption.setWordWrap(True)
            self.layout_.addWidget(caption)

    # -- lifecycle -------------------------------------------------------
    def on_show(self) -> None:
        """Called by the main window each time the page becomes visible.

        Scans are expensive (the uninstaller alone takes seconds), so a page
        that already holds a result reuses it instead of re-scanning. Use
        *Refresh* — or wait for :attr:`cache_ttl` — to read the system again.
        """
        if self._dirty or not self._loaded or self._cache_expired():
            self._dirty = False
            self._loaded = True
            try:
                self.refresh()
            except Exception as exc:  # noqa: BLE001 - a page must never take the app down
                self._loaded = False
                self.on_error(f"{self.title}: {exc}")
        else:
            self.update_cache_label()

    def _cache_expired(self) -> bool:
        if not self.cache_ttl or not self._loaded_at:
            return False
        return (time.time() - self._loaded_at) > self.cache_ttl

    def invalidate(self) -> None:
        self._dirty = True

    # -- cache bookkeeping -----------------------------------------------
    def mark_loaded(self) -> None:
        """Pages call this once their data has arrived."""
        self._loaded_at = time.time()
        self._loaded = True
        self._dirty = False
        self.update_cache_label()

    def cache_text(self) -> str:
        if not self._loaded_at:
            return ""
        return f"Updated {age_text(time.time() - self._loaded_at)}"

    def update_cache_label(self) -> None:
        if self.updated_label is not None:
            self.updated_label.setText(self.cache_text())

    def cache_row(self, refresh_text: str = "Refresh") -> QHBoxLayout:
        """A reusable 'Updated 2 minutes ago   [Refresh]' row."""
        row = QHBoxLayout()
        self.updated_label = QLabel("")
        self.updated_label.setEnabled(False)
        row.addWidget(self.updated_label)
        row.addStretch(1)
        button = QPushButton(refresh_text)
        button.clicked.connect(self.force_refresh)
        row.addWidget(button)
        self.refresh_button = button
        return row

    def force_refresh(self) -> None:
        """Discard the cached result and read the system again."""
        self._dirty = True
        self.on_show()

    def refresh(self) -> None:  # pragma: no cover - overridden
        pass

    # -- helpers ---------------------------------------------------------
    def log(self, text: str, level: str = "info") -> None:
        self.ctx.log(text, level)

    def status(self, text: str) -> None:
        self.ctx.status(text)

    def on_error(self, message: str) -> None:
        """Report a failed background job without losing the detail.

        The status bar gets one short line; the activity log keeps the whole
        traceback so a failure can still be diagnosed afterwards.
        """
        text = (message or "").strip() or "Unknown error"
        lines = text.splitlines()
        self.log(lines[0], "error")
        for extra in lines[1:20]:
            if extra.strip():
                self.log("    " + extra.rstrip(), "error")
        self.status(lines[0][:200])


class TabbedPage(Page):
    """A page made of other pages, one per tab (used by Network and Security)."""

    def __init__(
        self,
        ctx: AppContext,
        key: str,
        title: str,
        subtitle: str,
        tabs: list[tuple[str, Page]],
    ):
        self.key = key
        self.title = title
        self.subtitle = subtitle
        super().__init__(ctx)
        self.sub_pages = [page for _label, page in tabs]

        self.tabs = QTabWidget()
        for label, page in tabs:
            self.tabs.addTab(page, label)
        self.layout_.addWidget(self.tabs, 1)
        self.tabs.currentChanged.connect(self._tab_changed)

    def _tab_changed(self, index: int) -> None:
        page = self.tabs.widget(index)
        if isinstance(page, Page):
            page.on_show()

    def refresh(self) -> None:
        current = self.tabs.currentWidget()
        if isinstance(current, Page):
            current.on_show()
