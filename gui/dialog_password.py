# -*- coding: utf-8 -*-
"""
gui/dialog_password.py - Ventanas de contraseña compartidas por todas las vistas:
  - CambiarPasswordDialog: el usuario cambia su propia contraseña (obligatorio
    cuando la actual es temporal).
  - mostrar_password_temporal: muestra una sola vez la contraseña temporal
    generada al restablecer una cuenta.
Nadie puede ver una contraseña guardada (se guarda solo su hash PBKDF2):
solo se pueden restablecer.
"""

import tkinter as tk
from tkinter import messagebox

from core import session
from core.security import password_problem

BG_PANEL = "#2d2d44"
BG_ITEM  = "#3d3d5c"
FG_GREEN = "#00ff88"
FG_WHITE = "#ffffff"
FG_GRAY  = "#aaaaaa"
FG_RED   = "#ff4444"
FG_BLUE  = "#4488ff"


class CambiarPasswordDialog(tk.Toplevel):
    """Ventana modal. Tras cerrarse, self.ok indica si la contraseña se cambió."""

    def __init__(self, parent, obligatorio: bool = False, db=None):
        super().__init__(parent)
        self.title("Cambiar contraseña")
        self.configure(bg=BG_PANEL)
        self.resizable(False, False)
        self.transient(parent)
        self.ok = False
        self._db = db

        titulo = ("Su contraseña es temporal" if obligatorio else "Cambiar mi contraseña")
        tk.Label(self, text=titulo, font=("Segoe UI", 13, "bold"), bg=BG_PANEL,
                 fg=FG_GREEN).pack(padx=24, pady=(18, 4))
        if obligatorio:
            tk.Label(self, text="Por seguridad, elija una contraseña nueva antes de continuar.",
                     font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE).pack(padx=24)

        form = tk.Frame(self, bg=BG_PANEL)
        form.pack(padx=24, pady=12)
        self._e = {}
        for r, (label, key) in enumerate([("Contraseña actual" + (" (temporal)" if obligatorio else ""), "actual"),
                                          ("Contraseña nueva", "nueva"),
                                          ("Repita la nueva", "repetir")]):
            tk.Label(form, text=label, font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE,
                     anchor=tk.W).grid(row=r, column=0, sticky=tk.W, pady=4, padx=(0, 8))
            e = tk.Entry(form, font=("Segoe UI", 11), width=24, show="●", bg=BG_ITEM,
                         fg=FG_WHITE, insertbackground=FG_WHITE)
            e.grid(row=r, column=1, pady=4)
            self._e[key] = e
        tk.Label(self, text="Mínimo 8 caracteres, con letras y números.",
                 font=("Segoe UI", 8), bg=BG_PANEL, fg=FG_GRAY).pack()

        self._msg = tk.Label(self, text="", font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_RED,
                             wraplength=340)
        self._msg.pack(pady=(6, 0))

        row = tk.Frame(self, bg=BG_PANEL)
        row.pack(pady=(8, 18))
        tk.Button(row, text="Guardar", command=self._guardar, font=("Segoe UI", 10, "bold"),
                  bg=FG_GREEN, fg="black", width=12, relief=tk.FLAT,
                  cursor="hand2").pack(side=tk.LEFT, padx=4)
        tk.Button(row, text="Cerrar sesión" if obligatorio else "Cancelar",
                  command=self.destroy, font=("Segoe UI", 10), bg=BG_ITEM, fg=FG_WHITE,
                  width=12, relief=tk.FLAT, cursor="hand2").pack(side=tk.LEFT, padx=4)

        self.bind("<Return>", lambda _e: self._guardar())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._e["actual"].focus_set()
        self.grab_set()

    def _guardar(self):
        actual, nueva, repetir = (self._e[k].get() for k in ("actual", "nueva", "repetir"))
        if not actual or not nueva:
            self._msg.config(text="Complete los campos")
            return
        if nueva != repetir:
            self._msg.config(text="La contraseña nueva y su repetición no coinciden")
            return
        problema = password_problem(nueva)
        if problema:
            self._msg.config(text=problema)
            return
        if nueva == actual:
            self._msg.config(text="La contraseña nueva debe ser distinta de la actual")
            return
        try:
            session.cambiar_password(actual, nueva, self._db)
        except session.LoginError as e:
            self._msg.config(text=str(e))
            return
        self.ok = True
        messagebox.showinfo("Listo", "Contraseña cambiada", parent=self)
        self.destroy()


def mostrar_password_temporal(parent, email: str, password: str):
    """La contraseña temporal se muestra una sola vez: no queda guardada en ningún lado."""
    dlg = tk.Toplevel(parent)
    dlg.title("Contraseña temporal")
    dlg.configure(bg=BG_PANEL)
    dlg.resizable(False, False)
    dlg.transient(parent)
    tk.Label(dlg, text=f"Contraseña temporal de {email}", font=("Segoe UI", 12, "bold"),
             bg=BG_PANEL, fg=FG_GREEN).pack(padx=24, pady=(16, 4))
    tk.Label(dlg, text="Entréguela al usuario: deberá cambiarla al iniciar sesión.\n"
                       "No se vuelve a mostrar.",
             font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE, justify=tk.CENTER).pack(padx=24)
    e = tk.Entry(dlg, font=("Consolas", 16, "bold"), width=16, justify=tk.CENTER,
                 bg=BG_ITEM, fg=FG_WHITE, readonlybackground=BG_ITEM)
    e.insert(0, password)
    e.config(state="readonly")
    e.pack(padx=24, pady=12)

    def copiar():
        dlg.clipboard_clear()
        dlg.clipboard_append(password)

    row = tk.Frame(dlg, bg=BG_PANEL)
    row.pack(pady=(0, 16))
    tk.Button(row, text="Copiar", command=copiar, bg=FG_BLUE, fg=FG_WHITE,
              font=("Segoe UI", 10, "bold"), width=10, relief=tk.FLAT).pack(side=tk.LEFT, padx=4)
    tk.Button(row, text="Cerrar", command=dlg.destroy, bg=BG_ITEM, fg=FG_WHITE,
              font=("Segoe UI", 10), width=10, relief=tk.FLAT).pack(side=tk.LEFT, padx=4)
    dlg.grab_set()
