# -*- coding: utf-8 -*-
"""
gui/view_history.py - Historial de accesos + búsqueda de un residente por foto.
La búsqueda por foto solo compara contra residentes con consentimiento vigente.
"""

import heapq
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import cv2
import numpy as np
from PIL import Image, ImageTk

import config
from core.face_utils import compute_embedding
from database import DatabaseManager

BG_DARK   = "#1e1e2e"
BG_PANEL  = "#2d2d44"
BG_ITEM   = "#3d3d5c"
BG_HOVER  = "#4a4a6a"
FG_GREEN  = "#00ff88"
FG_WHITE  = "#ffffff"
FG_GRAY   = "#aaaaaa"
FG_WARN   = "#ffaa00"
FG_RED    = "#ff4444"
FG_BLUE   = "#4488ff"

RESULTADOS = {"reconocido": "Residente", "no_reconocido": "No reconocido",
              "residente": "Residente", "visita": "Visita", "no_registrado": "No registrado"}


def mezclar_detecciones(personas: list, vehiculos: list) -> list:
    """Une ambas listas sin alterar el orden de registro de cada una: reordenar todo por
    fecha volvería a esconder lo nuevo si el reloj del equipo retrocedió."""
    return list(heapq.merge(personas, vehiculos, key=lambda x: x[0]["fecha_hora"], reverse=True))


