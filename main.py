# -*- coding: utf-8 -*-
"""
main.py - Punto de entrada de Umbral Guardian
Sistema de Seguridad Inteligente
Ejecutar: python main.py
"""

import os
import sys

# Asegurar que el directorio raíz esté en el path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import tkinter as tk
from tkinter import messagebox


def check_dependencies() -> list[str]:
    """Verifica que las dependencias críticas estén instaladas."""
    missing = []
    required = [
        ("cv2",          "opencv-python"),
        ("PIL",          "pillow"),
        ("onnxruntime",  "onnxruntime-directml"),
        ("fast_plate_ocr", "fast-plate-ocr --no-deps"),
        ("numpy",        "numpy"),
        ("qrcode",       "qrcode"),
    ]
    for module, package in required:
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    return missing


def main():
    missing = check_dependencies()
    if missing:
        root = tk.Tk()
        root.withdraw()
        pkg_list = "\n".join(f"  pip install {p}" for p in missing)
        messagebox.showerror(
            "Dependencias faltantes",
            f"Instale los siguientes paquetes antes de continuar:\n\n{pkg_list}"
        )
        root.destroy()
        sys.exit(1)

    # inicio de sesión -> aplicación; "Cerrar sesión" vuelve al inicio de sesión
    from gui.login import LoginWindow
    from gui.app import UmbralGuardianApp
    while True:
        login = LoginWindow()
        login.mainloop()
        if login.session is None:
            break
        app = UmbralGuardianApp()
        app.mainloop()
        if not app.logout_requested:
            break


if __name__ == "__main__":
    main()
