# -*- coding: utf-8 -*-
"""
gui/view_visits.py - Registro de visitas por carnet (RUT y nombre) y patente.

Las visitas no se identifican biométricamente (RN-06, HU-13): el conserje las
registra y, si llegan en vehículo, el sistema reconoce su patente como "visita".
Los datos se eliminan tras DIAS_RETENCION_VISITAS (política de retención).
"""

import tkinter as tk
from tkinter import ttk, messagebox

import config
from core import session
from core.security import valid_rut, format_rut, mask_rut, clean_plate
from database import DatabaseManager

BG_DARK   = "#1e1e2e"
BG_PANEL  = "#2d2d44"
BG_ITEM   = "#3d3d5c"
FG_GREEN  = "#00ff88"
FG_WHITE  = "#ffffff"
FG_GRAY   = "#aaaaaa"
FG_WARN   = "#ffaa00"


class VisitsView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self._app = app
        self.db = DatabaseManager()
        self._unidades: list = []
        self._build_ui()

    def _connect_db(self) -> bool:
        return self.db.is_connected() or self.db.connect()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        top = tk.Frame(self, bg=BG_PANEL, height=50)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🧾  Visitas", font=("Segoe UI", 14, "bold"),
                 bg=BG_PANEL, fg=FG_GREEN).pack(side=tk.LEFT, padx=20, pady=10)

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        form = tk.Frame(body, bg=BG_PANEL, width=380)
        form.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        form.pack_propagate(False)

        tk.Label(form, text="Registrar ingreso", font=("Segoe UI", 12, "bold"),
                 bg=BG_PANEL, fg=FG_GREEN).pack(pady=12, padx=15, anchor=tk.W)

        ff = tk.Frame(form, bg=BG_PANEL)
        ff.pack(fill=tk.X, padx=15)
        self.entries: dict[str, tk.Entry] = {}
        for r, (label, key) in enumerate([("RUT *", "rut"), ("Nombres *", "nombres"),
                                          ("Apellidos *", "apellidos"),
                                          ("Patente (si viene en auto)", "patente")]):
            tk.Label(ff, text=label, font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE,
                     anchor=tk.W).grid(row=r, column=0, sticky=tk.W, pady=4, padx=4)
            e = tk.Entry(ff, font=("Segoe UI", 10), width=22, bg=BG_ITEM, fg=FG_WHITE,
                         insertbackground=FG_WHITE)
            e.grid(row=r, column=1, pady=4, padx=4, sticky=tk.EW)
            self.entries[key] = e

        tk.Label(ff, text="Unidad de destino *", font=("Segoe UI", 9), bg=BG_PANEL,
                 fg=FG_WHITE, anchor=tk.W).grid(row=4, column=0, sticky=tk.W, pady=4, padx=4)
        self.unidad_var = tk.StringVar()
        self.unidad_cb = ttk.Combobox(ff, textvariable=self.unidad_var, state="readonly",
                                      font=("Segoe UI", 10))
        self.unidad_cb.grid(row=4, column=1, pady=4, padx=4, sticky=tk.EW)
        ff.columnconfigure(1, weight=1)

        tk.Label(form, text=f"Sin registro de rostro. Los datos se eliminan a los "
                            f"{config.DIAS_RETENCION_VISITAS} días.",
                 font=("Segoe UI", 8), bg=BG_PANEL, fg=FG_GRAY, wraplength=340,
                 justify=tk.LEFT).pack(padx=15, anchor=tk.W, pady=(6, 0))

        tk.Button(form, text="Registrar visita", command=self._registrar,
                  font=("Segoe UI", 11, "bold"), bg=FG_GREEN, fg="black",
                  width=22, height=2, cursor="hand2").pack(pady=15)

        right = tk.Frame(body, bg=BG_PANEL)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        head = tk.Frame(right, bg=BG_PANEL)
        head.pack(fill=tk.X, padx=10, pady=(10, 0))
        tk.Label(head, text="Visitas", font=("Segoe UI", 12, "bold"),
                 bg=BG_PANEL, fg=FG_GREEN).pack(side=tk.LEFT)
        self.solo_activas = tk.BooleanVar(value=True)
        tk.Checkbutton(head, text="Solo dentro del condominio", variable=self.solo_activas,
                       command=self._load_list, bg=BG_PANEL, fg=FG_WHITE,
                       selectcolor=BG_ITEM, activebackground=BG_PANEL,
                       font=("Segoe UI", 9)).pack(side=tk.RIGHT)

        cols = ("ingreso", "nombre", "rut", "unidad", "patente", "salida")
        self._tree = ttk.Treeview(right, columns=cols, show="headings", height=18)
        for col, hdr, w in [("ingreso", "Ingreso", 130), ("nombre", "Nombre", 190),
                            ("rut", "RUT", 110), ("unidad", "Unidad", 90),
                            ("patente", "Patente", 80), ("salida", "Salida", 130)]:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, anchor=tk.W)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        btns = tk.Frame(right, bg=BG_PANEL)
        btns.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(btns, text="⏏ Marcar salida", command=self._salida,
                  font=("Segoe UI", 10, "bold"), bg=FG_WARN, fg="black",
                  cursor="hand2", relief=tk.FLAT, padx=10).pack(side=tk.LEFT, padx=4)
        tk.Button(btns, text="🔄 Actualizar", command=self._load_list,
                  font=("Segoe UI", 10), bg=BG_ITEM, fg=FG_WHITE,
                  cursor="hand2", relief=tk.FLAT, padx=10).pack(side=tk.LEFT, padx=4)

    # ── datos ─────────────────────────────────────────────────────────────

    def _load(self):
        if not self._connect_db():
            return
        self._unidades = self.db.list_unidades()
        self.unidad_cb.configure(values=[u["codigo"] for u in self._unidades])
        self._load_list()

    def _load_list(self):
        if not self._connect_db():
            return
        for row in self._tree.get_children():
            self._tree.delete(row)
        # el conserje ve el RUT enmascarado; el administrador lo ve completo
        show_rut = format_rut if session.current.is_admin else mask_rut
        for v in self.db.list_visitas(self.solo_activas.get()):
            self._tree.insert("", tk.END, iid=str(v["idvisita"]), values=(
                f"{v['fecha_ingreso']:%d/%m %H:%M}", f"{v['nombres']} {v['apellidos']}",
                show_rut(v["rut"]), v["unidad"], v["patente"] or "—",
                f"{v['fecha_salida']:%d/%m %H:%M}" if v["fecha_salida"] else "Dentro",
            ))

    def _registrar(self):
        g = {k: e.get().strip() for k, e in self.entries.items()}
        if not all([g["rut"], g["nombres"], g["apellidos"], self.unidad_var.get()]):
            messagebox.showerror("Error", "Complete los campos obligatorios (*)")
            return
        if not valid_rut(g["rut"]):
            messagebox.showerror("Error", "RUT inválido (revise el dígito verificador)")
            return
        patente = clean_plate(g["patente"])
        if patente and not 5 <= len(patente) <= 8:
            messagebox.showerror("Error", "Patente inválida")
            return
        idunidad = next(u["idunidad"] for u in self._unidades
                        if u["codigo"] == self.unidad_var.get())
        try:
            self.db.registrar_visita(format_rut(g["rut"]),
                                     g["nombres"], g["apellidos"], idunidad, patente or None,
                                     session.current.idcuenta)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo registrar:\n{e}")
            return
        for e in self.entries.values():
            e.delete(0, tk.END)
        self._load_list()

    def _salida(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione una visita")
            return
        self.db.marcar_salida(int(sel[0]))
        self._load_list()

    def on_show(self):
        self._load()
