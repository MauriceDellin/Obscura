# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Spec fuer die Obscura.
# Build:  py -3.13 -m PyInstaller --noconfirm anonymize.spec
# Ergebnis: dist\Obscura-Portable.exe  (eine portable Datei)
#
# Hinweis OCR: pytesseract (Python) wird mitgebündelt, falls installiert.
# Das eigentliche Tesseract-Programm wird NICHT eingebettet – der Code findet
# es zur Laufzeit am Standardpfad C:\Program Files\Tesseract-OCR.

block_cipher = None

a = Analysis(
    ['anonymize_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('app.ico', '.')],                 # Icon ins Bundle (Fenster-Symbol)
    hiddenimports=['PIL._tkinter_finder'],   # fuer PIL.ImageTk im gebündelten Build
    hookspath=[],
    runtime_hooks=[],
    excludes=['numpy', 'scipy', 'matplotlib', 'pandas'],  # nicht benoetigt -> kleiner
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Obscura-Portable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # GUI-App, kein Konsolenfenster
    disable_windowed_traceback=False,
    icon='app.ico',
    version='version_info.txt',
)
