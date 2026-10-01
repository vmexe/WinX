"""Icons taken from the operating system — nothing is drawn by WinX.

Three sources, in order of preference:

* :func:`file_icon` asks the Windows shell for the icon of a real file
  (``SHGetFileInfoW``), which is how Explorer renders programs. PNG logos
  (Store apps) are loaded directly.
* :func:`standard_icon` uses the current Qt style's standard pixmaps, which map
  to the platform's own icon theme.
* Everything falls back to an empty icon rather than a drawn placeholder.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QStyle

from ..core import platform as pf

_ICON_CACHE: dict[str, QIcon] = {}
_STANDARD_CACHE: dict[str, QIcon] = {}
_PAGE_CACHE: dict[str, QIcon] = {}

#: page key -> a Windows program whose icon already means that thing.
#: These are the icons Windows itself uses, so they look modern on Windows 11
#: and there is nothing for WinX to draw. Missing files simply fall through to
#: the style's standard pixmap below.
WINDOWS_PAGE_ICONS = {
    "dashboard": r"%SystemRoot%\System32\Taskmgr.exe",
    "systeminfo": r"%SystemRoot%\System32\msinfo32.exe",
    "cleaner": r"%SystemRoot%\System32\cleanmgr.exe",
    "apps": r"%SystemRoot%\System32\appwiz.cpl",
    "disks": r"%SystemRoot%\System32\dfrgui.exe",
    "performance": r"%SystemRoot%\System32\SystemPropertiesPerformance.exe",
    "gaming": r"%SystemRoot%\System32\joy.cpl",
    "startup": r"%SystemRoot%\System32\msconfig.exe",
    "repair": r"%SystemRoot%\System32\rstrui.exe",
    "network": r"%SystemRoot%\System32\ncpa.cpl",
    "drivers": r"%SystemRoot%\System32\hdwwiz.exe",
    "privacy": r"%SystemRoot%\System32\UserAccountControlSettings.exe",
    "security": r"%SystemRoot%\System32\SecurityHealthSystray.exe",
    "interface": r"%SystemRoot%\System32\desk.cpl",
    "tools": r"%SystemRoot%\System32\control.exe",
    "updater": r"%SystemRoot%\System32\MusNotification.exe",
    "settings": r"%SystemRoot%\ImmersiveControlPanel\SystemSettings.exe",
}

#: page key -> a standard pixmap that fits it
PAGE_PIXMAPS = {
    "dashboard": QStyle.StandardPixmap.SP_ComputerIcon,
    "systeminfo": QStyle.StandardPixmap.SP_DesktopIcon,
    "cleaner": QStyle.StandardPixmap.SP_TrashIcon,
    "apps": QStyle.StandardPixmap.SP_DirHomeIcon,
    "disks": QStyle.StandardPixmap.SP_DriveHDIcon,
    "performance": QStyle.StandardPixmap.SP_MediaSeekForward,
    "gaming": QStyle.StandardPixmap.SP_MediaPlay,
    "startup": QStyle.StandardPixmap.SP_BrowserReload,
    "repair": QStyle.StandardPixmap.SP_DialogResetButton,
    "network": QStyle.StandardPixmap.SP_DriveNetIcon,
    "drivers": QStyle.StandardPixmap.SP_DriveDVDIcon,
    "privacy": QStyle.StandardPixmap.SP_DialogDiscardButton,
    "security": QStyle.StandardPixmap.SP_VistaShield,
    "interface": QStyle.StandardPixmap.SP_DesktopIcon,
    "tools": QStyle.StandardPixmap.SP_FileDialogDetailedView,
    "settings": QStyle.StandardPixmap.SP_FileDialogListView,
    "updater": QStyle.StandardPixmap.SP_ArrowDown,
}

STATUS_PIXMAP = {
    "ok": QStyle.StandardPixmap.SP_DialogApplyButton,
    "info": QStyle.StandardPixmap.SP_MessageBoxInformation,
    "warn": QStyle.StandardPixmap.SP_MessageBoxWarning,
    "fail": QStyle.StandardPixmap.SP_MessageBoxCritical,
}


def standard_icon(pixmap: QStyle.StandardPixmap) -> QIcon:
    """An icon from the current platform style."""
    key = str(pixmap)
    cached = _STANDARD_CACHE.get(key)
    if cached is not None:
        return cached
    app = QApplication.instance()
    icon = app.style().standardIcon(pixmap) if app else QIcon()
    _STANDARD_CACHE[key] = icon
    return icon


def page_icon(key: str, size: int = 24) -> QIcon:
    """The navigation icon for a page: Windows' own, or the style's."""
    cached = _PAGE_CACHE.get(key)
    if cached is not None:
        return cached
    icon = QIcon()
    if pf.IS_WINDOWS:
        source = os.path.expandvars(WINDOWS_PAGE_ICONS.get(key, ""))
        if source and os.path.exists(source):
            icon = file_icon(source, size)
    if icon.isNull():
        pixmap = PAGE_PIXMAPS.get(key)
        icon = standard_icon(pixmap) if pixmap else QIcon()
    _PAGE_CACHE[key] = icon
    return icon


def status_icon(status: str) -> QIcon:
    return standard_icon(STATUS_PIXMAP.get(status, QStyle.StandardPixmap.SP_MessageBoxInformation))


def generic_app_icon() -> QIcon:
    return standard_icon(QStyle.StandardPixmap.SP_FileIcon)


def drive_icon() -> QIcon:
    return standard_icon(QStyle.StandardPixmap.SP_DriveHDIcon)


def file_icon(path: str, size: int = 32) -> QIcon:
    """The shell icon for ``path``; an empty icon when there isn't one.

    ``path`` may carry a resource index the way the registry writes it
    (``C:\\app\\app.exe,2`` or ``…\\shell32.dll,-16``), in which case that
    specific icon is extracted. Results are cached: pulling an icon out of an
    executable costs a handful of syscalls and the Uninstaller asks for
    hundreds of them.
    """
    if not path:
        return QIcon()
    cached = _ICON_CACHE.get(path)
    if cached is not None:
        return cached

    path, index = _split_index(path)
    icon = QIcon()
    lower = path.lower()
    try:
        if index and pf.IS_WINDOWS and os.path.exists(path):
            icon = _win_extract_icon(path, index, size)
        if icon.isNull() and lower.endswith((".ico",)) and os.path.isfile(path):
            icon = QIcon(path)
        if icon.isNull() and lower.endswith((".png", ".jpg", ".jpeg", ".bmp")) and os.path.isfile(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                icon = QIcon(
                    pixmap.scaled(
                        QSize(size, size),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        if icon.isNull() and pf.IS_WINDOWS and os.path.exists(path):
            icon = _win_shell_icon(path, size)
    except Exception:  # noqa: BLE001 - an icon is never worth an exception
        icon = QIcon()

    _ICON_CACHE[path] = icon
    return icon


def _split_index(spec: str) -> tuple[str, int]:
    """``"C:\\a.exe,3"`` -> ``("C:\\a.exe", 3)``."""
    head, _sep, tail = (spec or "").rpartition(",")
    stripped = tail.strip()
    if head and stripped.lstrip("-").isdigit():
        return head.strip().strip('"'), int(stripped)
    return (spec or "").strip().strip('"'), 0


def _win_extract_icon(path: str, index: int, size: int) -> QIcon:  # pragma: no cover - Windows
    """One specific icon out of an .exe/.dll resource table."""
    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.windll.shell32
    large = wintypes.HICON()
    small = wintypes.HICON()
    # a negative index is a resource *id*, which ExtractIconEx understands
    count = shell32.ExtractIconExW(
        ctypes.c_wchar_p(path), int(index), ctypes.byref(large), ctypes.byref(small), 1
    )
    if not count:
        return QIcon()
    handle = large.value if (size > 16 and large.value) else (small.value or large.value)
    try:
        image = _hicon_to_image(handle) if handle else None
    finally:
        for other in (large.value, small.value):
            if other:
                ctypes.windll.user32.DestroyIcon(other)
    if image is None or image.isNull():
        return QIcon()
    return QIcon(QPixmap.fromImage(image))


def _win_shell_icon(path: str, size: int) -> QIcon:  # pragma: no cover - Windows only
    """SHGetFileInfoW -> HICON -> QImage."""
    import ctypes
    from ctypes import wintypes

    SHGFI_ICON = 0x000000100
    SHGFI_LARGEICON = 0x000000000
    SHGFI_SMALLICON = 0x000000001

    class SHFILEINFOW(ctypes.Structure):
        _fields_ = [
            ("hIcon", wintypes.HICON),
            ("iIcon", ctypes.c_int),
            ("dwAttributes", wintypes.DWORD),
            ("szDisplayName", wintypes.WCHAR * 260),
            ("szTypeName", wintypes.WCHAR * 80),
        ]

    info = SHFILEINFOW()
    flags = SHGFI_ICON | (SHGFI_LARGEICON if size > 16 else SHGFI_SMALLICON)
    result = ctypes.windll.shell32.SHGetFileInfoW(
        ctypes.c_wchar_p(path), 0, ctypes.byref(info), ctypes.sizeof(info), flags
    )
    if not result or not info.hIcon:
        return QIcon()
    try:
        image = _hicon_to_image(info.hIcon)
    finally:
        ctypes.windll.user32.DestroyIcon(info.hIcon)
    return QIcon(QPixmap.fromImage(image)) if image is not None and not image.isNull() else QIcon()


def _hicon_to_image(hicon) -> QImage | None:  # pragma: no cover - Windows only
    """Copy an HICON's 32-bit bitmap into a QImage."""
    import ctypes
    from ctypes import wintypes

    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", wintypes.BOOL),
            ("xHotspot", wintypes.DWORD),
            ("yHotspot", wintypes.DWORD),
            ("hbmMask", wintypes.HBITMAP),
            ("hbmColor", wintypes.HBITMAP),
        ]

    class BITMAP(ctypes.Structure):
        _fields_ = [
            ("bmType", ctypes.c_long),
            ("bmWidth", ctypes.c_long),
            ("bmHeight", ctypes.c_long),
            ("bmWidthBytes", ctypes.c_long),
            ("bmPlanes", ctypes.c_ushort),
            ("bmBitsPixel", ctypes.c_ushort),
            ("bmBits", ctypes.c_void_p),
        ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long),
            ("biPlanes", ctypes.c_ushort),
            ("biBitCount", ctypes.c_ushort),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    gdi32, user32 = ctypes.windll.gdi32, ctypes.windll.user32
    info = ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(info)):
        return None
    try:
        bitmap = BITMAP()
        gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bitmap), ctypes.byref(bitmap))
        width, height = int(bitmap.bmWidth), int(bitmap.bmHeight)
        if width <= 0 or height <= 0:
            return None

        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth = width
        header.biHeight = -height          # top-down
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0           # BI_RGB

        buffer = ctypes.create_string_buffer(width * height * 4)
        hdc = user32.GetDC(0)
        try:
            copied = gdi32.GetDIBits(
                hdc, info.hbmColor, 0, height, buffer, ctypes.byref(header), 0
            )
        finally:
            user32.ReleaseDC(0, hdc)
        if not copied:
            return None
        image = QImage(buffer.raw, width, height, QImage.Format.Format_ARGB32)
        return image.copy()                # detach from the temporary buffer
    finally:
        if info.hbmColor:
            gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            gdi32.DeleteObject(info.hbmMask)


class IconLoader(QObject):
    """Fill in real icons a few rows at a time, without blocking the window.

    Asking the shell for an icon is cheap; asking it four hundred times in one
    go is half a second of frozen UI. Rows get a placeholder immediately and
    their real icon on later turns of the event loop.
    """

    CHUNK = 16

    def __init__(self, parent=None, size: int = 32):
        super().__init__(parent)
        self.size = size
        self._queue: list[tuple[object, str]] = []
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._tick)

    def load(self, pairs) -> None:
        """``pairs`` is an iterable of ``(QTreeWidgetItem, path)``."""
        self._queue = [(item, path) for item, path in pairs if path]
        if self._queue:
            self._timer.start()
        else:
            self._timer.stop()

    def stop(self) -> None:
        self._queue.clear()
        self._timer.stop()

    def _tick(self) -> None:
        for _ in range(self.CHUNK):
            if not self._queue:
                self._timer.stop()
                return
            item, path = self._queue.pop()
            icon = file_icon(path, self.size)
            if icon.isNull():
                continue
            try:
                item.setIcon(0, icon)
            except RuntimeError:               # the row was replaced
                continue
