# -*- coding: utf-8 -*-
"""Сборка одного exe-файла: python build_exe.py

Входной файл — mic_switcher_modern.py (CustomTkinter-UI), который
импортирует всю логику из mic_switcher.py (PyInstaller подхватит его сам).
"""
import base64
import subprocess
import sys

SRC = "mic_switcher_modern.py"
OUT = "mic_switcher_modern_app.py"

# Вшиваем иконку в код, чтобы exe был полностью автономным
b64 = base64.b64encode(open("mic.ico", "rb").read()).decode()
src = open(SRC, encoding="utf-8").read()
marker = 'ICON_B64 = ""'
if marker not in src:
    raise SystemExit("Не найден маркер ICON_B64 в " + SRC)
src = src.replace(marker, 'ICON_B64 = "' + b64 + '"')
with open(OUT, "w", encoding="utf-8") as f:
    f.write(src)

subprocess.run([
    sys.executable, "-m", "PyInstaller",
    "--onefile", "--windowed", "--clean", "--noconfirm",
    "--name", "MicSwitcher",
    "--icon", "mic.ico",
    "--collect-all", "pystray",
    "--collect-all", "customtkinter",
    "--hidden-import", "pystray._win32",
    "--hidden-import", "six",
    "--hidden-import", "PIL.ImageFile",
    OUT,
], check=True)
print("BUILD OK -> dist/MicSwitcher.exe")
