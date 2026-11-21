# -*- coding: utf-8 -*-
"""
gui/login.py - Inicio de sesión con verificación de suscripción.
"""

import tkinter as tk

import config
from core import session
from database import DatabaseManager
from gui.dialog_password import CambiarPasswordDialog

BG_DARK    = "#1e1e2e"
BG_PANEL   = "#2d2d44"
BG_ITEM    = "#3d3d5c"
FG_PRIMARY = "#00ff88"
FG_WHITE   = "#ffffff"
FG_GRAY    = "#aaaaaa"
FG_RED     = "#ff4444"
FG_WARN    = "#ffaa00"


class LoginWindow(tk.Tk):
    """Ventana de acceso. Tras cerrarla, self.session contiene la sesión o None."""

    def __init__(self):
        super().__init__()
        self.title("Umbral Guardian — Iniciar sesión")
        self.geometry("420x440")
        self.resizable(False, False)
        self.configure(bg=BG_DARK)
        self.session = None

        box = tk.Frame(self, bg=BG_PANEL, padx=30, pady=25)
        box.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        tk.Label(box, text="Umbral Guardian", font=("Segoe UI", 20, "bold"),
                 bg=BG_PANEL, fg=FG_PRIMARY).pack()
        tk.Label(box, text="Control de accesos", font=("Segoe UI", 10),
                 bg=BG_PANEL, fg=FG_GRAY).pack(pady=(0, 18))

        tk.Label(box, text="Correo", font=("Segoe UI", 10), bg=BG_PANEL,
                 fg=FG_WHITE, anchor=tk.W).pack(fill=tk.X)
        self._email = tk.Entry(box, font=("Segoe UI", 11), width=30, bg=BG_ITEM,
                               fg=FG_WHITE, insertbackground=FG_WHITE)
        self._email.pack(pady=(0, 10), ipady=4)

        tk.Label(box, text="Contraseña", font=("Segoe UI", 10), bg=BG_PANEL,
                 fg=FG_WHITE, anchor=tk.W).pack(fill=tk.X)
        self._password = tk.Entry(box, font=("Segoe UI", 11), width=30, show="●",
                                  bg=BG_ITEM, fg=FG_WHITE, insertbackground=FG_WHITE)
        self._password.pack(pady=(0, 14), ipady=4)

        self._btn = tk.Button(box, text="Ingresar", command=self._login,
                              font=("Segoe UI", 11, "bold"), bg=FG_PRIMARY, fg="black",
                              width=20, cursor="hand2", relief=tk.FLAT)
        self._btn.pack(ipady=4)

        self._msg = tk.Label(box, text="", font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_RED,
                             wraplength=300, justify=tk.CENTER)
        self._msg.pack(pady=(12, 0))

        self.bind("<Return>", lambda _e: self._login())
        self._email.focus_set()

    def _login(self):
        email, password = self._email.get().strip(), self._password.get()
        if not email or not password:
            self._msg.config(text="Ingrese correo y contraseña")
            return
        self._msg.config(text="Verificando...", fg=FG_GRAY)
        self.update_idletasks()

        # la base local es opcional para la cuenta del proveedor (no opera un condominio)
        db = DatabaseManager()
        if not db.connect():
            db = None
        try:
            s = session.login(db, email, password)
        except session.LoginError as e:
            self._msg.config(text=str(e), fg=FG_RED)
            self._password.delete(0, tk.END)
            if db:
                db.disconnect()
            return

        if s.debe_cambiar_password:
            # contraseña temporal (cuenta nueva o restablecida): cambiarla antes de entrar
            self._msg.config(text="")
            dlg = CambiarPasswordDialog(self, obligatorio=True, db=db)
            self.wait_window(dlg)
            if not dlg.ok:
                session.current = None
                self._msg.config(text="Debe cambiar la contraseña temporal para ingresar.",
                                 fg=FG_WARN)
                self._password.delete(0, tk.END)
                if db:
                    db.disconnect()
                return

        if db and not s.is_superadmin:
            # política de retención: se aplica al iniciar sesión (art. 3 c)
            try:
                borrados = db.purgar_datos_vencidos(config.DIAS_RETENCION_DETECCIONES,
                                                    config.DIAS_RETENCION_VISITAS)
                if any(borrados.values()):
                    print(f"[Retención] Datos vencidos eliminados: {borrados}")
                # invitaciones vencidas y solicitudes móviles sin resolver, con sus vectores
                n = db.purgar_registros_moviles(config.DIAS_RETENCION_VISITAS)
                if n:
                    print(f"[Retención] Registros móviles vencidos eliminados: {n}")
                n = db.purgar_autorizaciones_vencidas()
                if n:
                    print(f"[Retención] Visitas ocasionales vencidas (con su rostro): {n}")
            except Exception as e:
                print(f"[Retención] No se pudo aplicar: {e}")
        if db:
            db.disconnect()
        if s.offline:
            from tkinter import messagebox
            messagebox.showwarning(
                "Sin conexión",
                "No hay conexión con la nube. El sistema funcionará con los datos "
                "locales; la gestión de cuentas no estará disponible.", parent=self)

        self.session = s
        self.destroy()
