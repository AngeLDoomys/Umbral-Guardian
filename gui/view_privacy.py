# -*- coding: utf-8 -*-
"""
gui/view_privacy.py - Solicitudes de derechos del titular (arts. 4 a 11, Ley 21.719).

Cada solicitud queda registrada con su plazo legal (30 días corridos; 2 días
hábiles para el bloqueo) y se ejecuta desde aquí: exportación (acceso y
portabilidad), supresión, oposición al tratamiento biométrico y bloqueo.
"""

import json
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk, messagebox, filedialog, simpledialog

from core import session
from database import DatabaseManager

BG_DARK   = "#1e1e2e"
BG_PANEL  = "#2d2d44"
BG_ITEM   = "#3d3d5c"
FG_GREEN  = "#00ff88"
FG_WHITE  = "#ffffff"
FG_GRAY   = "#aaaaaa"
FG_WARN   = "#ffaa00"
FG_RED    = "#ff4444"
FG_BLUE   = "#4488ff"

TIPOS = {
    "acceso":        "Acceso (copia de sus datos)",
    "portabilidad":  "Portabilidad (archivo estructurado)",
    "rectificacion": "Rectificación (corregir datos)",
    "supresion":     "Supresión (eliminar sus datos)",
    "oposicion":     "Oposición al reconocimiento facial",
    "bloqueo":       "Bloqueo temporal del tratamiento",
}


def plazo_legal(tipo: str, fecha_solicitud: datetime) -> datetime:
    """30 días corridos (art. 11); bloqueo: 2 días hábiles."""
    if tipo != "bloqueo":
        return fecha_solicitud + timedelta(days=30)
    fecha, habiles = fecha_solicitud, 0
    while habiles < 2:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5:
            habiles += 1
    return fecha


