# -*- coding: utf-8 -*-
"""
gui/view_provider.py - Panel del proveedor (rol superadmin), vía API central.

Alta de condominios clientes (con plan, administrador y clave del nodo de su
portería), registro de pagos que extienden la vigencia y suspensión.
El cobro es manual (transferencia): integrar una pasarela de pago es trabajo futuro.
"""

import re
import tkinter as tk
from datetime import date, datetime
from tkinter import ttk, messagebox, simpledialog


def _pesos(n) -> str:
    return f"${int(n):,}".replace(",", ".")

from core import cloud, session
from core.security import valid_rut, format_rut, password_problem
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


def _api(method, path, body=None, parent=None):
    try:
        token = session.current.token
        return cloud.get(path, token) if method == "GET" else cloud.post(path, token, body)
    except cloud.CloudError as e:
        messagebox.showerror("Error", str(e), parent=parent)
        return None


def mostrar_clave_nodo(parent, condominio: str, clave: str):
    """La clave del nodo se muestra una sola vez para instalarla en la portería."""
    dlg = tk.Toplevel(parent)
    dlg.title("Clave del nodo")
    dlg.configure(bg=BG_PANEL)
    dlg.transient(parent)
    dlg.grab_set()
    tk.Label(dlg, text=f"Clave del nodo de {condominio}", font=("Segoe UI", 12, "bold"),
             bg=BG_PANEL, fg=FG_GREEN).pack(padx=20, pady=(15, 5))
    tk.Label(dlg, text="Guárdela ahora: no se vuelve a mostrar. En el PC de la portería "
                       "ejecute:\npython setup_nodo.py --clave <clave> --api <url de la API>",
             font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE, justify=tk.LEFT).pack(padx=20)
    e = tk.Entry(dlg, font=("Consolas", 11), width=52, bg=BG_ITEM, fg=FG_WHITE)
    e.insert(0, clave)
    e.config(state="readonly")
    e.pack(padx=20, pady=10)

    def copiar():
        dlg.clipboard_clear()
        dlg.clipboard_append(clave)

    row = tk.Frame(dlg, bg=BG_PANEL)
    row.pack(pady=(0, 15))
    tk.Button(row, text="Copiar", command=copiar, bg=FG_BLUE, fg=FG_WHITE,
              font=("Segoe UI", 10, "bold"), width=10).pack(side=tk.LEFT, padx=4)
    tk.Button(row, text="Cerrar", command=dlg.destroy, bg=BG_ITEM, fg=FG_WHITE,
              font=("Segoe UI", 10), width=10).pack(side=tk.LEFT, padx=4)


