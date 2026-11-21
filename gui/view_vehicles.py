# -*- coding: utf-8 -*-
"""
gui/view_vehicles.py - Vehículos autorizados, asociados a una unidad del condominio.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from core.security import clean_plate
from database import DatabaseManager

BG_DARK   = "#1e1e2e"
BG_PANEL  = "#2d2d44"
BG_ITEM   = "#3d3d5c"
FG_GREEN  = "#00ff88"
FG_WHITE  = "#ffffff"
FG_GRAY   = "#aaaaaa"
FG_RED    = "#ff4444"

TIPOS = [("auto", "Auto"), ("moto", "Moto"), ("camioneta", "Camioneta"), ("otro", "Otro")]


class VehiclesView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self._app = app
        self.db = DatabaseManager()
        self._vehiculos: list = []
        self._build_ui()

    def _connect_db(self) -> bool:
        return self.db.is_connected() or self.db.connect()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        top = tk.Frame(self, bg=BG_PANEL, height=50)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🚗  Vehículos de residentes",
                 font=("Segoe UI", 14, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            side=tk.LEFT, padx=20, pady=10)

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        form_panel = tk.Frame(body, bg=BG_PANEL, width=380)
        form_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        form_panel.pack_propagate(False)

        tk.Label(form_panel, text="Registrar vehículo",
                 font=("Segoe UI", 12, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            pady=12, padx=15, anchor=tk.W)

        ff = tk.Frame(form_panel, bg=BG_PANEL)
        ff.pack(fill=tk.X, padx=15)

        def lbl(text, row):
            tk.Label(ff, text=text, font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE,
                     anchor=tk.W).grid(row=row, column=0, sticky=tk.W, pady=4, padx=4)

        def entry(text, row):
            lbl(text, row)
            e = tk.Entry(ff, font=("Segoe UI", 10), width=22, bg=BG_ITEM, fg=FG_WHITE,
                         insertbackground=FG_WHITE)
            e.grid(row=row, column=1, pady=4, padx=4, sticky=tk.EW)
            return e

        self.e_patente = entry("Patente *", 0)
        lbl("Unidad *", 1)
        self.unidad_var = tk.StringVar()
        self.unidad_cb = ttk.Combobox(ff, textvariable=self.unidad_var,
                                      state="readonly", font=("Segoe UI", 10))
        self.unidad_cb.grid(row=1, column=1, pady=4, padx=4, sticky=tk.EW)
        self.e_marca  = entry("Marca", 2)
        self.e_modelo = entry("Modelo", 3)
        self.e_color  = entry("Color", 4)

        lbl("Tipo *", 5)
        self.tipo_var = tk.StringVar(value="auto")
        tipo_f = tk.Frame(ff, bg=BG_PANEL)
        tipo_f.grid(row=5, column=1, sticky=tk.W, pady=4)
        for val, text in TIPOS:
            tk.Radiobutton(tipo_f, text=text, variable=self.tipo_var, value=val,
                           bg=BG_PANEL, fg=FG_WHITE, selectcolor=BG_ITEM,
                           activebackground=BG_PANEL, font=("Segoe UI", 9)).pack(
                side=tk.LEFT, padx=2)
        ff.columnconfigure(1, weight=1)

        tk.Label(form_panel, text="Las unidades se crean al registrar residentes.",
                 font=("Segoe UI", 8), bg=BG_PANEL, fg=FG_GRAY).pack(padx=15, anchor=tk.W)

        tk.Button(form_panel, text="Registrar vehículo", command=self._registrar,
                  font=("Segoe UI", 11, "bold"), bg=FG_GREEN, fg="black",
                  width=22, height=2, cursor="hand2").pack(pady=15)

        list_panel = tk.Frame(body, bg=BG_PANEL)
        list_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        tk.Label(list_panel, text="Vehículos autorizados",
                 font=("Segoe UI", 12, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            padx=10, pady=(10, 0), anchor=tk.W)

        cols = ("patente", "unidad", "tipo", "marca", "modelo", "color")
        self._tree = ttk.Treeview(list_panel, columns=cols, show="headings", height=18)
        for col, hdr, w in [("patente", "Patente", 100), ("unidad", "Unidad", 100),
                            ("tipo", "Tipo", 90), ("marca", "Marca", 110),
                            ("modelo", "Modelo", 110), ("color", "Color", 80)]:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, anchor=tk.W)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        btn_row = tk.Frame(list_panel, bg=BG_PANEL)
        btn_row.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(btn_row, text="🗑 Eliminar", command=self._eliminar,
                  font=("Segoe UI", 10, "bold"), bg=FG_RED, fg=FG_WHITE,
                  width=14, cursor="hand2", relief=tk.FLAT).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_row, text="🔄 Actualizar", command=self._load,
                  font=("Segoe UI", 10), bg=BG_ITEM, fg=FG_WHITE,
                  width=14, cursor="hand2", relief=tk.FLAT).pack(side=tk.LEFT, padx=4)

    # ── datos ─────────────────────────────────────────────────────────────

    def _load(self):
        if not self._connect_db():
            return
        self._unidades = self.db.list_unidades()
        self.unidad_cb.configure(values=[u["codigo"] for u in self._unidades])
        for row in self._tree.get_children():
            self._tree.delete(row)
        for v in self.db.list_vehiculos():
            self._tree.insert("", tk.END, iid=str(v["idvehiculo"]), values=(
                v["patente"], v["unidad"], v["tipo"].capitalize(),
                v["marca"] or "", v["modelo"] or "", v["color"] or "",
            ))

    def _registrar(self):
        if not self._connect_db():
            messagebox.showerror("Error", "Sin conexión a BD")
            return
        patente = clean_plate(self.e_patente.get())
        if not 5 <= len(patente) <= 8:
            messagebox.showerror("Error", "Patente inválida")
            return
        unidad = next((u for u in self._unidades if u["codigo"] == self.unidad_var.get()), None)
        if not unidad:
            messagebox.showerror("Error", "Seleccione la unidad")
            return
        try:
            self.db.create_vehiculo(unidad["idunidad"], patente, self.tipo_var.get(),
                                    self.e_marca.get().strip() or None,
                                    self.e_modelo.get().strip() or None,
                                    self.e_color.get().strip() or None)
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):   # patente repetida
                messagebox.showerror("Error", "Esa patente ya está registrada en la unidad")
            else:
                messagebox.showerror("Error", f"No se pudo registrar:\n{e}")
            return
        for e in (self.e_patente, self.e_marca, self.e_modelo, self.e_color):
            e.delete(0, tk.END)
        self.tipo_var.set("auto")
        self._load()

    def _eliminar(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione un vehículo")
            return
        if messagebox.askyesno("Confirmar", "¿Eliminar el vehículo seleccionado?"):
            self.db.delete_vehiculo(int(sel[0]))
            self._load()

    def on_show(self):
        self._load()