class PrivacyView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self._app = app
        self.db = DatabaseManager()
        self._solicitudes: list = []
        self._residentes: list = []
        self._build_ui()

    def _connect_db(self) -> bool:
        return self.db.is_connected() or self.db.connect()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        top = tk.Frame(self, bg=BG_PANEL, height=50)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🔒  Privacidad — Derechos de los titulares",
                 font=("Segoe UI", 14, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            side=tk.LEFT, padx=20, pady=10)

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        form = tk.Frame(body, bg=BG_PANEL, width=360)
        form.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        form.pack_propagate(False)
        tk.Label(form, text="Nueva solicitud", font=("Segoe UI", 12, "bold"),
                 bg=BG_PANEL, fg=FG_GREEN).pack(pady=12, padx=15, anchor=tk.W)

        tk.Label(form, text="Titular (residente):", font=("Segoe UI", 9), bg=BG_PANEL,
                 fg=FG_WHITE).pack(padx=15, anchor=tk.W)
        self.res_var = tk.StringVar()
        self.res_cb = ttk.Combobox(form, textvariable=self.res_var, state="readonly",
                                   font=("Segoe UI", 10))
        self.res_cb.pack(fill=tk.X, padx=15, pady=(0, 8))

        tk.Label(form, text="Derecho que ejerce:", font=("Segoe UI", 9), bg=BG_PANEL,
                 fg=FG_WHITE).pack(padx=15, anchor=tk.W)
        self.tipo_var = tk.StringVar(value=TIPOS["acceso"])
        ttk.Combobox(form, textvariable=self.tipo_var, values=list(TIPOS.values()),
                     state="readonly", font=("Segoe UI", 10)).pack(fill=tk.X, padx=15)

        tk.Button(form, text="Registrar solicitud", command=self._crear,
                  font=("Segoe UI", 11, "bold"), bg=FG_GREEN, fg="black",
                  cursor="hand2").pack(pady=15)

        tk.Label(form, text="Plazos: 30 días corridos para responder (prorrogables una "
                            "vez); 2 días hábiles para el bloqueo temporal. Toda "
                            "denegación debe fundarse (art. 11).",
                 font=("Segoe UI", 8), bg=BG_PANEL, fg=FG_GRAY, wraplength=320,
                 justify=tk.LEFT).pack(padx=15, anchor=tk.W)

        right = tk.Frame(body, bg=BG_PANEL)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        cols = ("fecha", "titular", "rut", "tipo", "estado", "plazo", "gestion")
        self._tree = ttk.Treeview(right, columns=cols, show="headings", height=18)
        for col, hdr, w in [("fecha", "Recibida", 110), ("titular", "Titular", 170),
                            ("rut", "RUT", 100), ("tipo", "Derecho", 120),
                            ("estado", "Estado", 90), ("plazo", "Plazo", 120),
                            ("gestion", "Gestionada por", 140)]:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, anchor=tk.W)
        self._tree.tag_configure("vencida", foreground=FG_RED)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        btns = tk.Frame(right, bg=BG_PANEL)
        btns.pack(fill=tk.X, padx=10, pady=5)
        for text, cmd, bg in [("✔ Ejecutar y cerrar", self._ejecutar, FG_GREEN),
                              ("✖ Rechazar (fundado)", self._rechazar, FG_RED),
                              ("🔓 Levantar bloqueo", self._levantar_bloqueo, FG_BLUE)]:
            tk.Button(btns, text=text, command=cmd, font=("Segoe UI", 10, "bold"), bg=bg,
                      fg="black" if bg == FG_GREEN else FG_WHITE, cursor="hand2",
                      relief=tk.FLAT, padx=8).pack(side=tk.LEFT, padx=4)

    # ── datos ─────────────────────────────────────────────────────────────

    def _load(self):
        if not self._connect_db():
            return
        self._residentes = self.db.list_residentes()
        self.res_cb.configure(values=[self._label(r) for r in self._residentes])
        self._solicitudes = self.db.list_solicitudes()
        for row in self._tree.get_children():
            self._tree.delete(row)
        ahora = datetime.now()
        for s in self._solicitudes:
            limite = plazo_legal(s["tipo"], s["fecha_solicitud"])
            vencida = s["estado"] == "pendiente" and ahora > limite
            self._tree.insert("", tk.END, iid=str(s["idsolicitud"]),
                              tags=("vencida",) if vencida else (), values=(
                f"{s['fecha_solicitud']:%d/%m/%Y}", s["titular"] or "(datos suprimidos)",
                s["rut_titular"], s["tipo"].capitalize(), s["estado"].capitalize(),
                f"{limite:%d/%m/%Y}" + (" VENCIDA" if vencida else ""),
                s["gestionada_por"] or "—"))

    @staticmethod
    def _label(r):
        return f"{r['nombres']} {r['apellidos']} — {r['unidad']} ({r['rut']})"

    def _selected(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione una solicitud")
            return None
        s = next(x for x in self._solicitudes if str(x["idsolicitud"]) == sel[0])
        if s["estado"] != "pendiente":
            messagebox.showinfo("Aviso", "La solicitud ya fue respondida")
            return None
        return s

    # ── acciones ──────────────────────────────────────────────────────────

    def _crear(self):
        labels = [self._label(r) for r in self._residentes]
        if self.res_var.get() not in labels:
            messagebox.showerror("Error", "Seleccione al titular")
            return
        r = self._residentes[labels.index(self.res_var.get())]
        tipo = next(k for k, v in TIPOS.items() if v == self.tipo_var.get())
        self.db.create_solicitud(r["idresidente"], r["rut"], tipo)
        self._load()

    def _cerrar(self, s, estado, observacion):
        self.db.cerrar_solicitud(s["idsolicitud"], estado, observacion,
                                 session.current.idcuenta)
        self._load()

    def _ejecutar(self):
        s = self._selected()
        if not s:
            return
        if s["idresidente"] is None:
            self._cerrar(s, "acogida", "Datos ya suprimidos")
            return
        tipo = s["tipo"]

        if tipo in ("acceso", "portabilidad"):
            path = filedialog.asksaveasfilename(
                title="Guardar datos del titular", defaultextension=".json",
                initialfile=f"datos_{s['rut_titular']}.json",
                filetypes=[("JSON", "*.json")])
            if not path:
                return
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.db.exportar_residente(s["idresidente"]), f,
                          ensure_ascii=False, indent=2, default=str)
            self._cerrar(s, "acogida", f"Datos entregados en formato JSON ({tipo})")

        elif tipo == "supresion":
            if not messagebox.askyesno("Confirmar supresión",
                                       "Se eliminarán definitivamente los datos del titular, "
                                       "su consentimiento y su plantilla facial.\n¿Continuar?"):
                return
            self.db.delete_residente(s["idresidente"])
            self._cerrar(s, "acogida", "Datos suprimidos; registros de acceso anonimizados")

        elif tipo == "oposicion":
            self.db.revocar_consentimiento(s["idresidente"])
            self._cerrar(s, "acogida", "Se detuvo el reconocimiento facial y se eliminó "
                                       "la plantilla")

        elif tipo == "bloqueo":
            self.db.set_bloqueo(s["idresidente"], True)
            self._cerrar(s, "acogida", "Tratamiento bloqueado temporalmente")

        elif tipo == "rectificacion":
            if not messagebox.askyesno("Rectificación",
                                       "Corrija los datos desde la pantalla Residentes "
                                       "(botón Editar).\n¿Ya fueron corregidos?"):
                return
            self._cerrar(s, "acogida", "Datos rectificados")

    def _rechazar(self):
        s = self._selected()
        if not s:
            return
        motivo = simpledialog.askstring("Rechazar solicitud",
                                        "Indique la causa y los antecedentes que la justifican "
                                        "(se informará al titular que puede reclamar ante la "
                                        "Agencia en 30 días hábiles):", parent=self)
        if motivo and motivo.strip():
            self._cerrar(s, "rechazada", motivo.strip()[:500])

    def _levantar_bloqueo(self):
        labels = [self._label(r) for r in self._residentes if r["tratamiento_bloqueado"]]
        if not labels:
            messagebox.showinfo("Aviso", "No hay titulares con el tratamiento bloqueado")
            return
        r = next(r for r in self._residentes if self._label(r) == self.res_var.get()) \
            if self.res_var.get() in labels else None
        if not r:
            messagebox.showinfo("Aviso", "Seleccione arriba al titular bloqueado:\n\n" +
                                "\n".join(labels))
            return
        self.db.set_bloqueo(r["idresidente"], False)
        messagebox.showinfo("Listo", "Bloqueo levantado")
        self._load()

    def on_show(self):
        self._load()
