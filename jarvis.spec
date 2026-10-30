# -*- mode: python ; coding: utf-8 -*-
"""Especificação PyInstaller do JARVIS (distribuição one-dir)."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(ROOT / "assets" / "jarvis.ico"), "assets"),
    (str(ROOT / "assets" / "jarvis.png"), "assets"),
]
binaries = []
hiddenimports = []

# Bibliotecas com metadados, drivers e binários próprios.
for package in (
    "webview",
    "pyttsx3",
    "comtypes",
    "pycaw",
    "speech_recognition",
    "edge_tts",
    "pygame",
    "pythonnet",
):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
    except Exception:
        continue
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

hiddenimports += collect_submodules("backend")
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "win32com",
    "win32com.client",
    "pythoncom",
    "pywintypes",
]

# Não leve testes, exemplos ou documentação de bibliotecas para o executável.
EXCLUDED_PREFIXES = (
    "pygame.tests",
    "pygame.examples",
    "pygame.docs",
    "pygame.__pyinstaller",
    "comtypes.test",
    "speech_recognition.cli",
    "speech_recognition.__main__",
    "edge_tts.__main__",
)
hiddenimports = [
    module for module in hiddenimports if not module.startswith(EXCLUDED_PREFIXES)
]

a = Analysis(
    [str(ROOT / "run_jarvis.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tests",
        "pytest",
        "ruff",
        "tkinter",
        "pygame.tests",
        "pygame.examples",
        "pygame.docs",
        "comtypes.test",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JARVIS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "jarvis.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="JARVIS",
)
