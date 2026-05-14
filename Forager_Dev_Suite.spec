# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

_SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
_SRC_ON_PATH = os.path.join(_SPEC_DIR, 'src')

datas = [
    ('dashboard.py', '.'),
    ('src', 'src'),
    ('scripts', 'scripts'),
    ('theme_rules', 'theme_rules'),
    ('static', 'static'),
    ('.streamlit/config.toml', '.streamlit'),
]
binaries = []
hiddenimports = ['requests']

# Bundle Streamlit and all required assets/submodules explicitly.
hiddenimports += collect_submodules('streamlit')
st_datas, st_bins, st_hidden = collect_all('streamlit')
datas += st_datas
binaries += st_bins
hiddenimports += st_hidden

# dashboard.py is loaded by Streamlit from bundled data, so PyInstaller does
# not statically see imports such as `from PIL import ImageDraw`.
hiddenimports += collect_submodules('PIL')

# Optional pack tile art: web image search (dynamic import in dashboard.py).
hiddenimports += ['ddgs', 'duckduckgo_search']

# pywebview imports as `webview`, not `pywebview`.
hiddenimports += collect_submodules('webview')
wv_datas, wv_bins, wv_hidden = collect_all('webview')
datas += wv_datas
binaries += wv_bins
hiddenimports += wv_hidden

# Include app package modules explicitly.
hiddenimports += collect_submodules('forager_ai')
# Belt-and-suspenders: hub RAG + keyword fallback + pack git cards (real layout under forager_ai.ai).
hiddenimports += [
    'forager_ai.ai.embedding_rag',
    'forager_ai.ai.light_rag',
    'forager_ai.ai.git_context',
    'forager_ai.ai.hub_citations',
    'tomli',
    'tomli_w',
]

a = Analysis(
    ['run_dashboard.py'],
    pathex=[_SRC_ON_PATH],
    binaries=binaries,
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
    a.binaries,
    a.datas,
    [],
    name='Forager_Dev_Suite_v17',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
