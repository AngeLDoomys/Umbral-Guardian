# -*- coding: utf-8 -*-
"""
gui/view_settings.py - Configuración en tiempo de ejecución
Modifica settings.json sin tocar config.py y aplica los cambios en caliente.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import os

import config
from core import events

MODEL_KEYS = ("DETECTOR_MODEL", "PLATE_DETECTOR_MODEL")
BOOL_KEYS = {"USE_DATABASE_LOGS", "USE_CSV_LOGS", "SHOW_VIDEO_HUD", "SHOW_FACE_ZOOM",
             "VISITA_ROSTRO_OBLIGATORIO"}
FLOAT_KEYS = {"PERSON_CONFIDENCE", "VEHICLE_CONFIDENCE", "PLATE_CONFIDENCE",
              "PLATE_MIN_CHAR_CONF", "FACE_RECOGNITION_THRESHOLD", "SCALE_FACTOR"}
INT_KEYS = {"PROCESS_EVERY_N_FRAMES", "DIAS_RETENCION_DETECCIONES",
            "DIAS_RETENCION_VISITAS", "PERSON_TIMEOUT", "VEHICLE_TIMEOUT"}

BG_DARK  = "#1e1e2e"
BG_PANEL = "#2d2d44"
BG_ITEM  = "#3d3d5c"
FG_GREEN = "#00ff88"
FG_WHITE = "#ffffff"
FG_GRAY  = "#aaaaaa"
FG_WARN  = "#ffaa00"
FG_RED   = "#ff4444"


class SettingsView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self._app = app
        self._entries: dict[str, tk.Variable] = {}
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        top = tk.Frame(self, bg=BG_PANEL, height=50)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="⚙  Configuración",
                 font=("Segoe UI", 14, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            side=tk.LEFT, padx=20, pady=10)

        # ── botones ───────────────────────────────────────────────────────
        # van antes que las columnas y a todo el ancho: dentro de ellas quedaban
        # al costado y el mensaje de guardado salía fuera de la ventana
        btn_row = tk.Frame(self, bg=BG_DARK)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=15)

        tk.Button(btn_row, text="💾 Guardar en settings.json",
                  command=self._save,
                  font=("Segoe UI", 11, "bold"), bg=FG_GREEN, fg="black",
                  width=28, height=2, cursor="hand2", relief=tk.FLAT).pack(
            side=tk.LEFT, padx=5)

        tk.Button(btn_row, text="↺ Restaurar defaults",
                  command=self._restore,
                  font=("Segoe UI", 11), bg=BG_ITEM, fg=FG_WHITE,
                  width=20, height=2, cursor="hand2", relief=tk.FLAT).pack(
            side=tk.LEFT, padx=5)

        self.status_lbl = tk.Label(btn_row, text="",
                                   font=("Segoe UI", 10), bg=BG_DARK, fg=FG_GREEN)
        self.status_lbl.pack(side=tk.LEFT, padx=20)

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 0))

        # dos columnas
        col1 = tk.Frame(body, bg=BG_DARK)
        col1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 15))
        col2 = tk.Frame(body, bg=BG_DARK)
        col2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ── col 1: base de datos local ────────────────────────────────────
        self._section(col1, "Base de datos local (este equipo)")
        tk.Label(col1, text=f"Archivo: {config.DB_PATH}",
                 font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_GRAY, justify=tk.LEFT,
                 anchor=tk.W).pack(fill=tk.X, padx=15, pady=2)

        self._section(col1, "Nube")
        tk.Label(col1, text=f"API central: {config.API_URL}\n"
                            "La dirección y la clave del nodo se configuran con setup_nodo.py",
                 font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_GRAY, justify=tk.LEFT,
                 anchor=tk.W).pack(fill=tk.X, padx=15, pady=2)

        # ── col 1: detección ─────────────────────────────────────────────
        self._section(col1, "Detección y procesamiento")
        for key, label in [
            ("PERSON_CONFIDENCE",       "Confianza personas (0–1)"),
            ("VEHICLE_CONFIDENCE",      "Confianza vehículos (0–1)"),
            ("PLATE_CONFIDENCE",        "Confianza placas (0–1)"),
            ("PLATE_MIN_CHAR_CONF",     "Confianza mínima OCR por carácter (0–1)"),
            ("FACE_RECOGNITION_THRESHOLD", "Umbral reconocimiento facial"),
            ("SCALE_FACTOR",            "Factor de escala procesamiento"),
            ("PROCESS_EVERY_N_FRAMES",  "Procesar cada N frames"),
        ]:
            self._field(col1, key, label, getattr(config, key, ""))

        # ── col 2: modelos ────────────────────────────────────────────────
        self._section(col2, "Modelos (carpeta modelos/)")
        for key, label in [
            ("DETECTOR_MODEL",       "Personas y vehículos (RF-DETR)"),
            ("PLATE_DETECTOR_MODEL", "Detector de patentes"),
            ("FACE_MODEL",  "Modelo reconocimiento facial"),
        ]:
            self._field(col2, key, label, getattr(config, key, ""))

        # ── col 2: protección de datos ────────────────────────────────────
        self._section(col2, "Protección de datos (Ley 21.719)")
        for key, label in [
            ("DIAS_RETENCION_DETECCIONES", "Retención historial de accesos (días)"),
            ("DIAS_RETENCION_VISITAS",     "Retención datos de visitas (días)"),
            ("VERSION_CONSENTIMIENTO",     "Versión formulario consentimiento"),
        ]:
            self._field(col2, key, label, getattr(config, key, ""))

        # ── col 2: logs ───────────────────────────────────────────────────
        self._section(col2, "Registros")

        db_logs = tk.BooleanVar(value=config.USE_DATABASE_LOGS)
        csv_logs = tk.BooleanVar(value=config.USE_CSV_LOGS)
        self._entries["USE_DATABASE_LOGS"] = db_logs
        self._entries["USE_CSV_LOGS"] = csv_logs
        tk.Checkbutton(col2, text="Guardar detecciones en BD",
                       variable=db_logs, bg=BG_PANEL, fg=FG_WHITE,
                       selectcolor=BG_ITEM, activebackground=BG_PANEL,
                       font=("Segoe UI", 10)).pack(anchor=tk.W, padx=15, pady=3)
        tk.Checkbutton(col2, text="Guardar logs CSV",
                       variable=csv_logs, bg=BG_PANEL, fg=FG_WHITE,
                       selectcolor=BG_ITEM, activebackground=BG_PANEL,
                       font=("Segoe UI", 10)).pack(anchor=tk.W, padx=15, pady=3)

        # ── col 2: vista de cámaras ───────────────────────────────────────
        self._section(col2, "Vista de cámaras")
        for key, text in [("SHOW_VIDEO_HUD", "Datos técnicos sobre el video (FPS, latencia, BD)"),
                          ("SHOW_FACE_ZOOM", "Ampliación del último rostro en la esquina"),
                          ("VISITA_ROSTRO_OBLIGATORIO",
                           "Reglamento: las visitas registran su rostro")]:
            var = tk.BooleanVar(value=getattr(config, key))
            self._entries[key] = var
            tk.Checkbutton(col2, text=text, variable=var, bg=BG_PANEL, fg=FG_WHITE,
                           selectcolor=BG_ITEM, activebackground=BG_PANEL,
                           font=("Segoe UI", 10)).pack(anchor=tk.W, padx=15, pady=3)

    def _section(self, parent, title: str):
        f = tk.Frame(parent, bg=BG_PANEL, relief=tk.RAISED, bd=1)
        f.pack(fill=tk.X, pady=(10, 2))
        tk.Label(f, text=title, font=("Segoe UI", 10, "bold"),
                 bg=BG_PANEL, fg=FG_WARN).pack(anchor=tk.W, padx=12, pady=6)

    def _field(self, parent, key: str, label: str, default, password: bool = False):
        row = tk.Frame(parent, bg=BG_PANEL)
        row.pack(fill=tk.X, padx=15, pady=2)
        tk.Label(row, text=label, font=("Segoe UI", 9),
                 bg=BG_PANEL, fg=FG_WHITE, width=34, anchor=tk.W).pack(side=tk.LEFT)
        var = tk.StringVar(value=str(default))
        tk.Entry(row, textvariable=var, font=("Segoe UI", 10), width=22,
                 bg=BG_ITEM, fg=FG_WHITE, insertbackground=FG_WHITE,
                 show="●" if password else "").pack(side=tk.LEFT, padx=5)
        self._entries[key] = var

    # ── persistencia ──────────────────────────────────────────────────────

    def _collect(self) -> dict:
        """Valores del formulario. Lanza ValueError si un número no es válido: un
        texto en un campo numérico haría fallar a los motores en ejecución."""
        result = {}
        for key, var in self._entries.items():
            if isinstance(var, tk.BooleanVar):
                result[key] = var.get()
                continue
            raw = var.get().strip()
            if key in BOOL_KEYS:
                result[key] = raw.lower() in ("1", "true", "yes")
            elif key in INT_KEYS:
                try:
                    result[key] = int(raw)
                except ValueError:
                    raise ValueError(f"'{raw}' no es un número entero ({key})")
                if key == "PROCESS_EVERY_N_FRAMES" and result[key] < 1:
                    raise ValueError("Procesar cada N frames debe ser 1 o más")
            elif key in FLOAT_KEYS:
                try:
                    result[key] = float(raw.replace(",", "."))
                except ValueError:
                    raise ValueError(f"'{raw}' no es un número ({key})")
            else:
                result[key] = raw
        return result

    def _apply(self, before: dict) -> str:
        """Recarga config y avisa a los motores. Retorna el texto de estado."""
        config.reload()
        events.data_changed()  # p. ej. FACE_MODEL cambia qué plantillas se cargan
        if any(getattr(config, k) != before[k] for k in MODEL_KEYS):
            events.models_changed()
        return "✅ Guardado y aplicado"

    def _snapshot(self) -> dict:
        return {k: getattr(config, k) for k in MODEL_KEYS}

    def _save(self):
        try:
            overrides = self._collect()
        except ValueError as e:
            messagebox.showerror("Valor inválido", str(e))
            return
        before = self._snapshot()
        try:
            # conservar claves de settings.json que no aparecen en esta pantalla
            current = {}
            if os.path.exists(config.SETTINGS_FILE):
                with open(config.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    current = json.load(f)
            # los modelos de la carpeta del programa se guardan solo por su nombre:
            # una ruta completa dejaría de valer al mover la instalación
            for key in MODEL_KEYS:
                ruta = overrides.get(key, "")
                if os.path.normcase(os.path.dirname(os.path.abspath(ruta))) \
                        == os.path.normcase(config.MODELS_DIR):
                    overrides[key] = os.path.basename(ruta)
            current.update(overrides)
            with open(config.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2, ensure_ascii=False)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}")
            return
        self.status_lbl.config(text=self._apply(before), fg=FG_GREEN)

    def _restore(self):
        if not messagebox.askyesno("Confirmar", "¿Restaurar configuración por defecto?"):
            return
        before = self._snapshot()
        if os.path.exists(config.SETTINGS_FILE):
            os.remove(config.SETTINGS_FILE)
        status = self._apply(before).replace("Guardado", "Restaurado")
        self._load_values()
        self.status_lbl.config(text=status, fg=FG_GREEN)

    def _load_values(self):
        """Muestra en el formulario los valores vigentes de config."""
        for key, var in self._entries.items():
            val = getattr(config, key, "")
            var.set(val if isinstance(var, tk.BooleanVar) else str(val))

    def on_show(self):
        self._load_values()
        self.status_lbl.config(text="")
