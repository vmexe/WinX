# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a single-file WinX.exe.

    pyinstaller build/WinX.spec --noconfirm --clean

Paths inside a spec are resolved relative to the *spec's* directory, so the
project root is derived from SPECPATH rather than the current directory.
"""

import os

from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = os.path.abspath(SPECPATH)
ROOT = os.path.dirname(SPEC_DIR)

hiddenimports = [
    *collect_submodules("winx"),
    "psutil",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtNetwork",
]

excludes = [
    "tkinter",
    "unittest",
    "pydoc",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.Qt3DCore",
    "PySide6.QtMultimedia",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(ROOT, "assets"), "assets")],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WinX",
    icon=os.path.join(ROOT, "assets", "winx.ico"),
    version=os.path.join(ROOT, "build", "version_info.txt"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python3.dll", "qwindows.dll"],
    runtime_tmpdir=None,
    console=False,          # GUI app: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,        # WinX asks for elevation itself, when needed
)
