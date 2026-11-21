# -*- coding: utf-8 -*-
"""
gui/view_reports.py - Generación y exportación de reportes
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
import os

from database import DatabaseManager
from reports.report_generator import ReportGenerator

BG_DARK  = "#1e1e2e"
BG_PANEL = "#2d2d44"
BG_ITEM  = "#3d3d5c"
FG_GREEN = "#00ff88"
FG_WHITE = "#ffffff"
FG_GRAY  = "#aaaaaa"
FG_WARN  = "#ffaa00"
FG_RED   = "#ff4444"
FG_BLUE  = "#4488ff"


class ReportsView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self._app = app
        self.db: DatabaseManager = None
        self._build_ui()

    def _connect_db(self) -> bool:
        if self.db and self.db.is_connected():
            return True
        self.db = DatabaseManager()
        return self.db.connect()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        top = tk.Frame(self, bg=BG_PANEL, height=50)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="📊  Reportes y Exportación",
                 font=("Segoe UI", 14, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            side=tk.LEFT, padx=20, pady=10)

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # ── panel de filtros ──────────────────────────────────────────────
        filter_frame = tk.Frame(body, bg=BG_PANEL)
        filter_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Label(filter_frame, text="Período:",
                 font=("Segoe UI", 10), bg=BG_PANEL, fg=FG_WHITE).pack(
            side=tk.LEFT, padx=15, pady=10)

        self.period_var = tk.StringVar(value="hoy")
        for val, text in [("hoy", "Hoy"), ("semana", "Esta semana"),
                          ("mes", "Este mes"), ("custom", "Personalizado")]:
            tk.Radiobutton(filter_frame, text=text, variable=self.period_var,
                           value=val, command=self._update_period,
                           bg=BG_PANEL, fg=FG_WHITE, selectcolor=BG_ITEM,
                           activebackground=BG_PANEL,
                           font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=8)

        self.date_from_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.date_to_var   = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))

        self.date_frame = tk.Frame(filter_frame, bg=BG_PANEL)
        self.date_frame.pack(side=tk.LEFT, padx=15)
        tk.Label(self.date_frame, text="Desde:", font=("Segoe UI", 9),
                 bg=BG_PANEL, fg=FG_GRAY).pack(side=tk.LEFT)
        tk.Entry(self.date_frame, textvariable=self.date_from_var,
                 font=("Segoe UI", 10), width=12, bg=BG_ITEM, fg=FG_WHITE,
                 insertbackground=FG_WHITE).pack(side=tk.LEFT, padx=4)
        tk.Label(self.date_frame, text="Hasta:", font=("Segoe UI", 9),
                 bg=BG_PANEL, fg=FG_GRAY).pack(side=tk.LEFT, padx=(10, 0))
        tk.Entry(self.date_frame, textvariable=self.date_to_var,
                 font=("Segoe UI", 10), width=12, bg=BG_ITEM, fg=FG_WHITE,
                 insertbackground=FG_WHITE).pack(side=tk.LEFT, padx=4)

        # ── botones de tipo de reporte ────────────────────────────────────
        btn_frame = tk.Frame(body, bg=BG_DARK)
        btn_frame.pack(fill=tk.X, pady=(0, 20))

        report_types = [
            ("Accesos peatonales", "faces",    FG_GREEN),
            ("Accesos vehiculares", "vehicles", FG_BLUE),
            ("Tráfico por zona y horario", "traffic", FG_RED),
            ("Resumen general", "summary", FG_WARN),
            ("Residentes", "residents", "#cc88ff"),
        ]
        for label, rtype, color in report_types:
            card = tk.Frame(btn_frame, bg=BG_PANEL, relief=tk.RAISED, bd=2,
                            width=180, height=110)
            card.pack(side=tk.LEFT, padx=8, pady=5)
            card.pack_propagate(False)
            tk.Label(card, text=label, font=("Segoe UI", 11, "bold"),
                     bg=BG_PANEL, fg=color, wraplength=160, justify=tk.CENTER).pack(pady=12)
            rf = tk.Frame(card, bg=BG_PANEL)
            rf.pack(pady=(0, 10))
            tk.Button(rf, text="CSV", command=lambda r=rtype: self._export(r, "csv"),
                      font=("Segoe UI", 10, "bold"), bg=color,
                      fg="black" if color in (FG_GREEN, FG_WARN) else FG_WHITE,
                      width=7, cursor="hand2", relief=tk.FLAT).pack(side=tk.LEFT, padx=3)
            tk.Button(rf, text="PDF", command=lambda r=rtype: self._export(r, "pdf"),
                      font=("Segoe UI", 10, "bold"), bg=BG_ITEM, fg=FG_WHITE,
                      width=7, cursor="hand2", relief=tk.FLAT).pack(side=tk.LEFT, padx=3)

        # ── vista previa de estadísticas ──────────────────────────────────
        preview = tk.Frame(body, bg=BG_PANEL)
        preview.pack(fill=tk.BOTH, expand=True)
        tk.Label(preview, text="Estadísticas del período seleccionado",
                 font=("Segoe UI", 12, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            pady=12, anchor=tk.W, padx=15)

        self._stats_frame = tk.Frame(preview, bg=BG_PANEL)
        self._stats_frame.pack(fill=tk.BOTH, expand=True, padx=15)
        self._stat_labels: dict[str, tk.Label] = {}
        for key, text in [
            ("rostros_hoy", "Accesos peatonales hoy:"),
            ("vehiculos_hoy", "Accesos vehiculares hoy:"),
            ("residentes", "Residentes registrados:"),
            ("con_rostro", "Residentes con rostro enrolado:"),
            ("vehiculos", "Vehículos autorizados:"),
            ("visitas_activas", "Visitas dentro del condominio:"),
            ("solicitudes_pendientes", "Solicitudes de derechos pendientes:"),
        ]:
            row = tk.Frame(self._stats_frame, bg=BG_PANEL)
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=text, font=("Segoe UI", 11),
                     bg=BG_PANEL, fg=FG_WHITE, width=30, anchor=tk.W).pack(side=tk.LEFT)
            lbl = tk.Label(row, text="—", font=("Segoe UI", 11, "bold"),
                           bg=BG_PANEL, fg=FG_GREEN)
            lbl.pack(side=tk.LEFT, padx=10)
            self._stat_labels[key] = lbl

    # ── lógica ────────────────────────────────────────────────────────────

    def _update_period(self):
        p = self.period_var.get()
        today = datetime.now().date()
        if p == "hoy":
            self.date_from_var.set(str(today))
            self.date_to_var.set(str(today))
        elif p == "semana":
            self.date_from_var.set(str(today - timedelta(days=today.weekday())))
            self.date_to_var.set(str(today))
        elif p == "mes":
            self.date_from_var.set(str(today.replace(day=1)))
            self.date_to_var.set(str(today))

    def _load_stats(self):
        if not self._connect_db():
            return
        try:
            stats = self.db.get_statistics()
            for key, lbl in self._stat_labels.items():
                lbl.config(text=str(stats.get(key, 0)))
        except Exception as e:
            print(f"[ReportsView] Stats error: {e}")

    def _export(self, report_type: str, fmt: str):
        if not self._connect_db():
            messagebox.showerror("Error", "Sin conexión a BD")
            return

        date_from = self.date_from_var.get().strip()
        date_to   = self.date_to_var.get().strip()

        ext = ".csv" if fmt == "csv" else ".pdf"
        default_name = f"reporte_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports_output")
        os.makedirs(out_dir, exist_ok=True)

        save_path = filedialog.asksaveasfilename(
            title="Guardar reporte",
            initialdir=out_dir,
            initialfile=default_name,
            defaultextension=ext,
            filetypes=[(fmt.upper(), f"*{ext}")],
        )
        if not save_path:
            return
        # elegir un archivo de otro tipo no debe dejar un PDF con nombre .csv
        if not save_path.lower().endswith(ext):
            save_path = os.path.splitext(save_path)[0] + ext

        gen = ReportGenerator(self.db)
        try:
            if fmt == "csv":
                gen.export_csv(report_type, save_path, date_from, date_to)
            else:
                gen.export_pdf(report_type, save_path, date_from, date_to)
            messagebox.showinfo("Éxito", f"Reporte guardado en:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el reporte:\n{e}")

    # ── lifecycle ─────────────────────────────────────────────────────────

    def on_show(self):
        self._update_period()
        self._load_stats()
