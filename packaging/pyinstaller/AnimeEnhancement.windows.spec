# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
ICON = ROOT / "packaging" / "windows" / "assets" / "anime_enhancement.ico"


def add_tree(source: Path, target: str):
    if not source.exists():
        return []
    items = []
    for path in source.rglob("*"):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_file():
            destination = Path(target) / path.relative_to(source).parent
            items.append((str(path), str(destination)))
    return items


datas = [
    (str(ROOT / "gui" / "styles.qss"), "gui"),
]
datas += add_tree(ROOT / "src" / "utils", "src/utils")
datas += add_tree(ROOT / "assets" / "branding", "assets/branding")
datas += add_tree(ROOT / "packaging" / "windows" / "assets", "packaging/windows/assets")

hiddenimports = collect_submodules("src") + collect_submodules("gui")

common = dict(
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

a_gui = Analysis([str(ROOT / "gui" / "app.py")], **common)
pyz_gui = PYZ(a_gui.pure)
exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="AnimeEnhancement",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ICON) if ICON.exists() else None,
)

a_cli = Analysis([str(ROOT / "main.py")], **common)
pyz_cli = PYZ(a_cli.pure)
exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="AnimeEnhancementCLI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=str(ICON) if ICON.exists() else None,
)

coll = COLLECT(
    exe_gui,
    exe_cli,
    a_gui.binaries,
    a_gui.datas,
    a_cli.binaries,
    a_cli.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AnimeEnhancement",
)
