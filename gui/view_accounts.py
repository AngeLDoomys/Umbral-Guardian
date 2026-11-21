# -*- coding: utf-8 -*-
"""
gui/view_accounts.py - Suscripción del condominio y cuentas de acceso (administrador).
Las cuentas viven en la nube: se gestionan a través de la API central y luego se
sincroniza la copia local que permite iniciar sesión sin conexión.
"""

import re
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

from core import cloud, session
from core.security import valid_rut, format_rut, password_problem
from database import DatabaseManager
from gui.dialog_password import mostrar_password_temporal

BG_DARK   = "#1e1e2e"
BG_PANEL  = "#2d2d44"
BG_ITEM   = "#3d3d5c"
FG_GREEN  = "#00ff88"
FG_WHITE  = "#ffffff"
FG_GRAY   = "#aaaaaa"
FG_WARN   = "#ffaa00"
FG_RED    = "#ff4444"
FG_BLUE   = "#4488ff"


class AccountsView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self._app = app
        self.db = DatabaseManager()
        self._build_ui()

    def _connect_db(self) -> bool:
        return self.db.is_connected() or self.db.connect()

    def _build_ui(self):
        top = tk.Frame(self, bg=BG_PANEL, height=50)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🔑  Cuentas y suscripción", font=("Segoe UI", 14, "bold"),
                 bg=BG_PANEL, fg=FG_GREEN).pack(side=tk.LEFT, padx=20, pady=10)

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # suscripción
        self._susc = tk.Label(body, text="", font=("Segoe UI", 11), bg=BG_PANEL,
                              fg=FG_WHITE, justify=tk.LEFT, anchor=tk.W, padx=15, pady=12)
        self._susc.pack(fill=tk.X, pady=(0, 10))

        main = tk.Frame(body, bg=BG_DARK)
        main.pack(fill=tk.BOTH, expand=True)

        form = tk.Frame(main, bg=BG_PANEL, width=360)
        form.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        form.pack_propagate(False)
        tk.Label(form, text="Nueva cuenta", font=("Segoe UI", 12, "bold"),
                 bg=BG_PANEL, fg=FG_GREEN).pack(pady=12, padx=15, anchor=tk.W)

        ff = tk.Frame(form, bg=BG_PANEL)
        ff.pack(fill=tk.X, padx=15)
        self.entries: dict[str, tk.Entry] = {}
        for r, (label, key) in enumerate([("RUT *", "rut"), ("Nombres *", "nombres"),
                                          ("Apellidos *", "apellidos"),
                                          ("Correo (usuario) *", "email"),
                                          ("Contraseña inicial *", "password")]):
            tk.Label(ff, text=label, font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE,
                     anchor=tk.W).grid(row=r, column=0, sticky=tk.W, pady=4, padx=4)
            e = tk.Entry(ff, font=("Segoe UI", 10), width=22, bg=BG_ITEM, fg=FG_WHITE,
                         insertbackground=FG_WHITE, show="●" if key == "password" else "")
            e.grid(row=r, column=1, pady=4, padx=4, sticky=tk.EW)
            self.entries[key] = e
        tk.Label(ff, text="Rol *", font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE,
                 anchor=tk.W).grid(row=5, column=0, sticky=tk.W, pady=4, padx=4)
        self.rol_var = tk.StringVar(value="conserje")
        ttk.Combobox(ff, textvariable=self.rol_var, values=["conserje", "administrador"],
                     state="readonly", font=("Segoe UI", 10)).grid(
            row=5, column=1, pady=4, padx=4, sticky=tk.EW)
        ff.columnconfigure(1, weight=1)

        tk.Label(form, text="El usuario deberá cambiar la contraseña\ninicial al ingresar "
                            "por primera vez.", font=("Segoe UI", 8), bg=BG_PANEL,
                 fg=FG_GRAY, justify=tk.LEFT).pack(padx=15, anchor=tk.W)
        tk.Button(form, text="Crear cuenta", command=self._crear,
                  font=("Segoe UI", 11, "bold"), bg=FG_GREEN, fg="black",
                  cursor="hand2").pack(pady=15)

        right = tk.Frame(main, bg=BG_PANEL)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        cols = ("nombre", "email", "rol", "estado", "acceso")
        self._tree = ttk.Treeview(right, columns=cols, show="headings", height=14)
        for col, hdr, w in [("nombre", "Nombre", 200), ("email", "Correo", 220),
                            ("rol", "Rol", 110), ("estado", "Estado", 150),
                            ("acceso", "Último acceso", 140)]:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, anchor=tk.W)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        btns = tk.Frame(right, bg=BG_PANEL)
        btns.pack(fill=tk.X, padx=10, pady=5)
        for text, cmd, bg in [("⏯ Activar / desactivar", self._toggle, FG_WARN),
                              ("🔑 Restablecer contraseña", self._password, FG_BLUE)]:
            tk.Button(btns, text=text, command=cmd, font=("Segoe UI", 10, "bold"), bg=bg,
                      fg="black" if bg == FG_WARN else FG_WHITE, cursor="hand2",
                      relief=tk.FLAT, padx=8).pack(side=tk.LEFT, padx=4)

    # ── datos ─────────────────────────────────────────────────────────────

    def _api(self, method, path, body=None):
        """Llama a la API central; muestra el error y retorna None si falla."""
        s = session.current
        if s.offline:
            messagebox.showwarning("Sin conexión", "La gestión de cuentas requiere conexión "
                                                   "con la nube. Inicie sesión con internet.")
            return None
        try:
            return cloud.get(path, s.token) if method == "GET" else cloud.post(path, s.token, body)
        except cloud.CloudError as e:
            messagebox.showerror("Error", str(e))
            return None

    def _resync(self):
        """Actualiza la copia local de cuentas (para el inicio de sesión sin conexión)."""
        if self._connect_db():
            try:
                cloud.sincronizar(self.db)
            except cloud.CloudError as e:
                print(f"[Cuentas] Sincronización pendiente: {e}")

    def _load(self):
        s = session.current
        dias = s.dias_restantes
        estado = (f"vence en {dias} días" if dias >= 0
                  else f"VENCIDA hace {-dias} días (período de gracia)")
        self._susc.config(
            text=f"{s.condominio}   |   Plan {s.plan} (hasta {s.max_camaras} cámaras)   |   "
                 f"Pagado hasta {s.vence:%d/%m/%Y}: {estado}"
                 + ("   |   SIN CONEXIÓN" if s.offline else ""),
            fg=FG_GREEN if dias > 7 else FG_WARN)
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._cuentas = [] if s.offline else (self._api("GET", "/api/cuentas") or [])
        for c in self._cuentas:
            acceso = (datetime.fromisoformat(c["ultimo_acceso"]).strftime("%d/%m/%Y %H:%M")
                      if c["ultimo_acceso"] else "—")
            estado = "Activa" if c["activa"] else "Inactiva"
            if c.get("debe_cambiar_password"):
                estado += " · clave temporal"
            self._tree.insert("", tk.END, iid=str(c["idcuenta"]), values=(
                f"{c['nombres']} {c['apellidos']}", c["email"], c["rol"], estado, acceso))

    def _crear(self):
        g = {k: e.get().strip() for k, e in self.entries.items()}
        if not all(g.values()):
            messagebox.showerror("Error", "Complete todos los campos")
            return
        if not valid_rut(g["rut"]):
            messagebox.showerror("Error", "RUT inválido")
            return
        if not re.match(r"[^@]+@[^@]+\.[^@]+", g["email"]):
            messagebox.showerror("Error", "Correo inválido")
            return
        problem = password_problem(g["password"])
        if problem:
            messagebox.showerror("Error", problem)
            return
        body = dict(g, rut=format_rut(g["rut"]), rol=self.rol_var.get())
        if self._api("POST", "/api/cuentas", body) is None:
            return
        for e in self.entries.values():
            e.delete(0, tk.END)
        self._resync()
        self._load()

    def _selected(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione una cuenta")
            return None
        return next(c for c in self._cuentas if str(c["idcuenta"]) == sel[0])

    def _toggle(self):
        c = self._selected()
        if not c:
            return
        if c["idcuenta"] == session.current.idcuenta:
            messagebox.showwarning("Aviso", "No puede desactivar su propia cuenta")
            return
        if self._api("POST", f"/api/cuentas/{c['idcuenta']}/activa",
                     {"activa": not c["activa"]}) is not None:
            self._resync()
            self._load()

    def _password(self):
        c = self._selected()
        if not c:
            return
        if c["idcuenta"] == session.current.idcuenta:
            messagebox.showinfo("Su cuenta", "Para su propia cuenta use «🔑 Mi contraseña», "
                                             "arriba a la derecha.")
            return
        if not messagebox.askyesno(
                "Restablecer contraseña",
                f"Se generará una contraseña temporal para {c['email']}.\n"
                "La actual dejará de funcionar y el usuario deberá cambiarla al ingresar.\n\n"
                "¿Continuar?"):
            return
        r = self._api("POST", f"/api/cuentas/{c['idcuenta']}/password")
        if r is not None:
            self._resync()
            self._load()
            mostrar_password_temporal(self, r["email"], r["password_temporal"])

    def on_show(self):
        self._load()
