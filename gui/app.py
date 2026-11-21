# -*- coding: utf-8 -*-
"""
gui/app.py - Ventana principal Umbral Guardian
Una sola ventana Tkinter con barra lateral de navegación.
"""

import tkinter as tk
from tkinter import ttk, messagebox

import config
from core import session
from core.session import ROL_SUPERADMIN, ROL_ADMIN, ROL_CONSERJE

# paleta oscura
BG_DARK    = "#1e1e2e"
BG_PANEL   = "#2d2d44"
BG_ITEM    = "#3d3d5c"
BG_HOVER   = "#4a4a6a"
FG_PRIMARY = "#00ff88"
FG_WHITE   = "#ffffff"
FG_GRAY    = "#aaaaaa"
FG_WARN    = "#ffaa00"
FG_RED     = "#ff4444"
FG_BLUE    = "#4488ff"


# (clave, etiqueta, ícono, módulo, clase, roles que la ven)
NAV_ITEMS = [
    ("monitor",   "Monitor",       "🎥", "gui.view_monitor",   "MonitorView",   {ROL_ADMIN, ROL_CONSERJE}),
    ("visits",    "Visitas",       "🧾", "gui.view_visits",    "VisitsView",    {ROL_ADMIN, ROL_CONSERJE}),
    ("residents", "Residentes",    "👤", "gui.view_residents", "ResidentsView", {ROL_ADMIN, ROL_CONSERJE}),
    ("registro",  "Registro móvil", "📱", "gui.view_registros", "RegistrosView", {ROL_ADMIN, ROL_CONSERJE}),
    ("vehicles",  "Vehículos",     "🚗", "gui.view_vehicles",  "VehiclesView",  {ROL_ADMIN, ROL_CONSERJE}),
    ("cameras",   "Cámaras",       "📷", "gui.view_cameras",   "CamerasView",   {ROL_ADMIN}),
    ("history",   "Historial",     "📋", "gui.view_history",   "HistoryView",   {ROL_ADMIN, ROL_CONSERJE}),
    ("reports",   "Reportes",      "📊", "gui.view_reports",   "ReportsView",   {ROL_ADMIN}),
    ("privacy",   "Privacidad",    "🔒", "gui.view_privacy",   "PrivacyView",   {ROL_ADMIN}),
    ("accounts",  "Cuentas",       "🔑", "gui.view_accounts",  "AccountsView",  {ROL_ADMIN}),
    ("provider",  "Condominios",   "🏢", "gui.view_provider",  "ProviderView",  {ROL_SUPERADMIN}),
    ("plans",     "Planes",        "💲", "gui.view_plans",     "PlansView",     {ROL_SUPERADMIN}),
    ("settings",  "Configuración", "⚙",  "gui.view_settings",  "SettingsView",  {ROL_ADMIN}),
]


