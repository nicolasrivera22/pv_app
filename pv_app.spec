# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# spec_path = Path(SPECPATH).resolve()
# project_root = spec_path.parent
project_root = Path(SPECPATH).resolve()


datas = [
    (str(project_root / "assets"), "assets"),
    (str(project_root / "pages"), "pages"),
    (str(project_root / "PV_inputs.xlsx"), "."),
    # Optional documentation bundle for trial distributions
    (str(project_root / "README.md"), "."),
    (str(project_root / "DEVELOPER_NOTES.md"), "."),
    (str(project_root / "GUIA_USUARIO.md"), "."),
    (str(project_root / "PVWorkbench_Guia_Rapida.html"), "."),
] + collect_data_files("dash_cytoscape")

hiddenimports = [
    *collect_submodules("pages"),
    "services.workspace_shared_callbacks",
    "services.workspace_admin_callbacks",
    "services.workspace_assumptions_callbacks",
    "services.workspace_results_callbacks",
]


a = Analysis(
    ["desktop_launcher.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PVWorkbench",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PVWorkbench",
)
