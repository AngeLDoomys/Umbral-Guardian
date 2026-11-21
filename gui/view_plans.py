# -*- coding: utf-8 -*-
"""
gui/view_plans.py - Planes comerciales (rol superadmin), vía API central.

Crear y editar planes (nombre, precio mensual, cámaras) y activarlos o
desactivarlos. Un plan desactivado ya no se ofrece a clientes nuevos, pero los
condominios que lo tienen lo conservan. Un precio nuevo rige para los pagos que
se registren desde ese momento: los ya registrados mantienen su monto.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from gui.view_provider import _api, BG_DARK, BG_PANEL, BG_ITEM, FG_GREEN, FG_WHITE, \
    FG_GRAY, FG_WARN, FG_BLUE


class PlansView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self._app = app
        self._planes: list = []
        self._editando = None   # idplan en edición, o None para uno nuevo
        self._build_ui()

    def _build_ui(self):
        top = tk.Frame(self, bg=BG_PANEL, height=50)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="💲  Planes y precios", font=("Segoe UI", 14, "bold"),
                 bg=BG_PANEL, fg=FG_GREEN).pack(side=tk.LEFT, padx=20, pady=10)

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # formulario
        form = tk.Frame(body, bg=BG_PANEL, width=330)
        form.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        form.pack_propagate(False)
        self._titulo = tk.Label(form, text="Nuevo plan", font=("Segoe UI", 12, "bold"),
                                bg=BG_PANEL, fg=FG_GREEN)
        self._titulo.pack(anchor=tk.W, padx=15, pady=12)
        ff = tk.Frame(form, bg=BG_PANEL)
        ff.pack(fill=tk.X, padx=15)
        self._e = {}
        for r, (label, key) in enumerate([("Nombre *", "nombre"),
                                          ("Precio mensual (CLP) *", "precio_mensual"),
                                          ("Máximo de cámaras *", "max_camaras")]):
            tk.Label(ff, text=label, font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE,
                     anchor=tk.W).grid(row=r, column=0, sticky=tk.W, pady=4)
            e = tk.Entry(ff, font=("Segoe UI", 10), width=16, bg=BG_ITEM, fg=FG_WHITE,
                         insertbackground=FG_WHITE)
            e.grid(row=r, column=1, pady=4, padx=(6, 0))
            self._e[key] = e
        self._activo = tk.BooleanVar(value=True)
        tk.Checkbutton(ff, text="Ofrecido a clientes nuevos (activo)", variable=self._activo,
                       bg=BG_PANEL, fg=FG_WHITE, selectcolor=BG_ITEM, activebackground=BG_PANEL,
                       font=("Segoe UI", 9)).grid(row=3, column=0, columnspan=2, sticky=tk.W,
                                                  pady=(6, 0))
        tk.Label(form, text="Un precio nuevo rige para los pagos que se\nregistren desde ahora; "
                            "los anteriores conservan\nel monto cobrado.",
                 font=("Segoe UI", 8), bg=BG_PANEL, fg=FG_GRAY, justify=tk.LEFT).pack(
            anchor=tk.W, padx=15, pady=(10, 0))
        row = tk.Frame(form, bg=BG_PANEL)
        row.pack(pady=15)
        tk.Button(row, text="Guardar", command=self._guardar, font=("Segoe UI", 10, "bold"),
                  bg=FG_GREEN, fg="black", width=10, relief=tk.FLAT,
                  cursor="hand2").pack(side=tk.LEFT, padx=4)
        tk.Button(row, text="Nuevo", command=self._nuevo, font=("Segoe UI", 10),
                  bg=BG_ITEM, fg=FG_WHITE, width=10, relief=tk.FLAT,
                  cursor="hand2").pack(side=tk.LEFT, padx=4)

        # lista
        right = tk.Frame(body, bg=BG_PANEL)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cols = ("nombre", "precio", "camaras", "estado", "uso")
        self._tree = ttk.Treeview(right, columns=cols, show="headings", height=14)
        for col, hdr, w in [("nombre", "Plan", 160), ("precio", "Precio mensual", 130),
                            ("camaras", "Cámaras", 80), ("estado", "Estado", 110),
                            ("uso", "Condominios con el plan", 170)]:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, anchor=tk.W)
        self._tree.tag_configure("inactivo", foreground=FG_GRAY)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._editar())
        tk.Label(right, text="Seleccione un plan para editarlo.", font=("Segoe UI", 9),
                 bg=BG_PANEL, fg=FG_GRAY).pack(anchor=tk.W, padx=10, pady=(0, 8))

    def _load(self):
        data = _api("GET", "/api/proveedor/planes?todos=1", parent=self)
        if data is None:
            return
        self._planes = data
        for r in self._tree.get_children():
            self._tree.delete(r)
        for p in data:
            self._tree.insert("", tk.END, iid=str(p["idplan"]),
                              tags=() if p["activo"] else ("inactivo",), values=(
                p["nombre"], f"${p['precio_mensual']:,}".replace(",", "."), p["max_camaras"],
                "Activo" if p["activo"] else "Desactivado", p["suscripciones"]))

    def _nuevo(self):
        self._editando = None
        self._titulo.config(text="Nuevo plan")
        for e in self._e.values():
            e.delete(0, tk.END)
        self._activo.set(True)
        self._tree.selection_remove(self._tree.selection())

    def _editar(self):
        sel = self._tree.selection()
        if not sel:
            return
        p = next(x for x in self._planes if str(x["idplan"]) == sel[0])
        self._editando = p["idplan"]
        self._titulo.config(text=f"Editar plan: {p['nombre']}")
        for key in self._e:
            self._e[key].delete(0, tk.END)
            self._e[key].insert(0, str(p[key]))
        self._activo.set(bool(p["activo"]))

    def _guardar(self):
        body = {k: e.get().strip().replace(".", "").replace("$", "") if k != "nombre"
                else e.get().strip() for k, e in self._e.items()}
        body["activo"] = self._activo.get()
        if self._editando is None:
            r = _api("POST", "/api/proveedor/planes", body, self)
        else:
            p = next(x for x in self._planes if x["idplan"] == self._editando)
            if (str(p["precio_mensual"]) != body["precio_mensual"] and p["suscripciones"]
                    and not messagebox.askyesno(
                        "Cambiar precio",
                        f"{p['suscripciones']} condominio(s) tienen el plan {p['nombre']}.\n"
                        "El precio nuevo se cobrará en sus próximos pagos.\n\n¿Continuar?",
                        parent=self)):
                return
            r = _api("POST", f"/api/proveedor/planes/{self._editando}", body, self)
        if r is not None:
            self._load()
            self._nuevo()

    def on_show(self):
        self._load()