class UmbralGuardianApp(tk.Tk):
    """Ventana raíz de la aplicación (requiere session.current)."""

    def __init__(self):
        super().__init__()
        self.title("Umbral Guardian — Sistema de Seguridad")
        self.geometry("1400x860")
        self.minsize(1100, 700)
        self.configure(bg=BG_DARK)

        self.logout_requested = False
        self._items = [i for i in NAV_ITEMS if session.current.rol in i[5]]
        self._views: dict[str, tk.Frame] = {}
        self._active_view: str = ""
        self._nav_buttons: dict[str, tk.Button] = {}

        self._build_layout()
        self._load_views()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.navigate(self._items[0][0])
        if not session.current.is_superadmin:
            self._schedule_sync()
        if session.current.en_gracia:
            self.after(500, lambda: messagebox.showwarning(
                "Suscripción vencida",
                f"La suscripción venció el {session.current.vence:%d/%m/%Y}.\n"
                "El sistema seguirá operando durante el período de gracia.\n"
                "Regularice el pago con el proveedor."))

    # ── layout ────────────────────────────────────────────────────────────

    def _build_layout(self):
        # cabecera
        header = tk.Frame(self, bg=BG_PANEL, height=60)
        header.pack(side=tk.TOP, fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header, text="Umbral Guardian",
            font=("Segoe UI", 18, "bold"), bg=BG_PANEL, fg=FG_PRIMARY,
        ).pack(side=tk.LEFT, padx=20, pady=10)

        s = session.current
        tk.Button(
            header, text="Cerrar sesión", command=self._logout,
            font=("Segoe UI", 9), bg=BG_ITEM, fg=FG_WHITE, relief=tk.FLAT, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=(10, 20))
        tk.Button(
            header, text="🔑 Mi contraseña", command=self._cambiar_password,
            font=("Segoe UI", 9), bg=BG_ITEM, fg=FG_WHITE, relief=tk.FLAT, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=(10, 0))

        tk.Label(
            header, text=f"{s.nombre}  ·  {s.rol}",
            font=("Segoe UI", 10), bg=BG_PANEL, fg=FG_WHITE,
        ).pack(side=tk.RIGHT, padx=10)

        self._status_label = tk.Label(
            header, text="● SIN CONEXIÓN" if s.offline else "● EN LÍNEA",
            font=("Segoe UI", 10), bg=BG_PANEL, fg=FG_WARN if s.offline else FG_PRIMARY,
        )
        self._status_label.pack(side=tk.RIGHT, padx=10)

        self._db_label = tk.Label(
            header, text="BD: —",
            font=("Segoe UI", 10), bg=BG_PANEL, fg=FG_GRAY,
        )
        self._db_label.pack(side=tk.RIGHT, padx=10)

        if s.idcondominio:
            dias = s.dias_restantes
            color = FG_RED if dias < 0 else FG_WARN if dias <= 7 else FG_GRAY
            tk.Label(
                header, text=f"{s.condominio}  ·  Plan {s.plan}  ·  pagado hasta "
                             f"{s.vence:%d/%m/%Y}",
                font=("Segoe UI", 10), bg=BG_PANEL, fg=color,
            ).pack(side=tk.LEFT, padx=10)

        # cuerpo
        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True)

        # barra lateral
        self._sidebar = tk.Frame(body, bg=BG_PANEL, width=200)
        self._sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self._sidebar.pack_propagate(False)

        tk.Label(
            self._sidebar, text="NAVEGACIÓN",
            font=("Segoe UI", 8, "bold"), bg=BG_PANEL, fg=FG_GRAY,
        ).pack(pady=(20, 5), padx=15, anchor=tk.W)

        for key, label, icon, *_ in self._items:
            btn = tk.Button(
                self._sidebar,
                text=f"  {icon}  {label}",
                font=("Segoe UI", 11),
                bg=BG_PANEL, fg=FG_WHITE,
                activebackground=BG_HOVER, activeforeground=FG_PRIMARY,
                anchor=tk.W, relief=tk.FLAT, bd=0,
                padx=10, pady=10, cursor="hand2",
                command=lambda k=key: self.navigate(k),
            )
            btn.pack(fill=tk.X, padx=5)
            self._nav_buttons[key] = btn
            self._bind_hover(btn)

        # versión al fondo de la sidebar
        tk.Label(
            self._sidebar, text="v3.0 — RF-DETR Nano",
            font=("Segoe UI", 8), bg=BG_PANEL, fg=FG_GRAY,
        ).pack(side=tk.BOTTOM, pady=10)

        # contenedor de vistas
        self._content = tk.Frame(body, bg=BG_DARK)
        self._content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _bind_hover(self, btn: tk.Button):
        btn.bind("<Enter>", lambda e: btn.config(bg=BG_HOVER, fg=FG_PRIMARY))
        btn.bind("<Leave>", lambda e: self._restore_btn(btn))

    def _restore_btn(self, btn: tk.Button):
        key = next((k for k, b in self._nav_buttons.items() if b is btn), None)
        if key and key == self._active_view:
            btn.config(bg=BG_ITEM, fg=FG_PRIMARY)
        else:
            btn.config(bg=BG_PANEL, fg=FG_WHITE)

    # ── carga de vistas ───────────────────────────────────────────────────

    def _load_views(self):
        import importlib
        for key, _label, _icon, module, cls_name, _roles in self._items:
            cls = getattr(importlib.import_module(module), cls_name)
            view = cls(self._content, self)
            view.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._views[key] = view

    # ── navegación ────────────────────────────────────────────────────────

    def navigate(self, key: str):
        if key not in self._views:
            return

        # ocultar vista activa
        if self._active_view and self._active_view in self._views:
            prev_view = self._views[self._active_view]
            if hasattr(prev_view, "on_hide"):
                prev_view.on_hide()
            prev_view.place_forget()
            prev_btn = self._nav_buttons.get(self._active_view)
            if prev_btn:
                prev_btn.config(bg=BG_PANEL, fg=FG_WHITE)

        # mostrar nueva
        self._views[key].place(relx=0, rely=0, relwidth=1, relheight=1)
        self._views[key].tkraise()
        self._active_view = key

        # marcar botón activo
        btn = self._nav_buttons.get(key)
        if btn:
            btn.config(bg=BG_ITEM, fg=FG_PRIMARY)

        # notificar vista
        view = self._views[key]
        if hasattr(view, "on_show"):
            view.on_show()

    # ── helpers públicos ──────────────────────────────────────────────────

    def set_db_status(self, connected: bool):
        text = "BD: CONECTADA" if connected else "BD: DESCONECTADA"
        color = FG_PRIMARY if connected else FG_RED
        self._db_label.config(text=text, fg=color)

    def _schedule_sync(self):
        self.after(config.SINCRONIZAR_CADA_H * 3600 * 1000, self._sync)

    def _sync(self):
        """Re-sincroniza licencia y cuentas con la nube; cierra sesión si la licencia caducó."""
        from database import DatabaseManager
        db = DatabaseManager()
        if db.connect():
            problema = session.resincronizar(db)
            db.disconnect()
            if problema:
                messagebox.showerror("Suscripción", problema)
                self.logout_requested = True
                self._on_close()
                return
        self._schedule_sync()

    def notify_cameras_changed(self):
        """Avisa a la vista de Monitor que cameras.json cambió (alta/baja/edición)."""
        monitor = self._views.get("monitor")
        if monitor and hasattr(monitor, "refresh_cameras"):
            monitor.refresh_cameras()

    # ── cierre ────────────────────────────────────────────────────────────

    def _cambiar_password(self):
        if session.current.offline:
            messagebox.showwarning("Sin conexión", "Cambiar la contraseña requiere conexión "
                                                   "con la nube. Inicie sesión con internet.")
            return
        from database import DatabaseManager
        from gui.dialog_password import CambiarPasswordDialog
        db = None if session.current.is_superadmin else DatabaseManager()
        if db is not None and not db.connect():
            db = None
        self.wait_window(CambiarPasswordDialog(self, db=db))
        if db:
            db.disconnect()

    def _logout(self):
        if messagebox.askyesno("Cerrar sesión", "¿Cerrar la sesión actual?"):
            self.logout_requested = True
            self._on_close()

    def _on_close(self):
        # detener motor si está corriendo
        monitor = self._views.get("monitor")
        if monitor and hasattr(monitor, "stop_engine"):
            monitor.stop_engine()
        session.current = None
        self.destroy()
