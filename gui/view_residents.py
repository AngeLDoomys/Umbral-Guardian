# -*- coding: utf-8 -*-
"""
gui/view_residents.py - Residentes, consentimiento biométrico y enrolamiento facial.

Flujo (Ley 21.719): ficha del residente -> consentimiento expreso informado
(art. 16 ter; tutor si es menor de 16, art. 16 quáter) -> captura del rostro.
Solo se almacena la plantilla facial (vector), nunca la fotografía.
"""

import re
import threading
import time
import tkinter as tk
from datetime import date, datetime
from tkinter import ttk, messagebox, filedialog

import cv2
import numpy as np
from PIL import Image, ImageTk

import config
from core import session
from core.face_utils import compute_embedding
from core.security import valid_rut, format_rut
from core.texto import clave_busqueda
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
FG_PURPLE = "#9966ff"

MAX_CAPTURES = config.MAX_CAPTURES
MIN_CAPTURE_DIFF = config.MIN_CAPTURE_DIFF
EDAD_CONSENTIMIENTO_PROPIO = 16

from core.textos import TEXTO_CONSENTIMIENTO  # noqa: E402  (compartido con el registro móvil)


def _parse_fecha(texto: str):
    texto = texto.strip()
    if not texto:
        return None
    return datetime.strptime(texto, "%d-%m-%Y").date()


def _edad(nacimiento) -> int:
    hoy = date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


