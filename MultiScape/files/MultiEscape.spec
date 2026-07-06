# -*- mode: python ; coding: utf-8 -*-
# ============================================================
# Multi Escape ERP — PyInstaller Spec File
# Gerado automaticamente. Execute via construir_exe.bat
# ============================================================

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# ── Detecta se a pasta de logos existe ──────────────────────
pasta_logos = 'logos_marcas'
datas_extras = []
if os.path.isdir(pasta_logos):
    datas_extras.append((pasta_logos, 'logos_marcas'))

# ── Hidden imports necessários ────────────────────────────────
hidden = [
    # tkinter
    'tkinter', 'tkinter.ttk', 'tkinter.messagebox',
    'tkinter.filedialog', 'tkinter.font',
    '_tkinter',
    # banco de dados
    'sqlite3', '_sqlite3', 'pyodbc',
    # sistema
    'threading', 'platform', 'subprocess',
    'urllib', 'urllib.request', 'urllib.error',
    # PIL / Pillow (opcional — não falha se não estiver)
    'PIL', 'PIL.Image', 'PIL.ImageTk',
    'PIL._tkinter_finder',
    # reportlab (opcional)
    'reportlab',
    'reportlab.lib', 'reportlab.lib.pagesizes',
    'reportlab.lib.colors', 'reportlab.lib.units',
    'reportlab.lib.enums', 'reportlab.lib.styles',
    'reportlab.platypus',
    'reportlab.platypus.flowables',
    'reportlab.platypus.paragraph',
    'reportlab.platypus.tables',
    'reportlab.pdfbase', 'reportlab.pdfbase.pdfmetrics',
    'reportlab.pdfbase.ttfonts',
    'reportlab.pdfgen',
    'reportlab.graphics',
]

# Coleta todos os submódulos do reportlab se estiver instalado
try:
    hidden += collect_submodules('reportlab')
except Exception:
    pass

# ── Análise principal ──────────────────────────────────────────
a = Analysis(
    ['sistema_oficina_v2.py'],
    pathex=['.'],
    binaries=[],
    datas=datas_extras,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclui módulos pesados desnecessários
        'numpy', 'pandas', 'matplotlib', 'scipy',
        'IPython', 'jupyter', 'notebook',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'wx', 'gi', 'gtk',
        'test', 'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Executável ─────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MultiEscape_ERP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # comprime com UPX se disponível (reduz tamanho)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # False = sem janela de terminal (modo GUI limpo)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Ícone — descomente e ajuste o caminho se tiver um arquivo .ico
    # icon='icone_multiescap.ico',
    version='versao_info.txt',   # informações de versão do Windows
)