class ProviderView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self._app = app
        self._condominios: list = []
        self._build_ui()

    def _build_ui(self):
        top = tk.Frame(self, bg=BG_PANEL, height=50)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🏢  Proveedor — Condominios y suscripciones",
                 font=("Segoe UI", 14, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            side=tk.LEFT, padx=20, pady=10)

        body = tk.Frame(self, bg=BG_PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        cols = ("nombre", "rut", "comuna", "plan", "vence", "estado", "contacto")
        self._tree = ttk.Treeview(body, columns=cols, show="headings", height=18)
        for col, hdr, w in [("nombre", "Condominio", 210), ("rut", "RUT", 100),
                            ("comuna", "Comuna", 100), ("plan", "Plan", 160),
                            ("vence", "Pagado hasta", 100), ("estado", "Estado", 140),
                            ("contacto", "Último contacto del nodo", 170)]:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, anchor=tk.W)
        self._tree.tag_configure("vencida", foreground=FG_RED)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        filas = [
            [("+ Nuevo condominio", self._nuevo, FG_GREEN),
             ("💵 Registrar pago", self._pago, FG_BLUE),
             ("📜 Historial de pagos", self._historial, FG_BLUE),
             ("🔁 Cambiar plan", self._cambiar_plan, FG_BLUE)],
            [("⏸ Suspender / reactivar", self._suspender, FG_WARN),
             ("👥 Cuentas y contraseñas", self._cuentas, FG_BLUE),
             ("🔑 Nueva clave de nodo", self._nueva_clave, BG_ITEM),
             ("🔄 Actualizar", self._load, BG_ITEM)],
        ]
        for fila in filas:
            btns = tk.Frame(body, bg=BG_PANEL)
            btns.pack(fill=tk.X, padx=10, pady=(4, 4))
            for text, cmd, bg in fila:
                tk.Button(btns, text=text, command=cmd, font=("Segoe UI", 10, "bold"), bg=bg,
                          fg="black" if bg in (FG_GREEN, FG_WARN) else FG_WHITE,
                          cursor="hand2", relief=tk.FLAT, padx=8).pack(side=tk.LEFT, padx=4)

    def _load(self):
        data = _api("GET", "/api/proveedor/condominios", parent=self)
        if data is None:
            return
        self._condominios = data
        for row in self._tree.get_children():
            self._tree.delete(row)
        hoy = date.today()
        for c in self._condominios:
            fin = date.fromisoformat(c["fecha_fin"]) if c["fecha_fin"] else None
            vencida = fin is not None and fin < hoy
            estado = c["estado"] or "sin suscripción"
            if c["estado"] == "activa" and vencida:
                estado = f"vencida ({(hoy - fin).days} días)"
            contacto = (datetime.fromisoformat(c["ultimo_contacto"]).strftime("%d/%m/%Y %H:%M")
                        if c["ultimo_contacto"] else "nunca")
            self._tree.insert("", tk.END, iid=str(c["idcondominio"]),
                              tags=("vencida",) if vencida else (), values=(
                c["nombre"], c["rut"], c["comuna"],
                f"{c['plan']} ({_pesos(c['precio_mensual'])})" if c["plan"] else "—",
                f"{fin:%d/%m/%Y}" if fin else "—", estado, contacto))

    def _selected(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione un condominio")
            return None
        return next(c for c in self._condominios if str(c["idcondominio"]) == sel[0])

    def _nuevo(self):
        planes = _api("GET", "/api/proveedor/planes", parent=self)
        if planes:
            NewClientDialog(self, planes, self._load)

    def _pago(self):
        c = self._selected()
        if c and c["idsuscripcion"]:
            PagoDialog(self, c, self._load)

    def _historial(self):
        c = self._selected()
        if c:
            PagosDialog(self, c, self._load)

    def _cambiar_plan(self):
        c = self._selected()
        if not c or not c["idsuscripcion"]:
            return
        planes = _api("GET", "/api/proveedor/planes", parent=self)
        if planes:
            CambiarPlanDialog(self, c, planes, self._load)

    def _suspender(self):
        c = self._selected()
        if not c or not c["idsuscripcion"]:
            return
        nuevo = "suspendida" if c["estado"] == "activa" else "activa"
        if messagebox.askyesno("Confirmar", f"¿Cambiar la suscripción de {c['nombre']} "
                                            f"a '{nuevo}'?"):
            if _api("POST", f"/api/proveedor/suscripciones/{c['idsuscripcion']}/estado",
                    {"estado": nuevo}, self) is not None:
                self._load()

    def _nueva_clave(self):
        c = self._selected()
        if not c:
            return
        if not messagebox.askyesno("Nueva clave de nodo",
                                   f"Se generará una nueva clave para {c['nombre']} y la "
                                   "anterior dejará de funcionar.\n¿Continuar?"):
            return
        r = _api("POST", f"/api/proveedor/condominios/{c['idcondominio']}/nodo", parent=self)
        if r:
            mostrar_clave_nodo(self, c["nombre"], r["clave_nodo"])

    def _cuentas(self):
        c = self._selected()
        if c:
            CuentasCondominioDialog(self, c)

    def on_show(self):
        self._load()


class CuentasCondominioDialog(tk.Toplevel):
    """Cuentas de un condominio: el proveedor puede restablecer la contraseña de
    cualquiera (p. ej. el único administrador, que no tiene a quién pedírselo)."""

    def __init__(self, parent, condominio: dict):
        super().__init__(parent)
        self.title(f"Cuentas — {condominio['nombre']}")
        self.geometry("760x380")
        self.configure(bg=BG_PANEL)
        self.transient(parent)
        self._cond = condominio
        self._cuentas: list = []

        tk.Label(self, text=f"Cuentas de {condominio['nombre']}", font=("Segoe UI", 12, "bold"),
                 bg=BG_PANEL, fg=FG_GREEN).pack(anchor=tk.W, padx=15, pady=(12, 6))
        cols = ("nombre", "email", "rol", "estado", "acceso")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", height=10)
        for col, hdr, w in [("nombre", "Nombre", 180), ("email", "Correo", 200),
                            ("rol", "Rol", 100), ("estado", "Estado", 140),
                            ("acceso", "Último acceso", 120)]:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, anchor=tk.W)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=15)

        row = tk.Frame(self, bg=BG_PANEL)
        row.pack(fill=tk.X, padx=15, pady=10)
        tk.Button(row, text="🔑 Restablecer contraseña", command=self._restablecer,
                  font=("Segoe UI", 10, "bold"), bg=FG_BLUE, fg=FG_WHITE, relief=tk.FLAT,
                  cursor="hand2", padx=8).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(row, text="⏯ Activar / desactivar", command=self._toggle,
                  font=("Segoe UI", 10, "bold"), bg=FG_WARN, fg="black", relief=tk.FLAT,
                  cursor="hand2", padx=8).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(row, text="Cerrar", command=self.destroy, font=("Segoe UI", 10),
                  bg=BG_ITEM, fg=FG_WHITE, relief=tk.FLAT, padx=8).pack(side=tk.RIGHT)
        self._load()
        self.grab_set()

    def _load(self):
        data = _api("GET", f"/api/proveedor/condominios/{self._cond['idcondominio']}/cuentas",
                    parent=self)
        if data is None:
            return
        self._cuentas = data
        for r in self._tree.get_children():
            self._tree.delete(r)
        for c in data:
            estado = "Activa" if c["activa"] else "Inactiva"
            if c["debe_cambiar_password"]:
                estado += " · clave temporal"
            acceso = (datetime.fromisoformat(c["ultimo_acceso"]).strftime("%d/%m/%Y %H:%M")
                      if c["ultimo_acceso"] else "—")
            self._tree.insert("", tk.END, iid=str(c["idcuenta"]), values=(
                f"{c['nombres']} {c['apellidos']}", c["email"], c["rol"], estado, acceso))

    def _sel(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione una cuenta", parent=self)
            return None
        return next(x for x in self._cuentas if str(x["idcuenta"]) == sel[0])

    def _toggle(self):
        c = self._sel()
        if not c:
            return
        accion = "desactivar" if c["activa"] else "activar"
        if not messagebox.askyesno("Confirmar", f"¿{accion.capitalize()} la cuenta "
                                                f"{c['email']}?", parent=self):
            return
        if _api("POST", f"/api/proveedor/cuentas/{c['idcuenta']}/activa",
                {"activa": not c["activa"]}, self) is not None:
            self._load()

    def _restablecer(self):
        c = self._sel()
        if not c:
            return
        if not messagebox.askyesno(
                "Restablecer contraseña",
                f"Se generará una contraseña temporal para {c['email']}.\n"
                "La actual dejará de funcionar y el usuario deberá cambiarla al ingresar.\n\n"
                "¿Continuar?", parent=self):
            return
        r = _api("POST", f"/api/proveedor/cuentas/{c['idcuenta']}/password", parent=self)
        if r:
            self._load()
            mostrar_password_temporal(self, r["email"], r["password_temporal"])


def _ventana(parent, titulo, geometry):
    w = tk.Toplevel(parent)
    w.title(titulo)
    w.geometry(geometry)
    w.configure(bg=BG_PANEL)
    w.transient(parent)
    return w


class PagoDialog:
    """Registrar un pago: meses, medio y referencia, con el monto calculado."""

    def __init__(self, parent, cond: dict, on_done):
        self._c, self._on_done = cond, on_done
        w = self._w = _ventana(parent, "Registrar pago", "420x330")
        tk.Label(w, text=cond["nombre"], font=("Segoe UI", 12, "bold"), bg=BG_PANEL,
                 fg=FG_GREEN).pack(anchor=tk.W, padx=20, pady=(14, 2))
        tk.Label(w, text=f"Plan {cond['plan']}: {_pesos(cond['precio_mensual'])} mensual",
                 font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE).pack(anchor=tk.W, padx=20)
        f = tk.Frame(w, bg=BG_PANEL)
        f.pack(fill=tk.X, padx=20, pady=10)
        self._meses = tk.IntVar(value=1)
        self._medio = tk.StringVar(value="transferencia")
        tk.Label(f, text="Meses que cubre", bg=BG_PANEL, fg=FG_WHITE,
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky=tk.W, pady=4)
        tk.Spinbox(f, from_=1, to=24, textvariable=self._meses, width=6,
                   font=("Segoe UI", 10), command=self._monto).grid(row=0, column=1, sticky=tk.W)
        tk.Label(f, text="Medio de pago", bg=BG_PANEL, fg=FG_WHITE,
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Combobox(f, textvariable=self._medio, state="readonly", width=16,
                     values=["transferencia", "efectivo", "otro"]).grid(row=1, column=1, sticky=tk.W)
        tk.Label(f, text="N° transferencia / referencia", bg=BG_PANEL, fg=FG_WHITE,
                 font=("Segoe UI", 9)).grid(row=2, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        self._ref = tk.Entry(f, font=("Segoe UI", 10), width=20, bg=BG_ITEM, fg=FG_WHITE,
                             insertbackground=FG_WHITE)
        self._ref.grid(row=2, column=1, sticky=tk.W)
        self._total = tk.Label(w, text="", font=("Segoe UI", 11, "bold"), bg=BG_PANEL,
                               fg=FG_WARN)
        self._total.pack(anchor=tk.W, padx=20)
        self._meses.trace_add("write", lambda *_: self._monto())
        self._monto()
        tk.Button(w, text="Registrar pago", command=self._guardar, font=("Segoe UI", 11, "bold"),
                  bg=FG_GREEN, fg="black", relief=tk.FLAT, cursor="hand2").pack(pady=16)
        w.grab_set()

    def _monto(self):
        try:
            meses = int(self._meses.get())
        except (tk.TclError, ValueError):
            self._total.config(text="")
            return
        self._total.config(text=f"Monto: {_pesos(meses * self._c['precio_mensual'])}")

    def _guardar(self):
        try:
            meses = int(self._meses.get())
        except (tk.TclError, ValueError):
            meses = 0
        if not 1 <= meses <= 24:
            messagebox.showerror("Error", "Meses inválidos (1 a 24)", parent=self._w)
            return
        body = {"meses": meses, "medio": self._medio.get(),
                "referencia": self._ref.get().strip() or None}
        if _api("POST", f"/api/proveedor/suscripciones/{self._c['idsuscripcion']}/pagos",
                body, self._w) is not None:
            self._w.destroy()
            self._on_done()


class PagosDialog:
    """Historial de pagos de un condominio, con anulación del último pago vigente."""

    def __init__(self, parent, cond: dict, on_done):
        self._c, self._on_done = cond, on_done
        self._pagos: list = []
        w = self._w = _ventana(parent, f"Pagos — {cond['nombre']}", "860x420")
        tk.Label(w, text=f"Historial de pagos de {cond['nombre']}", font=("Segoe UI", 12, "bold"),
                 bg=BG_PANEL, fg=FG_GREEN).pack(anchor=tk.W, padx=15, pady=(12, 6))
        cols = ("fecha", "plan", "meses", "monto", "medio", "ref", "estado")
        self._tree = ttk.Treeview(w, columns=cols, show="headings", height=12)
        for col, hdr, wd in [("fecha", "Fecha", 90), ("plan", "Plan", 90), ("meses", "Meses", 55),
                             ("monto", "Monto", 100), ("medio", "Medio", 100),
                             ("ref", "Referencia", 130), ("estado", "Estado", 260)]:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=wd, anchor=tk.W)
        self._tree.tag_configure("anulado", foreground=FG_GRAY)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=15)
        self._total = tk.Label(w, text="", font=("Segoe UI", 10, "bold"), bg=BG_PANEL, fg=FG_WHITE)
        self._total.pack(anchor=tk.W, padx=15, pady=(6, 0))
        row = tk.Frame(w, bg=BG_PANEL)
        row.pack(fill=tk.X, padx=15, pady=10)
        tk.Button(row, text="✖ Anular pago", command=self._anular, font=("Segoe UI", 10, "bold"),
                  bg=FG_RED, fg=FG_WHITE, relief=tk.FLAT, cursor="hand2", padx=8).pack(side=tk.LEFT)
        tk.Label(row, text="Solo el último pago vigente; la vigencia vuelve a la que tenía antes.",
                 font=("Segoe UI", 8), bg=BG_PANEL, fg=FG_GRAY).pack(side=tk.LEFT, padx=10)
        tk.Button(row, text="Cerrar", command=w.destroy, font=("Segoe UI", 10), bg=BG_ITEM,
                  fg=FG_WHITE, relief=tk.FLAT, padx=8).pack(side=tk.RIGHT)
        self._load()
        w.grab_set()

    def _load(self):
        data = _api("GET", f"/api/proveedor/condominios/{self._c['idcondominio']}/pagos",
                    parent=self._w)
        if data is None:
            return
        self._pagos = data
        for r in self._tree.get_children():
            self._tree.delete(r)
        for p in data:
            estado = "Vigente"
            if p["anulado"]:
                estado = f"ANULADO: {p['motivo_anulacion'] or ''}"
            self._tree.insert("", tk.END, iid=str(p["idpago"]),
                              tags=("anulado",) if p["anulado"] else (), values=(
                date.fromisoformat(p["fecha_pago"]).strftime("%d/%m/%Y"), p["plan"], p["meses"],
                _pesos(p["monto"]), p["medio"], p["referencia"] or "—", estado))
        total = sum(p["monto"] for p in data if not p["anulado"])
        self._total.config(text=f"Total pagado (sin anulados): {_pesos(total)}")

    def _anular(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione un pago", parent=self._w)
            return
        p = next(x for x in self._pagos if str(x["idpago"]) == sel[0])
        motivo = simpledialog.askstring(
            "Anular pago", f"Pago de {_pesos(p['monto'])} ({p['meses']} mes(es)).\n"
                           "La vigencia del condominio vuelve a la que tenía antes de este pago.\n\n"
                           "Motivo de la anulación:", parent=self._w)
        if not motivo or not motivo.strip():
            return
        if _api("POST", f"/api/proveedor/pagos/{p['idpago']}/anular",
                {"motivo": motivo.strip()}, self._w) is not None:
            self._load()
            self._on_done()


class CambiarPlanDialog:
    def __init__(self, parent, cond: dict, planes: list, on_done):
        self._c, self._planes, self._on_done = cond, planes, on_done
        w = self._w = _ventana(parent, "Cambiar plan", "430x230")
        tk.Label(w, text=cond["nombre"], font=("Segoe UI", 12, "bold"), bg=BG_PANEL,
                 fg=FG_GREEN).pack(anchor=tk.W, padx=20, pady=(14, 2))
        tk.Label(w, text=f"Plan actual: {cond['plan']} ({_pesos(cond['precio_mensual'])}/mes, "
                         f"{cond['max_camaras']} cámaras)",
                 font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE).pack(anchor=tk.W, padx=20)
        self._labels = [f"{p['nombre']} — {_pesos(p['precio_mensual'])}/mes, "
                        f"{p['max_camaras']} cámaras" for p in planes]
        self._var = tk.StringVar()
        cb = ttk.Combobox(w, textvariable=self._var, values=self._labels, state="readonly",
                          width=44)
        cb.pack(padx=20, pady=12, anchor=tk.W)
        actual = next((i for i, p in enumerate(planes) if p["idplan"] == cond["idplan"]), 0)
        cb.current(actual)
        tk.Label(w, text="Rige para los próximos pagos. El nuevo límite de cámaras llega al\n"
                         "equipo de la portería en su próxima sincronización.",
                 font=("Segoe UI", 8), bg=BG_PANEL, fg=FG_GRAY, justify=tk.LEFT).pack(
            anchor=tk.W, padx=20)
        tk.Button(w, text="Cambiar plan", command=self._guardar, font=("Segoe UI", 11, "bold"),
                  bg=FG_GREEN, fg="black", relief=tk.FLAT, cursor="hand2").pack(pady=12)
        w.grab_set()

    def _guardar(self):
        plan = self._planes[self._labels.index(self._var.get())]
        if plan["idplan"] == self._c["idplan"]:
            self._w.destroy()
            return
        if _api("POST", f"/api/proveedor/suscripciones/{self._c['idsuscripcion']}/plan",
                {"idplan": plan["idplan"]}, self._w) is not None:
            self._w.destroy()
            self._on_done()


class NewClientDialog(tk.Toplevel):
    """Alta de un condominio con su suscripción de prueba, su administrador y su nodo."""

    def __init__(self, parent, planes, on_done):
        super().__init__(parent)
        self.title("Nuevo condominio")
        self.geometry("480x620")
        self.configure(bg=BG_PANEL)
        self.transient(parent)
        self.grab_set()
        self._planes, self._on_done, self._parent = planes, on_done, parent
        self.e: dict[str, tk.Entry] = {}

        def section(text):
            tk.Label(self, text=text, font=("Segoe UI", 11, "bold"), bg=BG_PANEL,
                     fg=FG_GREEN).pack(anchor=tk.W, padx=20, pady=(12, 4))

        def row(label, key, show=""):
            f = tk.Frame(self, bg=BG_PANEL)
            f.pack(fill=tk.X, padx=20, pady=2)
            tk.Label(f, text=label, width=18, anchor=tk.W, bg=BG_PANEL, fg=FG_WHITE,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT)
            e = tk.Entry(f, font=("Segoe UI", 10), bg=BG_ITEM, fg=FG_WHITE,
                         insertbackground=FG_WHITE, show=show)
            e.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.e[key] = e

        section("Condominio")
        row("RUT comunidad *", "rut")
        row("Nombre *", "nombre")
        row("Dirección *", "direccion")
        row("Comuna *", "comuna")
        row("Correo contacto *", "email")
        row("Teléfono", "telefono")

        f = tk.Frame(self, bg=BG_PANEL)
        f.pack(fill=tk.X, padx=20, pady=2)
        tk.Label(f, text="Plan *", width=18, anchor=tk.W, bg=BG_PANEL, fg=FG_WHITE,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self._plan_labels = [f"{p['nombre']} — ${p['precio_mensual']:,}/mes, "
                             f"{p['max_camaras']} cámaras" for p in planes]
        self.plan_var = tk.StringVar()
        cb = ttk.Combobox(f, textvariable=self.plan_var, state="readonly",
                          values=self._plan_labels)
        cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if planes:
            cb.current(0)

        section("Administrador del condominio")
        row("RUT *", "adm_rut")
        row("Nombres *", "adm_nombres")
        row("Apellidos *", "adm_apellidos")
        row("Correo (usuario) *", "adm_email")
        row("Contraseña inicial *", "adm_password", show="●")

        tk.Label(self, text="Se crea con 30 días de servicio; luego registre los pagos "
                            "desde el panel.\nEl administrador deberá cambiar la contraseña "
                            "inicial al ingresar.", font=("Segoe UI", 8), bg=BG_PANEL,
                 fg=FG_GRAY, justify=tk.LEFT).pack(padx=20, anchor=tk.W, pady=(8, 0))
        tk.Button(self, text="Crear condominio", command=self._save,
                  font=("Segoe UI", 11, "bold"), bg=FG_GREEN, fg="black",
                  cursor="hand2").pack(pady=14)

    def _save(self):
        g = {k: e.get().strip() for k, e in self.e.items()}
        if [k for k, v in g.items() if not v and k != "telefono"]:
            messagebox.showerror("Error", "Complete los campos obligatorios (*)", parent=self)
            return
        for key in ("rut", "adm_rut"):
            if not valid_rut(g[key]):
                messagebox.showerror("Error", "RUT inválido", parent=self)
                return
        for key in ("email", "adm_email"):
            if not re.match(r"[^@]+@[^@]+\.[^@]+", g[key]):
                messagebox.showerror("Error", "Correo inválido", parent=self)
                return
        problem = password_problem(g["adm_password"])
        if problem:
            messagebox.showerror("Error", problem, parent=self)
            return
        plan = self._planes[self._plan_labels.index(self.plan_var.get())]
        body = {
            "idplan": plan["idplan"],
            "condominio": {"rut": format_rut(g["rut"]), "nombre": g["nombre"],
                           "direccion": g["direccion"], "comuna": g["comuna"],
                           "email": g["email"], "telefono": g["telefono"]},
            "administrador": {"rut": format_rut(g["adm_rut"]), "nombres": g["adm_nombres"],
                              "apellidos": g["adm_apellidos"], "email": g["adm_email"],
                              "password": g["adm_password"]},
        }
        r = _api("POST", "/api/proveedor/condominios", body, self)
        if not r:
            return
        self.destroy()
        self._on_done()
        mostrar_clave_nodo(self._parent, g["nombre"], r["clave_nodo"])
