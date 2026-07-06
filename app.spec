# -*- mode: python ; coding: utf-8 -*-
# PyInstaller — Sistema Logístico Integrado (rede + desktop)

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('database', 'database'),
    ],
    hiddenimports=[
        'modulos_portal',
        'modulo_roteirizador',
        'modulo_cep_ibge',
        'pandas',
        'openpyxl',
        'requests',
        'webview',
        'pyodbc',
        'database_adapter',
    ],
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
    name='SistemaLogistico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
