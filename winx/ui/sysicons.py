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

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QStyle

from ..core import platform as pf

_ICON_CACHE: dict[str, QIcon] = {}
_STANDARD_CACHE: dict[str, QIcon] = {}

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


def page_icon(key: str) -> QIcon:
    pixmap = PAGE_PIXMAPS.get(key)
    return standard_icon(pixmap) if pixmap else QIcon()


def status_icon(status: str) -> QIcon:
    return standard_icon(STATUS_PIXMAP.get(status, QStyle.StandardPixmap.SP_MessageBoxInformation))


def generic_app_icon() -> QIcon:
    return standard_icon(QStyle.StandardPixmap.SP_FileIcon)


def drive_icon() -> QIcon:
    return standard_icon(QStyle.StandardPixmap.SP_DriveHDIcon)


def file_icon(path: str, size: int = 32) -> QIcon:
    """The shell icon for ``path``; an empty icon when there isn't one.

    Results are cached: pulling an icon out of an executable costs a handful of
    syscalls and the uninstaller asks for hundreds of them.
    """
    if not path:
        return QIcon()
    cached = _ICON_CACHE.get(path)
    if cached is not None:
        return cached

    icon = QIcon()
    lower = path.lower()
    try:
        if lower.endswith((".png", ".jpg", ".jpeg", ".bmp")) and os.path.isfile(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                icon = QIcon(
                    pixmap.scaled(
                        QSize(size, size),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        elif pf.IS_WINDOWS and os.path.exists(path):
            icon = _win_shell_icon(path, size)
    except Exception:  # noqa: BLE001 - an icon is never worth an exception
        icon = QIcon()

    _ICON_CACHE[path] = icon
    return icon


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
