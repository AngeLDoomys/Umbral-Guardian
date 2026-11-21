# -*- coding: utf-8 -*-
"""
gui/view_monitor.py - Vista de monitoreo en tiempo real
Muestra hasta dos cámaras a la vez, cada una con su propio motor de detección
y sus detecciones superpuestas.
"""

import tkinter as tk
from tkinter import ttk
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk
from datetime import datetime
import queue
from typing import Optional

import config
from engine.security_engine import SecurityEngine
from core.camera_manager import CameraManager

BG_DARK  = "#1e1e2e"
BG_PANEL = "#2d2d44"
BG_ITEM  = "#3d3d5c"
FG_GREEN = "#00ff88"
FG_WHITE = "#ffffff"
FG_GRAY  = "#aaaaaa"
FG_WARN  = "#ffaa00"
FG_RED   = "#ff4444"

NUM_SLOTS = 2
NO_SIGNAL = "Sin señal — Seleccione cámara e inicie"


class CameraSlot(tk.Frame):
    """Un panel de cámara: selector, controles, video y estadísticas,
    con su propio SecurityEngine corriendo en un hilo aparte."""

    def __init__(self, parent, view: "MonitorView", number: int):
        super().__init__(parent, bg=BG_PANEL)
        self._view = view
        self._number = number
        self._engine = SecurityEngine()
        self._running = False
        self._frame_queue: queue.Queue = queue.Queue(maxsize=2)
        self._cams_list: list = []
        self.running_cam_id: str = ""
        self._running_cam_source = None
        self._running_cam_name: str = ""

        self._build_ui()
        self._engine.set_callbacks(
            on_frame=self._on_frame,
            on_face=self._on_face_event,
            on_vehicle=self._on_vehicle_event,
            on_stats=self._on_stats,
        )

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # celda del panel: controles, video y línea de datos se ubican juntos y
        # centrados; el video toma la proporción de la cámara con el mayor tamaño
        # posible, sin franjas negras ni deformación (ver _relayout)
        self._video_cell = tk.Frame(self, bg=BG_PANEL)
        self._video_cell.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        ctrl = tk.Frame(self._video_cell, bg=BG_PANEL)
        self._ctrl = ctrl

        tk.Label(ctrl, text=f"Cámara {self._number}:", font=("Segoe UI", 10, "bold"),
                 bg=BG_PANEL, fg=FG_GREEN).pack(side=tk.LEFT, padx=(0, 5))

        self._cam_var = tk.StringVar()
        self._cam_combo = ttk.Combobox(ctrl, textvariable=self._cam_var,
                                       state="readonly", width=22,
                                       font=("Segoe UI", 10))
        self._cam_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        self._btn_pause = tk.Button(ctrl, text="⏸ Pausa",
                                    command=self._toggle_pause,
                                    font=("Segoe UI", 10),
                                    bg=BG_ITEM, fg=FG_WHITE, width=10,
                                    cursor="hand2", relief=tk.FLAT,
                                    state=tk.DISABLED)
        self._btn_pause.pack(side=tk.RIGHT, padx=(5, 0))

        self._btn_full = tk.Button(ctrl, text="⛶", command=self._toggle_fullscreen,
                                   font=("Segoe UI", 11), bg=BG_ITEM, fg=FG_WHITE, width=3,
                                   cursor="hand2", relief=tk.FLAT, state=tk.DISABLED)
        self._btn_full.pack(side=tk.RIGHT, padx=(5, 0))

        self._btn_start = tk.Button(ctrl, text="▶ Iniciar",
                                    command=self._toggle_engine,
                                    font=("Segoe UI", 10, "bold"),
                                    bg=FG_GREEN, fg="black", width=10,
                                    cursor="hand2", relief=tk.FLAT)
        self._btn_start.pack(side=tk.RIGHT, padx=5)

        self._aspect = 16 / 9
        self._video_size = (640, 360)
        self._video_label = tk.Label(self._video_cell, bg="black", text=NO_SIGNAL,
                                     font=("Segoe UI", 12), fg=FG_GRAY, bd=0)
        self._video_cell.bind("<Configure>", lambda e: self._relayout())
        self._video_label.bind("<Double-Button-1>", lambda e: self._toggle_fullscreen())
        # nombre de la cámara en la esquina (como el OSD de un grabador): se dibuja
        # sobre la imagen, porque un widget encima lo tapa cada actualización
        self._osd_text = ""
        self._fs: Optional[tk.Toplevel] = None
        self._fs_label: Optional[tk.Label] = None

        self._stats_line = tk.Label(self._video_cell, text="", font=("Segoe UI", 9),
                                    bg=BG_PANEL, fg=FG_GRAY, anchor=tk.W)

    # ── camera list ───────────────────────────────────────────────────────

    def set_camera_list(self, cams: list):
        # id de la cámara seleccionada actualmente (para preservar selección tras recargar)
        prev_id = None
        prev_idx = self._cam_combo.current()
        if self._cams_list and 0 <= prev_idx < len(self._cams_list):
            prev_id = self._cams_list[prev_idx].id

        names = [f"{c.name} ({c.zona})" for c in cams]
        self._cam_combo["values"] = names
        self._cams_list = cams

        # prioridad de selección: cámara en ejecución > selección previa > por número de panel
        target_id = self.running_cam_id or prev_id
        target_idx = next((i for i, c in enumerate(cams) if c.id == target_id), None)
        if target_idx is not None:
            self._cam_combo.current(target_idx)
        elif names:
            self._cam_combo.current(min(self._number - 1, len(names) - 1))
        else:
            self._cam_combo.set("")

    def apply_camera_changes(self, cam_mgr: CameraManager):
        """Si la cámara en ejecución fue editada, eliminada o desactivada,
        aplica el cambio en caliente."""
        if not self._running:
            return
        cam = cam_mgr.get_by_id(self.running_cam_id)
        if cam is None or not cam.enabled:
            self._log("⚠ La cámara en monitoreo fue eliminada o desactivada — deteniendo",
                      FG_WARN)
            self.stop_engine()
            return

        self._running_cam_name = cam.name  # un cambio de nombre no requiere reiniciar
        self._set_osd(f"{self._number} · {cam.name}")
        if (cam.source, cam.source_hi) != self._running_cam_source:
            self._log("🔄 Configuración actualizada — reiniciando feed", FG_WARN)
            self._engine.stop()
            self._engine.start(cam)
            self._running_cam_source = (cam.source, cam.source_hi)

    # ── engine control ────────────────────────────────────────────────────

    def _toggle_engine(self):
        if self._running:
            self.stop_engine()
        else:
            self._start_engine()

    def _start_engine(self):
        idx = self._cam_combo.current()
        if idx < 0 or not self._cams_list:
            self._log("⚠ Seleccione una cámara primero", FG_WARN)
            return

        cam = self._cams_list[idx]
        # una cámara (sobre todo USB) no puede abrirse dos veces a la vez
        if self._view.is_camera_in_use(cam.id, exclude=self):
            self._log(f"⚠ '{cam.name}' ya se está monitoreando en el otro panel", FG_WARN)
            return

        self._engine.start(cam)
        self._running = True
        self.running_cam_id = cam.id
        self._running_cam_source = (cam.source, cam.source_hi)
        self._running_cam_name = cam.name
        self._cam_combo.config(state=tk.DISABLED)
        self._btn_start.config(text="⏹ Detener", bg=FG_RED, fg=FG_WHITE)
        self._btn_pause.config(state=tk.NORMAL)
        self._btn_full.config(state=tk.NORMAL)
        self._set_osd(f"{self._number} · {cam.name}")
        self._log("▶ Iniciado", FG_GREEN)
        self._poll_frames()

    def stop_engine(self):
        if not self._running:
            return
        self._exit_fullscreen()
        self._engine.stop()
        self._running = False
        self._log("⏹ Detenido", FG_WARN)
        self.running_cam_id = ""
        self._running_cam_source = None
        self._running_cam_name = ""
        self._cam_combo.config(state="readonly")
        self._btn_start.config(text="▶ Iniciar", bg=FG_GREEN, fg="black")
        self._btn_pause.config(state=tk.DISABLED, text="⏸ Pausa")
        self._btn_full.config(state=tk.DISABLED)
        self._set_osd("")
        self._stats_line.config(text="", fg=FG_GRAY)
        self._video_label.config(image="", text=NO_SIGNAL, font=("Segoe UI", 12))
        self._video_label.image = None

    # ── distribución del video ────────────────────────────────────────────

    @staticmethod
    def _fit(w: int, h: int, aspect: float) -> tuple:
        """Mayor rectángulo con la proporción `aspect` que cabe en w x h."""
        if w / max(h, 1) > aspect:
            return max(1, int(h * aspect)), max(1, h)
        return max(1, w), max(1, int(w / aspect))

    def _relayout(self):
        cw, ch = self._video_cell.winfo_width(), self._video_cell.winfo_height()
        if cw < 10 or ch < 10:
            return
        bar_h = self._ctrl.winfo_reqheight()
        stats_h = self._stats_line.winfo_reqheight()
        gap = 4
        tw, th = self._fit(cw, max(10, ch - bar_h - stats_h - 2 * gap), self._aspect)
        self._video_size = (tw, th)
        x = (cw - tw) // 2
        y = max(0, (ch - (bar_h + th + stats_h + 2 * gap)) // 2)
        self._ctrl.place(x=x, y=y, width=tw)
        self._video_label.place(x=x, y=y + bar_h + gap, width=tw, height=th)
        self._stats_line.place(x=x, y=y + bar_h + gap + th + gap, width=tw)

    def _set_osd(self, text: str):
        self._osd_text = text

    _fonts: dict = {}

    @classmethod
    def _font(cls, size: int):
        if size not in cls._fonts:
            try:
                cls._fonts[size] = ImageFont.truetype("segoeuib.ttf", size)
            except OSError:
                cls._fonts[size] = ImageFont.load_default()
        return cls._fonts[size]

    def _draw_osd(self, img: Image.Image) -> Image.Image:
        if not self._osd_text:
            return img
        size = max(11, img.height // 28)
        font = self._font(size)
        draw = ImageDraw.Draw(img)
        x0, y0, x1, y1 = draw.textbbox((0, 0), self._osd_text, font=font)
        pad = max(3, size // 4)
        draw.rectangle((6, 6, 6 + x1 - x0 + 2 * pad, 6 + y1 - y0 + 2 * pad), fill=(0, 0, 0))
        draw.text((6 + pad - x0, 6 + pad - y0), self._osd_text, font=font, fill=(255, 255, 255))
        return img

    # ── pantalla completa ─────────────────────────────────────────────────

    def _toggle_fullscreen(self):
        if self._fs is not None:
            self._exit_fullscreen()
        elif self._running:
            self._enter_fullscreen()

    def _enter_fullscreen(self):
        fs = tk.Toplevel(self)
        fs.configure(bg="black")
        fs.attributes("-fullscreen", True)
        fs.title(f"Cámara {self._number} · {self._running_cam_name}")
        self._fs_label = tk.Label(fs, bg="black", bd=0)
        self._fs_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        hint = tk.Label(fs, text="Esc o doble clic para salir", font=("Segoe UI", 10),
                        bg="black", fg=FG_GRAY)
        hint.place(relx=0.5, rely=1.0, anchor=tk.S, y=-12)
        fs.after(3000, hint.destroy)
        for w in (fs, self._fs_label):
            w.bind("<Escape>", lambda e: self._exit_fullscreen())
            w.bind("<Double-Button-1>", lambda e: self._exit_fullscreen())
        fs.protocol("WM_DELETE_WINDOW", self._exit_fullscreen)
        fs.focus_force()
        self._fs = fs

    def _exit_fullscreen(self):
        if self._fs is None:
            return
        self._fs.destroy()
        self._fs = self._fs_label = None

    def _toggle_pause(self):
        self._engine.toggle_pause()
        if self._engine.is_paused:
            self._btn_pause.config(text="▶ Reanudar")
        else:
            self._btn_pause.config(text="⏸ Pausa")

    # ── frame polling ─────────────────────────────────────────────────────

    def _poll_frames(self):
        if not self._running:
            return
        try:
            frame_bgr = self._frame_queue.get_nowait()
            self._display_frame(frame_bgr)
        except queue.Empty:
            pass
        self.after(20, self._poll_frames)

    def _display_frame(self, frame_bgr: np.ndarray):
        h, w = frame_bgr.shape[:2]
        aspect = w / h
        if abs(aspect - self._aspect) > 0.01:   # cámara con otra proporción (p. ej. 4:3)
            self._aspect = aspect
            self._relayout()

        if self._fs is not None:
            # pantalla completa: el video ocupa todo lo que permite su proporción
            target = self._fit(self._fs.winfo_width(), self._fs.winfo_height(), aspect)
            label = self._fs_label
            label.place_configure(width=target[0], height=target[1])
        else:
            target, label = self._video_size, self._video_label

        # el label tiene la misma proporción que el frame: lo llena entero
        interp = cv2.INTER_AREA if target[0] < w else cv2.INTER_LINEAR
        rgb = cv2.cvtColor(cv2.resize(frame_bgr, target, interpolation=interp), cv2.COLOR_BGR2RGB)
        img = ImageTk.PhotoImage(self._draw_osd(Image.fromarray(rgb)))
        label.config(image=img, text="")
        label.image = img

    # ── callbacks desde engine (hilo separado) ────────────────────────────

    def _on_frame(self, frame: np.ndarray):
        try:
            self._frame_queue.put_nowait(frame)
        except queue.Full:
            pass

    def _on_face_event(self, event: dict):
        ts = event.get("timestamp", "")[-8:]
        if event["type"] == "registered":
            msg = f"[{ts}] RESIDENTE: {event['name']} ({event['unidad']})"
            color = FG_GREEN
        elif event["type"] == "visit":
            msg = f"[{ts}] VISITA: {event['name']} → {event['unidad']}"
            color = "#ffd000"
        else:
            msg = f"[{ts}] Persona no reconocida"
            color = FG_WARN
        self.after(0, lambda: self._log(msg, color))

    def _on_vehicle_event(self, event: dict):
        ts = event.get("timestamp", "")[-8:]
        color = {"residente": FG_GREEN, "visita": "#ffd000"}.get(event["status"], FG_RED)
        msg = f"[{ts}] PATENTE {event['label']}"
        self.after(0, lambda: self._log(msg, color))

    def _on_stats(self, stats: dict):
        def _update():
            if not self._running:
                return
            # los datos técnicos que antes se dibujaban sobre el video, en una línea
            partes = [
                f"FPS {stats.get('fps', 0):.0f}",
                f"detección {stats.get('latency_detect_ms', 0):.0f} ms "
                f"(p95 {stats.get('latency_detect_p95', 0):.0f})",
                f"residentes {stats.get('faces_registered', 0)} · "
                f"visitas {stats.get('faces_visit', 0)} · "
                f"no rec. {stats.get('faces_unknown', 0)}",
                f"patentes {stats.get('plates_registered', 0)} res. · "
                f"{stats.get('plates_visit', 0)} vis. · {stats.get('plates_unregistered', 0)} no reg.",
            ]
            alerta = []
            if stats.get("gpu") is False:
                alerta.append("SIN GPU")
            if stats.get("hires_ok") is False:
                alerta.append("canal alta res. sin señal")
            if not stats.get("db_connected", True):
                alerta.append("BD desconectada")
            self._stats_line.config(text="   |   ".join(alerta + partes),
                                    fg=FG_WARN if alerta else FG_GRAY)
            self._view.set_db_status(stats.get("db_connected", False))
        self.after(0, _update)

    def _log(self, msg: str, color: str = FG_WHITE):
        cam = f" · {self._running_cam_name}" if self._running_cam_name else ""
        self._view.log_event(f"[C{self._number}{cam}] {msg}", color)


class MonitorView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self._app = app
        self._cam_mgr = CameraManager()
        self._slots: list[CameraSlot] = []

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # cabecera de vista
        top = tk.Frame(self, bg=BG_PANEL, height=50)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🎥  Monitor en Tiempo Real",
                 font=("Segoe UI", 14, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            side=tk.LEFT, padx=20, pady=10)

        self._db_label = tk.Label(top, text="BD: —", font=("Segoe UI", 10, "bold"),
                                  bg=BG_PANEL, fg=FG_GRAY)
        self._db_label.pack(side=tk.RIGHT, padx=20)

        # cuerpo principal
        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # panel lateral: registro de eventos de ambas cámaras
        side_col = tk.Frame(body, bg=BG_PANEL, width=280)
        side_col.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        side_col.pack_propagate(False)

        # paneles de video, uno junto al otro con el mismo ancho
        video_area = tk.Frame(body, bg=BG_DARK)
        video_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        video_area.rowconfigure(0, weight=1)
        for i in range(NUM_SLOTS):
            video_area.columnconfigure(i, weight=1, uniform="slot")
            slot = CameraSlot(video_area, self, i + 1)
            slot.grid(row=0, column=i, sticky="nsew",
                      padx=(0 if i == 0 else 5, 0 if i == NUM_SLOTS - 1 else 5))
            self._slots.append(slot)

        tk.Label(side_col, text="Eventos recientes",
                 font=("Segoe UI", 11, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            pady=(15, 5), anchor=tk.W, padx=15)

        log_frame = tk.Frame(side_col, bg=BG_ITEM)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        vsb = tk.Scrollbar(log_frame, orient=tk.VERTICAL)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb = tk.Scrollbar(log_frame, orient=tk.HORIZONTAL)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._log_list = tk.Listbox(
            log_frame, font=("Consolas", 9), bg=BG_ITEM, fg=FG_WHITE,
            selectbackground=BG_PANEL, relief=tk.FLAT,
            yscrollcommand=vsb.set, xscrollcommand=hsb.set, activestyle="none",
        )
        self._log_list.pack(fill=tk.BOTH, expand=True)
        vsb.config(command=self._log_list.yview)
        hsb.config(command=self._log_list.xview)

        self._refresh_camera_list()

    # ── camera list ───────────────────────────────────────────────────────

    def _refresh_camera_list(self):
        self._cam_mgr.load()  # recarga las cámaras desde la BD (altas/bajas/ediciones)
        cams = self._cam_mgr.get_enabled()
        for slot in self._slots:
            slot.set_camera_list(cams)

    def refresh_cameras(self):
        """Llamado desde CamerasView cuando se agrega/edita/elimina una cámara.
        Aplica el cambio en caliente sin reiniciar el programa."""
        self._refresh_camera_list()
        for slot in self._slots:
            slot.apply_camera_changes(self._cam_mgr)

    def is_camera_in_use(self, cam_id: str, exclude: CameraSlot) -> bool:
        return any(s is not exclude and s.running_cam_id == cam_id for s in self._slots)

    def usb_en_uso(self, index: int):
        """Número del panel que está usando la webcam `index`, o None. Una webcam no
        puede abrirse dos veces (p. ej. el Monitor y la captura de rostro a la vez)."""
        for s in self._slots:
            src = s._running_cam_source[0] if s._running_cam_source else None
            if isinstance(src, int) and src == index:
                return s._number
        return None

    # ── engine control ────────────────────────────────────────────────────

    def stop_engine(self):
        """Detiene todas las cámaras (cierre de sesión / salida)."""
        for slot in self._slots:
            slot.stop_engine()

    # ── estado compartido ─────────────────────────────────────────────────

    def set_db_status(self, connected: bool):
        self._db_label.config(
            text="BD: CONECTADA" if connected else "BD: DESCONECTADA",
            fg=FG_GREEN if connected else FG_RED,
        )
        self._app.set_db_status(connected)

    def log_event(self, msg: str, color: str = FG_WHITE):
        ts = datetime.now().strftime("%H:%M:%S")
        full = f"{ts}  {msg}"
        self._log_list.insert(tk.END, full)
        self._log_list.itemconfig(tk.END, fg=color)
        self._log_list.see(tk.END)
        # conservar últimas 200 entradas
        if self._log_list.size() > 200:
            self._log_list.delete(0)

    # ── lifecycle ─────────────────────────────────────────────────────────

    def on_show(self):
        self._refresh_camera_list()