class ResidentsView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self._app = app
        self.db = DatabaseManager()
        self._residentes: list = []
        self._tipos: list = []
        self._editing_id = None
        self._build_ui()

    def _connect_db(self) -> bool:
        return self.db.is_connected() or self.db.connect()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        top = tk.Frame(self, bg=BG_PANEL, height=50)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="👤  Residentes",
                 font=("Segoe UI", 14, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            side=tk.LEFT, padx=20, pady=10)

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ── formulario ────────────────────────────────────────────────────
        form = tk.Frame(body, bg=BG_PANEL, width=400)
        form.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        form.pack_propagate(False)

        self._form_title = tk.Label(form, text="Nuevo residente", font=("Segoe UI", 13, "bold"),
                                    bg=BG_PANEL, fg=FG_GREEN)
        self._form_title.pack(pady=(12, 6))

        ff = tk.Frame(form, bg=BG_PANEL)
        ff.pack(fill=tk.X, padx=15)
        self.entries: dict[str, tk.Entry] = {}

        def row(r, label, key):
            tk.Label(ff, text=label, font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE,
                     anchor=tk.W).grid(row=r, column=0, sticky=tk.W, pady=4, padx=4)
            e = tk.Entry(ff, font=("Segoe UI", 10), width=24, bg=BG_ITEM, fg=FG_WHITE,
                         insertbackground=FG_WHITE)
            e.grid(row=r, column=1, pady=4, padx=4, sticky=tk.EW)
            self.entries[key] = e

        row(0, "RUT *", "rut")
        row(1, "Nombres *", "nombres")
        row(2, "Apellidos *", "apellidos")

        tk.Label(ff, text="Unidad *", font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE,
                 anchor=tk.W).grid(row=3, column=0, sticky=tk.W, pady=4, padx=4)
        self.unidad_var = tk.StringVar()
        self.unidad_cb = ttk.Combobox(ff, textvariable=self.unidad_var, font=("Segoe UI", 10))
        self.unidad_cb.grid(row=3, column=1, pady=4, padx=4, sticky=tk.EW)

        tk.Label(ff, text="Tipo *", font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE,
                 anchor=tk.W).grid(row=4, column=0, sticky=tk.W, pady=4, padx=4)
        self.tipo_var = tk.StringVar()
        self.tipo_cb = ttk.Combobox(ff, textvariable=self.tipo_var, state="readonly",
                                    font=("Segoe UI", 10))
        self.tipo_cb.grid(row=4, column=1, pady=4, padx=4, sticky=tk.EW)

        row(5, "Nacimiento (dd-mm-aaaa)", "nacimiento")
        row(6, "Teléfono", "telefono")
        row(7, "Email", "email")
        ff.columnconfigure(1, weight=1)

        tk.Label(form, text="La fecha de nacimiento solo se usa para exigir la\n"
                            "autorización de un tutor a menores de 16 años.",
                 font=("Segoe UI", 8), bg=BG_PANEL, fg=FG_GRAY, justify=tk.LEFT).pack(
            padx=15, anchor=tk.W)

        btns = tk.Frame(form, bg=BG_PANEL)
        btns.pack(pady=12)
        tk.Button(btns, text="Guardar", command=self._guardar, font=("Segoe UI", 11, "bold"),
                  bg=FG_GREEN, fg="black", width=12, cursor="hand2").pack(side=tk.LEFT, padx=4)
        tk.Button(btns, text="Limpiar", command=self._limpiar, font=("Segoe UI", 11),
                  bg=BG_ITEM, fg=FG_WHITE, width=10, cursor="hand2").pack(side=tk.LEFT, padx=4)

        # ── listado ───────────────────────────────────────────────────────
        right = tk.Frame(body, bg=BG_PANEL)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        sf = tk.Frame(right, bg=BG_PANEL)
        sf.pack(fill=tk.X, padx=10, pady=(10, 4))
        tk.Label(sf, text="Buscar:", font=("Segoe UI", 10), bg=BG_PANEL,
                 fg=FG_WHITE).pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._fill_tree())
        tk.Entry(sf, textvariable=self.search_var, font=("Segoe UI", 10), bg=BG_ITEM,
                 fg=FG_WHITE, insertbackground=FG_WHITE).pack(side=tk.LEFT, fill=tk.X,
                                                                expand=True, padx=6)

        cols = ("unidad", "nombre", "rut", "tipo", "consent", "rostro", "bloqueo")
        self._tree = ttk.Treeview(right, columns=cols, show="headings", height=18)
        for col, hdr, w in [("unidad", "Unidad", 90), ("nombre", "Nombre", 200),
                            ("rut", "RUT", 100), ("tipo", "Tipo", 110),
                            ("consent", "Consentimiento", 110), ("rostro", "Rostro", 70),
                            ("bloqueo", "Bloqueado", 80)]:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, anchor=tk.W)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=10)

        acts = tk.Frame(right, bg=BG_PANEL)
        acts.pack(fill=tk.X, padx=10, pady=8)
        acciones = [("✎ Editar", self._editar, FG_BLUE),
                    ("📝 Consentimiento", self._consentimiento, FG_PURPLE),
                    ("📸 Capturar rostro", self._capturar, FG_GREEN)]
        # la supresión de datos la ejecuta solo el administrador
        if session.current.is_admin:
            acciones.append(("🗑 Dar de baja", self._baja, FG_RED))
        for text, cmd, bg in acciones:
            tk.Button(acts, text=text, command=cmd, font=("Segoe UI", 10, "bold"), bg=bg,
                      fg="black" if bg == FG_GREEN else FG_WHITE, cursor="hand2",
                      relief=tk.FLAT, padx=8).pack(side=tk.LEFT, padx=4)

    # ── datos ─────────────────────────────────────────────────────────────

    def _load(self):
        if not self._connect_db():
            messagebox.showerror("Error", "Sin conexión a la base de datos")
            return
        self._tipos = self.db.list_tipos_residente()
        self.tipo_cb.configure(values=[t["nombre"] for t in self._tipos])
        if self._tipos and not self.tipo_var.get():
            self.tipo_cb.current(0)
        self.unidad_cb.configure(values=[u["codigo"] for u in self.db.list_unidades()])
        self._residentes = self.db.list_residentes()
        self._fill_tree()

    def _fill_tree(self):
        for row in self._tree.get_children():
            self._tree.delete(row)
        # sin distinguir mayúsculas ni tildes: «jose» encuentra a «José»
        term = clave_busqueda(self.search_var.get().strip())
        for r in self._residentes:
            texto = clave_busqueda(f"{r['unidad']} {r['nombres']} {r['apellidos']} {r['rut']}")
            if term and term not in texto:
                continue
            self._tree.insert("", tk.END, iid=str(r["idresidente"]), values=(
                r["unidad"], f"{r['nombres']} {r['apellidos']}", r["rut"], r["tipo"],
                "Vigente" if r["consentimiento_vigente"] else "—",
                r["plantillas"] or "—", "Sí" if r["tratamiento_bloqueado"] else "No",
            ))

    def _selected(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione un residente")
            return None
        return next((r for r in self._residentes if str(r["idresidente"]) == sel[0]), None)

    # ── ficha ─────────────────────────────────────────────────────────────

    def _limpiar(self):
        for e in self.entries.values():
            e.config(state=tk.NORMAL)
            e.delete(0, tk.END)
        self.unidad_var.set("")
        self._editing_id = None
        self._form_title.config(text="Nuevo residente")

    def _editar(self):
        r = self._selected()
        if not r:
            return
        self._limpiar()
        self._editing_id = r["idresidente"]
        self._form_title.config(text="Editar residente (rectificación)")
        valores = {"rut": r["rut"], "nombres": r["nombres"], "apellidos": r["apellidos"],
                   "nacimiento": r["fecha_nacimiento"].strftime("%d-%m-%Y")
                   if r["fecha_nacimiento"] else "",
                   "telefono": r["telefono"] or "", "email": r["email"] or ""}
        for k, v in valores.items():
            self.entries[k].insert(0, v)
        self.entries["rut"].config(state=tk.DISABLED)   # el RUT identifica al titular
        self.unidad_var.set(r["unidad"])
        self.tipo_var.set(r["tipo"])

    def _guardar(self):
        if not self._connect_db():
            return
        g = {k: e.get().strip() for k, e in self.entries.items()}
        unidad = self.unidad_var.get().strip()
        if not all([g["rut"], g["nombres"], g["apellidos"], unidad]):
            messagebox.showerror("Error", "Complete los campos obligatorios (*)")
            return
        if not valid_rut(g["rut"]):
            messagebox.showerror("Error", "RUT inválido (revise el dígito verificador)")
            return
        if g["email"] and not re.match(r"[^@]+@[^@]+\.[^@]+", g["email"]):
            messagebox.showerror("Error", "Email inválido")
            return
        try:
            nacimiento = _parse_fecha(g["nacimiento"])
        except ValueError:
            messagebox.showerror("Error", "Fecha de nacimiento: use el formato dd-mm-aaaa")
            return
        idtipo = next((t["idtipo_residente"] for t in self._tipos
                       if t["nombre"] == self.tipo_var.get()), None)
        rut = format_rut(g["rut"])
        try:
            idunidad = self.db.get_or_create_unidad(unidad)
            if self._editing_id:
                self.db.update_residente(self._editing_id, idunidad, idtipo, g["nombres"],
                                         g["apellidos"], nacimiento, g["telefono"] or None,
                                         g["email"] or None)
                messagebox.showinfo("Listo", "Datos del residente actualizados")
            else:
                if self.db.find_residente_by_rut(rut):
                    messagebox.showerror("Error", "Ya existe un residente con ese RUT")
                    return
                self.db.create_residente(idunidad, idtipo, rut, g["nombres"], g["apellidos"],
                                         nacimiento, g["telefono"] or None, g["email"] or None)
                messagebox.showinfo("Listo", "Residente registrado.\n"
                                             "Para usar reconocimiento facial registre su "
                                             "consentimiento y luego capture su rostro.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}")
            return
        self._limpiar()
        self._load()

    def _baja(self):
        r = self._selected()
        if not r:
            return
        if not messagebox.askyesno(
                "Dar de baja",
                f"Se eliminarán los datos de {r['nombres']} {r['apellidos']}, su "
                "consentimiento y su plantilla facial. Sus registros de acceso quedarán "
                "anonimizados.\n\n¿Continuar?"):
            return
        try:
            self.db.delete_residente(r["idresidente"])
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo eliminar:\n{e}")
            return
        self._load()

    # ── consentimiento ────────────────────────────────────────────────────

    def _consentimiento(self):
        r = self._selected()
        if not r:
            return
        vigente = self.db.get_consentimiento_vigente(r["idresidente"])
        if vigente:
            if messagebox.askyesno(
                    "Consentimiento vigente",
                    f"Otorgado el {vigente['fecha_otorgamiento']:%d/%m/%Y} "
                    f"({vigente['medio']}, formulario {vigente['version_formulario']}).\n\n"
                    "¿Desea REVOCARLO? Se eliminará la plantilla facial."):
                self.db.revocar_consentimiento(r["idresidente"])
                self._load()
            return
        ConsentDialog(self, r, self._residentes, self.db, on_done=self._load)

    # ── captura ───────────────────────────────────────────────────────────

    def _capturar(self):
        r = self._selected()
        if not r:
            return
        if r["tratamiento_bloqueado"]:
            messagebox.showwarning("Bloqueado", "El tratamiento de este titular está bloqueado")
            return
        if not r["consentimiento_vigente"]:
            messagebox.showwarning(
                "Consentimiento requerido",
                "No se puede capturar el rostro sin consentimiento expreso vigente "
                "(art. 16 ter).\nUse el botón 'Consentimiento' primero.")
            return
        monitor = getattr(self._app, "_views", {}).get("monitor")
        CaptureDialog(self, r, self.db, on_done=self._load,
                      en_monitor=getattr(monitor, "usb_en_uso", None))

    def on_show(self):
        self._load()


class ConsentDialog(tk.Toplevel):
    """Registra el consentimiento informado y expreso del titular."""

    def __init__(self, parent, residente, residentes, db, on_done):
        super().__init__(parent)
        self.title("Consentimiento para tratamiento biométrico")
        self.geometry("620x640")
        self.configure(bg=BG_PANEL)
        self.transient(parent)
        self.grab_set()
        self._r, self._db, self._on_done = residente, db, on_done

        tk.Label(self, text=f"{residente['nombres']} {residente['apellidos']} — "
                            f"{residente['unidad']}",
                 font=("Segoe UI", 12, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(pady=(12, 6))

        txt = tk.Text(self, height=14, wrap=tk.WORD, font=("Segoe UI", 10), bg=BG_ITEM,
                      fg=FG_WHITE, relief=tk.FLAT)
        txt.insert("1.0", TEXTO_CONSENTIMIENTO.format(modelo=config.FACE_MODEL))
        txt.config(state=tk.DISABLED)
        txt.pack(fill=tk.X, padx=15)

        f = tk.Frame(self, bg=BG_PANEL)
        f.pack(fill=tk.X, padx=15, pady=10)
        tk.Label(f, text="Medio:", bg=BG_PANEL, fg=FG_WHITE,
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky=tk.W)
        self._medio = tk.StringVar(value="escrito")
        ttk.Combobox(f, textvariable=self._medio, values=["escrito", "digital", "verbal"],
                     state="readonly", width=18).grid(row=0, column=1, sticky=tk.W, padx=6)
        tk.Label(f, text=f"Formulario: {config.VERSION_CONSENTIMIENTO}", bg=BG_PANEL,
                 fg=FG_GRAY, font=("Segoe UI", 9)).grid(row=0, column=2, padx=10)

        # tutor para menores de 16 (art. 16 quáter)
        self._menor = bool(residente["fecha_nacimiento"]) and \
            _edad(residente["fecha_nacimiento"]) < EDAD_CONSENTIMIENTO_PROPIO
        self._tutores = [x for x in residentes
                         if x["idunidad"] == residente["idunidad"]
                         and x["idresidente"] != residente["idresidente"]
                         and not (x["fecha_nacimiento"] and _edad(x["fecha_nacimiento"]) < 18)]
        self._tutor = tk.StringVar()
        if self._menor:
            tk.Label(f, text="Tutor que autoriza *:", bg=BG_PANEL, fg=FG_WARN,
                     font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky=tk.W, pady=8)
            ttk.Combobox(f, textvariable=self._tutor, state="readonly", width=40,
                         values=[f"{t['nombres']} {t['apellidos']} ({t['rut']})"
                                 for t in self._tutores]).grid(row=1, column=1, columnspan=2,
                                                               sticky=tk.W, padx=6)

        self._acepta = tk.BooleanVar(value=False)
        quien = "El tutor" if self._menor else "El titular"
        tk.Checkbutton(self, variable=self._acepta, bg=BG_PANEL, fg=FG_WHITE,
                       selectcolor=BG_ITEM, activebackground=BG_PANEL,
                       font=("Segoe UI", 10), wraplength=560, justify=tk.LEFT,
                       text=f"{quien} recibió esta información y otorga su consentimiento "
                            "expreso para el tratamiento de los datos biométricos descritos."
                       ).pack(padx=15, anchor=tk.W)

        tk.Button(self, text="Registrar consentimiento", command=self._save,
                  font=("Segoe UI", 11, "bold"), bg=FG_GREEN, fg="black",
                  cursor="hand2").pack(pady=15)

    def _save(self):
        if not self._acepta.get():
            messagebox.showwarning("Aviso", "Debe confirmar la aceptación", parent=self)
            return
        idtutor = None
        if self._menor:
            nombres = [f"{t['nombres']} {t['apellidos']} ({t['rut']})" for t in self._tutores]
            if self._tutor.get() not in nombres:
                messagebox.showerror(
                    "Tutor requerido",
                    "El titular es menor de 16 años: seleccione al padre, madre o tutor.\n"
                    "Si no aparece, regístrelo primero como residente de la misma unidad.",
                    parent=self)
                return
            idtutor = self._tutores[nombres.index(self._tutor.get())]["idresidente"]
        try:
            self._db.registrar_consentimiento(self._r["idresidente"],
                                              config.VERSION_CONSENTIMIENTO,
                                              self._medio.get(), idtutor,
                                              session.current.idcuenta)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            return
        self.destroy()
        self._on_done()


class CaptureDialog(tk.Toplevel):
    """Captura el rostro (cámara o archivo) y guarda solo la plantilla facial."""

    def __init__(self, parent, residente, db, on_done, en_monitor=None):
        super().__init__(parent)
        self.title("Captura de rostro")
        self._en_monitor = en_monitor   # índice de webcam -> panel del Monitor que la usa
        self.geometry("720x660")
        self.configure(bg=BG_PANEL)
        self.transient(parent)
        self.grab_set()
        self._r, self._db, self._on_done = residente, db, on_done
        self._cap = None
        self._running = False
        self._frame = None
        self._faces = []
        self._captured = 0
        self._embs = []  # vectores de esta sesión, para exigir capturas distintas entre sí
        self._cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

        tk.Label(self, text=f"{residente['nombres']} {residente['apellidos']}",
                 font=("Segoe UI", 12, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(pady=(10, 2))
        self._prog = tk.Label(self, text=f"Capturas: 0/{MAX_CAPTURES}",
                              font=("Segoe UI", 11, "bold"), bg=BG_PANEL, fg=FG_WARN)
        self._prog.pack()
        tk.Label(self, text="Entre captura y captura cambie levemente la pose: de frente, girando "
                            "a cada lado, mirando un poco hacia arriba y hacia abajo",
                 font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_WHITE, wraplength=680).pack()

        row = tk.Frame(self, bg=BG_PANEL)
        row.pack(pady=6)
        # webcam del equipo: la 0 suele ser la integrada; con una USB conectada, la 1
        self._cam_idx = tk.StringVar(value="0")
        tk.Label(row, text="Cámara del equipo:", font=("Segoe UI", 9), bg=BG_PANEL,
                 fg=FG_WHITE).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Combobox(row, textvariable=self._cam_idx, values=["0", "1", "2", "3"],
                     state="readonly", width=3, font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 2))
        self._b_cam = tk.Button(row, text="▶ Cámara", command=self._start, width=12,
                                font=("Segoe UI", 10, "bold"), bg=FG_GREEN, fg="black")
        self._b_cam.pack(side=tk.LEFT, padx=4)
        self._b_cap = tk.Button(row, text="📸 Capturar", command=self._capture_frame, width=12,
                                font=("Segoe UI", 10, "bold"), bg=FG_BLUE, fg=FG_WHITE,
                                state=tk.DISABLED)
        self._b_cap.pack(side=tk.LEFT, padx=4)
        tk.Button(row, text="📁 Cargar foto", command=self._from_file, width=12,
                  font=("Segoe UI", 10, "bold"), bg=FG_PURPLE, fg=FG_WHITE).pack(
            side=tk.LEFT, padx=4)
        tk.Button(row, text="Cerrar", command=self._close, width=10,
                  font=("Segoe UI", 10), bg=BG_ITEM, fg=FG_WHITE).pack(side=tk.LEFT, padx=4)

        self._video = tk.Label(self, bg="black")
        self._video.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
        self.protocol("WM_DELETE_WINDOW", self._close)

    _CAMARA_OCUPADA = (
        "La cámara no entrega imagen.\n\n"
        "Lo más probable es que otro programa la esté usando:\n"
        "  • el Monitor de Umbral Guardian (detenga esa cámara con ⏹ Detener),\n"
        "  • Teams, Zoom, Meet o la app Cámara de Windows.\n\n"
        "Ciérrelos y presione ▶ Cámara otra vez. Si el equipo tiene más de una "
        "cámara, pruebe con otro número en la lista de la izquierda.")

    @staticmethod
    def _abrir_camara(index: int):
        """Abre la webcam y confirma que entrega imagen. En Windows se prueba primero
        DirectShow (más estable con webcams) y luego Media Foundation. Una cámara
        tomada por otro programa se abre igual, pero no entrega cuadros."""
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
            cap = cv2.VideoCapture(index, backend)
            if cap.isOpened():
                fin = time.time() + 3
                while time.time() < fin:
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        return cap
                    time.sleep(0.1)
            cap.release()
        return None

    def _start(self):
        index = int(self._cam_idx.get())
        panel = self._en_monitor(index) if self._en_monitor else None
        if panel:
            messagebox.showwarning(
                "Cámara en uso",
                f"La cámara {index} se está usando en el Monitor (Cámara {panel}).\n\n"
                "Vaya al Monitor, presione ⏹ Detener en ese panel y vuelva a intentarlo.",
                parent=self)
            return
        self._b_cam.config(state=tk.DISABLED, text="Abriendo...")
        self.update_idletasks()
        self._cap = self._abrir_camara(index)
        if self._cap is None:
            self._b_cam.config(state=tk.NORMAL, text="▶ Cámara")
            messagebox.showerror("Cámara", self._CAMARA_OCUPADA, parent=self)
            return
        self._b_cam.config(text="▶ Cámara")
        self._camara_perdida = False
        self._running = True
        self._b_cam.config(state=tk.DISABLED)
        self._b_cap.config(state=tk.NORMAL)
        self._shown = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._refresh()

    def _loop(self):
        """Hilo de lectura: SOLO lee la cámara y busca el rostro. No toca la ventana:
        Tkinter no es thread-safe y, si este hilo actualiza widgets mientras el hilo
        principal muestra un mensaje (p. ej. «Captura repetida»), la ventana se congela."""
        ultimo_ok = time.time()
        while self._running:
            ret, frame = self._cap.read()
            if not ret or frame is None:
                if time.time() - ultimo_ok > 3:   # otro programa tomó la cámara
                    self._camara_perdida = True
                    return
                time.sleep(0.05)
                continue
            ultimo_ok = time.time()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._cascade.detectMultiScale(gray, 1.1, 5, minSize=(100, 100))
            shown = frame.copy()
            for (x, y, w, h) in faces:
                cv2.rectangle(shown, (x, y), (x + w, y + h), (0, 255, 0), 2)
            self._frame, self._faces, self._shown = frame, faces, shown

    def _refresh(self):
        """Dibuja la última imagen desde el hilo principal (~30 veces por segundo)."""
        if not self._running:
            return
        if self._camara_perdida:
            self._running = False
            self._cap.release()
            self._cap = None
            self._b_cam.config(state=tk.NORMAL)
            self._b_cap.config(state=tk.DISABLED)
            messagebox.showerror("Cámara", self._CAMARA_OCUPADA, parent=self)
            return
        shown = self._shown
        if shown is not None:
            h, w = shown.shape[:2]
            s = min(640 / w, 480 / h)          # sin deformar la imagen
            rgb = cv2.cvtColor(cv2.resize(shown, (int(w * s), int(h * s))), cv2.COLOR_BGR2RGB)
            img = ImageTk.PhotoImage(Image.fromarray(rgb))
            self._video.imgtk = img
            self._video.configure(image=img)
        self.after(33, self._refresh)

    def _capture_frame(self):
        if self._frame is None or len(self._faces) == 0:
            messagebox.showwarning("Aviso", "No hay un rostro en la imagen", parent=self)
            return
        # imagen completa: compute_embedding detecta y alinea el rostro por su cuenta
        self._save(self._frame.copy())

    def _from_file(self):
        path = filedialog.askopenfilename(parent=self, title="Seleccionar foto",
                                          filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.bmp")])
        if not path:
            return
        frame = cv2.imread(path)
        if frame is None:
            messagebox.showerror("Error", "No se pudo leer la imagen", parent=self)
            return
        faces = self._cascade.detectMultiScale(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                                               1.1, 5, minSize=(100, 100))
        if len(faces) == 0:
            messagebox.showerror("Error", "No se detectó un rostro en la imagen", parent=self)
            return
        self._save(frame)

    def _save(self, face_crop):
        try:
            emb = compute_embedding(face_crop)
            # cinco fotos casi iguales equivalen a una sola: el residente no se reconoce
            # cuando la cámara del acceso lo ve desde otro ángulo o con otra luz
            v = np.asarray(emb, float)
            for prev in self._embs:
                if 1 - v @ prev / (np.linalg.norm(v) * np.linalg.norm(prev)) < MIN_CAPTURE_DIFF:
                    messagebox.showwarning(
                        "Captura repetida",
                        "Esta captura es casi igual a una anterior y no se guardó.\n"
                        "Cambie levemente la pose (gire la cara o mire un poco hacia "
                        "arriba o abajo) y capture de nuevo.", parent=self)
                    return
            self._db.add_plantilla(self._r["idresidente"], emb, config.FACE_MODEL)
            self._embs.append(v)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar la plantilla:\n{e}", parent=self)
            return
        self._captured += 1
        self._prog.config(text=f"Capturas: {self._captured}/{MAX_CAPTURES}")
        if self._captured >= MAX_CAPTURES:
            messagebox.showinfo("Completado", "Rostro enrolado correctamente", parent=self)
            self._close()

    def _close(self):
        self._running = False
        if getattr(self, "_thread", None):
            self._thread.join(timeout=2)   # que termine la lectura antes de liberar la cámara
        if self._cap:
            self._cap.release()
        self.destroy()
        self._on_done()
