# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
ICON = ROOT / "packaging" / "macos" / "assets" / "anime_enhancement.icns"


def add_tree(source: Path, target: str):
    if not source.exists():
        return []
    items = []
    for path in source.rglob("*"):
        if path.is_file():
            destination = Path(target) / path.relative_to(source).parent
            items.append((str(path), str(destination)))
    return items


datas = [(str(ROOT / "gui" / "styles.qss"), "gui")]
datas += add_tree(ROOT / "src" / "utils", "src/utils")
datas += add_tree(ROOT / "assets" / "branding", "assets/branding")
datas += add_tree(ROOT / "packaging" / "macos" / "assets", "packaging/macos/assets")

hiddenimports = collect_submodules("src") + collect_submodules("gui")

a = Analysis(
    [str(ROOT / "gui" / "app.py")],
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
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AnimeEnhancement",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AnimeEnhancement",
)
app = BUNDLE(
    coll,
    name="AnimeEnhancement.app",
    icon=str(ICON) if ICON.exists() else None,
    bundle_identifier="com.anime-enhancement.app",
)
