# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT, BUNDLE

block_cipher = None

a = Analysis(
    ['aoi2list_gui.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=['requests'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AOI2List',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,               # GUI app, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AOI2List',
)

app = BUNDLE(
    coll,
    name='AOI2List.app',
    icon='AOI2List.icns',
    bundle_identifier='org.techbill.aoi2list',
    info_plist={
        "CFBundleName": "AOI2List",
        "CFBundleDisplayName": "AOI2List",
        "CFBundleIdentifier": "org.techbill.aoi2list",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "CFBundleGetInfoString": "AOI2List – USGS LiDAR AOI Tile Finder & LAZ Downloader",
        "NSHumanReadableCopyright": "© 2025 Bill Fleming",
    },
)