class HistoryView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self._app = app
        self.db = DatabaseManager()
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self.foto_cargada = None
        self._refresh_job = None
        self._build_ui()

    def _connect_db(self) -> bool:
        return self.db.is_connected() or self.db.connect()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        top = tk.Frame(self, bg=BG_PANEL, height=50)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="📋  Historial de accesos",
                 font=("Segoe UI", 14, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            side=tk.LEFT, padx=20, pady=10)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_ITEM, foreground=FG_WHITE,
                        padding=[15, 7], font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", FG_GREEN)],
                  foreground=[("selected", "black")])
        style.configure("Treeview", background="white", foreground="black",
                        rowheight=25, fieldbackground="white", font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background=BG_ITEM, foreground=FG_WHITE,
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#cce8ff")],
                  foreground=[("selected", "black")])

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        tab_detec = tk.Frame(nb, bg=BG_DARK)
        nb.add(tab_detec, text="Detecciones")
        tab_busqueda = tk.Frame(nb, bg=BG_DARK)
        nb.add(tab_busqueda, text="Búsqueda por foto")
        self._build_tab_detections(tab_detec)
        self._build_tab_search(tab_busqueda)

    # ── pestaña detecciones ───────────────────────────────────────────────

    def _build_tab_detections(self, parent):
        filter_row = tk.Frame(parent, bg=BG_PANEL, height=45)
        filter_row.pack(fill=tk.X)
        filter_row.pack_propagate(False)

        tk.Label(filter_row, text="Tipo:", font=("Segoe UI", 10),
                 bg=BG_PANEL, fg=FG_WHITE).pack(side=tk.LEFT, padx=10, pady=10)
        self.det_type_var = tk.StringVar(value="Todos")
        for val, text in [("Todos", "Todos"), ("rostros", "Personas"),
                          ("vehiculos", "Vehículos")]:
            tk.Radiobutton(filter_row, text=text, variable=self.det_type_var, value=val,
                           command=self._load_detections, bg=BG_PANEL, fg=FG_WHITE,
                           selectcolor=BG_ITEM, activebackground=BG_PANEL,
                           font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=5)

        tk.Button(filter_row, text="🔄 Actualizar", command=self._load_detections,
                  font=("Segoe UI", 10), bg=BG_ITEM, fg=FG_WHITE,
                  cursor="hand2", relief=tk.FLAT).pack(side=tk.RIGHT, padx=10)

        cols = ("fecha", "tipo", "detalle", "resultado", "confianza", "zona")
        self._det_tree = ttk.Treeview(parent, columns=cols, show="headings", height=22)
        for col, hdr, w in [("fecha", "Fecha/Hora", 150), ("tipo", "Tipo", 80),
                            ("detalle", "Detalle", 260), ("resultado", "Resultado", 120),
                            ("confianza", "Confianza", 80), ("zona", "Zona / cámara", 220)]:
            self._det_tree.heading(col, text=hdr)
            self._det_tree.column(col, width=w, anchor=tk.W)
        sb = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self._det_tree.yview)
        self._det_tree.configure(yscrollcommand=sb.set)
        self._det_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)
        sb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 5), pady=5)

    def _load_detections(self):
        if not self._connect_db():
            return
        for row in self._det_tree.get_children():
            self._det_tree.delete(row)
        tipo = self.det_type_var.get()
        personas, vehiculos = [], []
        try:
            if tipo in ("Todos", "rostros"):
                for d in self.db.list_detecciones_rostro(limit=200):
                    detalle = f"{d['persona']} ({d['unidad']})" if d["persona"] else "—"
                    personas.append((d, "Persona", detalle))
            if tipo in ("Todos", "vehiculos"):
                for d in self.db.list_detecciones_vehiculo(limit=200):
                    detalle = d["patente_leida"] + (f"  → {d['unidad']}" if d["unidad"] else "")
                    vehiculos.append((d, "Vehículo", detalle))
        except Exception as e:
            print(f"[HistoryView] Error: {e}")
        for d, tipo_txt, detalle in mezclar_detecciones(personas, vehiculos):
            conf = f"{float(d['confianza']):.0%}" if d["confianza"] is not None else "—"
            self._det_tree.insert("", tk.END, values=(
                f"{d['fecha_hora']:%d/%m/%Y %H:%M:%S}", tipo_txt, detalle,
                RESULTADOS.get(d["resultado"], d["resultado"]), conf,
                f"{d['zona']} / {d['camara']}",
            ))

    # ── pestaña búsqueda por foto ─────────────────────────────────────────

    def _build_tab_search(self, parent):
        body = tk.Frame(parent, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left = tk.Frame(body, bg=BG_PANEL, width=480)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left.pack_propagate(False)
        tk.Label(left, text="Buscar residente por foto",
                 font=("Segoe UI", 13, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(pady=12)

        img_box = tk.Frame(left, bg=BG_PANEL, width=420, height=420)
        img_box.pack()
        img_box.pack_propagate(False)
        self.img_lbl = tk.Label(img_box, bg="black", text="Sin imagen",
                                font=("Segoe UI", 11), fg=FG_GRAY)
        self.img_lbl.place(relx=0.5, rely=0.5, anchor=tk.CENTER, width=400, height=400)

        tk.Button(left, text="📁 CARGAR FOTO", command=self._load_photo,
                  font=("Segoe UI", 12, "bold"), bg=FG_BLUE, fg=FG_WHITE,
                  width=24, height=2, cursor="hand2", relief=tk.FLAT).pack(pady=12)
        self.btn_search = tk.Button(left, text="🔍 BUSCAR", command=self._search,
                                    font=("Segoe UI", 12, "bold"), bg=FG_GREEN, fg="black",
                                    width=24, height=2, cursor="hand2", relief=tk.FLAT,
                                    state=tk.DISABLED)
        self.btn_search.pack(pady=5)
        self.search_status = tk.Label(left, text="Esperando foto...", font=("Segoe UI", 10),
                                      bg=BG_PANEL, fg=FG_GRAY, wraplength=420)
        self.search_status.pack(pady=10)

        right = tk.Frame(body, bg=BG_PANEL)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        tk.Label(right, text="Resultado", font=("Segoe UI", 13, "bold"),
                 bg=BG_PANEL, fg=FG_GREEN).pack(pady=12)
        rc = tk.Frame(right, bg=BG_PANEL)
        rc.pack(fill=tk.BOTH, expand=True, padx=10)
        canvas = tk.Canvas(rc, bg=BG_PANEL, highlightthickness=0)
        vsb = tk.Scrollbar(rc, orient=tk.VERTICAL, command=canvas.yview)
        self.results_frame = tk.Frame(canvas, bg=BG_PANEL)
        self.results_frame.bind("<Configure>",
                                lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.results_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

    def _clear_results(self):
        for w in self.results_frame.winfo_children():
            w.destroy()

    def _load_photo(self):
        path = filedialog.askopenfilename(title="Seleccionar foto",
                                          filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.bmp")])
        if not path:
            return
        frame = cv2.imread(path)
        if frame is None:
            messagebox.showerror("Error", "No se pudo leer la imagen")
            return
        faces = self.face_cascade.detectMultiScale(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                                                   1.1, 5, minSize=(100, 100))
        if len(faces) == 0:
            messagebox.showerror("Error", "No se detectó un rostro en la imagen")
            return
        (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
        m = int(w * 0.2)
        self.foto_cargada = frame[max(0, y - m):min(frame.shape[0], y + h + m),
                                  max(0, x - m):min(frame.shape[1], x + w + m)]
        rgb = cv2.cvtColor(self.foto_cargada, cv2.COLOR_BGR2RGB)
        img = ImageTk.PhotoImage(Image.fromarray(rgb).resize((400, 400)))
        self.img_lbl.config(image=img, text="")
        self.img_lbl.image = img
        self.btn_search.config(state=tk.NORMAL)
        self.search_status.config(text="✅ Rostro detectado — listo para buscar", fg=FG_GREEN)

    def _search(self):
        if self.foto_cargada is None or not self._connect_db():
            return
        self.search_status.config(text="🔍 Buscando...", fg=FG_WARN)
        self.update()
        try:
            query = np.array(compute_embedding(self.foto_cargada))
        except Exception as e:
            messagebox.showerror("Error", f"Error al procesar la foto: {e}")
            return

        best, best_dist = None, float("inf")
        for p in self.db.get_plantillas_activas():
            emb = np.array(p["embedding"])
            dist = 1.0 - float(np.dot(query, emb) /
                               (np.linalg.norm(query) * np.linalg.norm(emb) + 1e-9))
            if dist < best_dist:
                best, best_dist = p, dist

        self._clear_results()
        if best is None or best_dist >= config.FACE_RECOGNITION_THRESHOLD:
            self.search_status.config(text="❌ No corresponde a un residente registrado",
                                      fg=FG_RED)
            tk.Label(self.results_frame, text="Sin coincidencias", font=("Segoe UI", 16, "bold"),
                     bg=BG_PANEL, fg=FG_RED).pack(pady=20)
            return
        conf = 1.0 - best_dist
        self.search_status.config(text=f"✅ Coincidencia {conf:.0%}", fg=FG_GREEN)
        self._show_results(best, conf)

    def _show_results(self, persona: dict, conf: float):
        info = tk.Frame(self.results_frame, bg=BG_ITEM, relief=tk.RAISED, bd=2)
        info.pack(padx=20, pady=8, fill=tk.X)
        tk.Label(info, text=f"👤 {persona['nombres']} {persona['apellidos']}",
                 font=("Segoe UI", 14, "bold"), bg=BG_ITEM, fg=FG_WHITE).pack(pady=(12, 4))
        tk.Label(info, text=f"Unidad: {persona['unidad']}  |  Coincidencia: {conf:.0%}",
                 font=("Segoe UI", 11), bg=BG_ITEM, fg=FG_GREEN).pack(pady=(0, 12))

        historial = self.db.historial_residente(persona["idresidente"])
        tk.Label(self.results_frame, text=f"📊 {len(historial)} registros de acceso",
                 font=("Segoe UI", 12, "bold"), bg=BG_PANEL, fg=FG_WHITE).pack(pady=8)
        for d in historial[:30]:
            tk.Label(self.results_frame,
                     text=f"📅 {d['fecha_hora']:%d/%m/%Y %H:%M:%S}   {d['zona']} / {d['camara']}",
                     font=("Segoe UI", 10), bg=BG_HOVER, fg=FG_WHITE, anchor=tk.W).pack(
                padx=25, pady=2, fill=tk.X)
        if len(historial) > 30:
            tk.Label(self.results_frame, text=f"... y {len(historial) - 30} más",
                     font=("Segoe UI", 10, "italic"), bg=BG_PANEL, fg=FG_GRAY).pack(pady=8)

    # ── lifecycle ─────────────────────────────────────────────────────────

    def on_show(self):
        self._load_detections()
        self._schedule_refresh()

    def on_hide(self):
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None

    def _schedule_refresh(self):
        self._refresh_job = self.after(10000, self._auto_refresh)

    def _auto_refresh(self):
        self._load_detections()
        self._schedule_refresh()
