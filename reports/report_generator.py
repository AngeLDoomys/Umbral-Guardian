# -*- coding: utf-8 -*-
"""
reports/report_generator.py - Exportación de reportes PDF y CSV
"""

import csv
import os
from datetime import datetime
from typing import TYPE_CHECKING

from core import session
from core.security import mask_rut

if TYPE_CHECKING:
    from database import DatabaseManager

RESULTADOS = {"reconocido": "Residente", "no_reconocido": "No reconocido",
              "residente": "Residente", "visita": "Visita", "no_registrado": "No registrado"}


class ReportGenerator:

    def __init__(self, db: "DatabaseManager"):
        self.db = db

    # ─────────────────────────────────────────────────────────────────────
    # CSV
    # ─────────────────────────────────────────────────────────────────────

    def export_csv(self, report_type: str, path: str, date_from: str, date_to: str):
        data, headers = self._get_data(report_type, date_from, date_to)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            # Excel en español (Chile) separa columnas con punto y coma: con comas
            # dejaba todo el reporte en una sola columna
            writer = csv.writer(f, delimiter=";")
            writer.writerow(headers)
            writer.writerows(data)

    # ─────────────────────────────────────────────────────────────────────
    # PDF
    # ─────────────────────────────────────────────────────────────────────

    def export_pdf(self, report_type: str, path: str, date_from: str, date_to: str):
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib import colors
            from reportlab.platypus import (
                SimpleDocTemplate, Table, TableStyle,
                Paragraph, Spacer, HRFlowable
            )
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        except ImportError:
            raise ImportError("reportlab no instalado. Ejecute: pip install reportlab")

        title_map = {
            "faces":     "Reporte de Accesos Peatonales",
            "vehicles":  "Reporte de Accesos Vehiculares",
            "traffic":   "Reporte de Tráfico por Zona y Horario",
            "summary":   "Reporte Resumen General",
            "residents": "Reporte de Residentes",
        }
        title = title_map.get(report_type, "Reporte")

        COLOR_DARK   = colors.HexColor("#1e1e2e")
        COLOR_PANEL  = colors.HexColor("#2d2d44")
        COLOR_GREEN  = colors.HexColor("#00cc66")
        COLOR_RED    = colors.HexColor("#cc3333")
        COLOR_BLUE   = colors.HexColor("#3366cc")
        COLOR_WARN   = colors.HexColor("#cc8800")
        COLOR_PURPLE = colors.HexColor("#8844cc")
        COLOR_ROW1   = colors.HexColor("#f0f4f0")
        COLOR_ROW2   = colors.white
        COLOR_HEAD   = colors.HexColor("#2d2d44")

        accent = {
            "faces":     COLOR_GREEN,
            "vehicles":  COLOR_BLUE,
            "traffic":   COLOR_RED,
            "summary":   COLOR_WARN,
            "residents": COLOR_PURPLE,
        }.get(report_type, COLOR_GREEN)

        page_size = landscape(A4)
        doc = SimpleDocTemplate(
            path, pagesize=page_size,
            rightMargin=1.5*cm, leftMargin=1.5*cm,
            topMargin=1.5*cm, bottomMargin=2*cm,
        )

        styles = getSampleStyleSheet()
        style_title = ParagraphStyle(
            "UGTitle", fontSize=18, fontName="Helvetica-Bold",
            textColor=colors.white, leading=22, spaceAfter=2, alignment=TA_LEFT,
        )
        style_subtitle = ParagraphStyle(
            "UGSub", fontSize=10, fontName="Helvetica",
            textColor=colors.HexColor("#555555"), spaceAfter=4,
        )
        style_section = ParagraphStyle(
            "UGSection", fontSize=11, fontName="Helvetica-Bold",
            textColor=accent, spaceBefore=10, spaceAfter=6,
        )
        style_footer = ParagraphStyle(
            "UGFooter", fontSize=8, fontName="Helvetica",
            textColor=colors.HexColor("#888888"), alignment=TA_CENTER,
        )

        story = []

        # ── Encabezado ────────────────────────────────────────────────────
        header_data = [[
            Paragraph(f"<b>Umbral Guardian</b><br/><font size='9' color='#aaaaaa'>"
                      f"{session.current.condominio}</font>", style_title),
            Paragraph(
                f"<b>{title}</b><br/>"
                f"<font size='9' color='#cccccc'>"
                f"Período: {date_from} → {date_to} &nbsp;&nbsp; "
                f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}</font>",
                ParagraphStyle("h2", fontSize=13, fontName="Helvetica-Bold", leading=18,
                               textColor=accent, alignment=TA_RIGHT),
            ),
        ]]
        header_table = Table(header_data, colWidths=[page_size[0]*0.4 - 1.5*cm,
                                                      page_size[0]*0.6 - 1.5*cm])
        header_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_DARK),
            ("TOPPADDING",    (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("LEFTPADDING",   (0, 0), (0, -1), 16),
            ("RIGHTPADDING",  (-1, 0), (-1, -1), 16),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 0.4*cm))

        # ── Caja de resumen ───────────────────────────────────────────────
        summary_rows = self._build_summary_box(report_type, date_from, date_to)
        if summary_rows:
            story.append(Paragraph("Resumen del período", style_section))
            sw = (page_size[0] - 3*cm) / len(summary_rows[0])
            sum_table = Table(summary_rows, colWidths=[sw]*len(summary_rows[0]))
            sum_table.setStyle(TableStyle([
                ("BACKGROUND",  (0, 0), (-1, 0), accent),
                ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
                ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",    (0, 0), (-1, 0), 9),
                ("BACKGROUND",  (0, 1), (-1, -1), COLOR_PANEL),
                ("TEXTCOLOR",   (0, 1), (-1, -1), colors.white),
                ("FONTNAME",    (0, 1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE",    (0, 1), (-1, -1), 14),
                ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
                ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING",  (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
                ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#444466")),
                ("ROUNDEDCORNERS", [4, 4, 4, 4]),
            ]))
            story.append(sum_table)
            story.append(Spacer(1, 0.4*cm))

        # ── Tabla de datos ────────────────────────────────────────────────
        data, headers, col_widths, row_tags = self._get_data_with_tags(
            report_type, date_from, date_to, page_size[0] - 3*cm
        )

        story.append(Paragraph("Detalle", style_section))
        story.append(HRFlowable(width="100%", thickness=1, color=accent,
                                spaceAfter=4))

        if not data:
            story.append(Paragraph(
                "⚠  Sin datos para el período seleccionado.",
                ParagraphStyle("warn", fontSize=11, textColor=COLOR_WARN,
                               fontName="Helvetica-Bold")
            ))
        else:
            table_data = [headers] + [[str(c) for c in row] for row in data]
            main_table = Table(table_data, colWidths=col_widths, repeatRows=1)

            ts = [
                ("BACKGROUND",    (0, 0), (-1, 0), COLOR_HEAD),
                ("TEXTCOLOR",     (0, 0), (-1, 0), accent),
                ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",      (0, 0), (-1, 0), 9),
                ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
                ("TOPPADDING",    (0, 0), (-1, 0), 7),
                ("FONTSIZE",      (0, 1), (-1, -1), 8),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING",    (0, 1), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
                ("LINEBELOW",     (0, 0), (-1, 0), 1.5, accent),
            ]

            for i, (row, tag) in enumerate(zip(data, row_tags), start=1):
                bg = COLOR_ROW1 if i % 2 == 0 else COLOR_ROW2
                ts.append(("BACKGROUND", (0, i), (-1, i), bg))
                if tag in ("reconocido", "residente"):
                    ts.append(("TEXTCOLOR", (0, i), (-1, i), COLOR_GREEN))
                elif tag in ("no_reconocido", "no_registrado"):
                    ts.append(("TEXTCOLOR", (0, i), (-1, i), COLOR_RED))

            main_table.setStyle(TableStyle(ts))
            story.append(main_table)

        # ── Pie de página (total) ─────────────────────────────────────────
        story.append(Spacer(1, 0.5*cm))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=colors.HexColor("#cccccc"), spaceAfter=4))
        story.append(Paragraph(
            f"Umbral Guardian — Sistema de Seguridad Inteligente &nbsp;|&nbsp; "
            f"Total de registros: {len(data)} &nbsp;|&nbsp; "
            f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            style_footer,
        ))

        doc.build(story)

    # ─────────────────────────────────────────────────────────────────────
    # Caja de resumen por tipo
    # ─────────────────────────────────────────────────────────────────────

    def _build_summary_box(self, report_type, date_from, date_to):
        if report_type == "faces":
            rows = self.db.list_detecciones_rostro(date_from, date_to, 100000)
            reg = sum(1 for r in rows if r["resultado"] == "reconocido")
            return [["Total detecciones", "Residentes", "No reconocidos"],
                    [str(len(rows)), str(reg), str(len(rows) - reg)]]
        if report_type == "vehicles":
            rows = self.db.list_detecciones_vehiculo(date_from, date_to, 100000)
            count = {k: sum(1 for r in rows if r["resultado"] == k)
                     for k in ("residente", "visita", "no_registrado")}
            return [["Total", "Residentes", "Visitas", "No registrados"],
                    [str(len(rows)), str(count["residente"]), str(count["visita"]),
                     str(count["no_registrado"])]]
        if report_type == "traffic":
            rows = self.db.trafico_por_zona_hora(date_from, date_to)
            personas = sum(int(r["personas"]) for r in rows)
            vehiculos = sum(int(r["vehiculos"]) for r in rows)
            pico = max(rows, key=lambda r: r["personas"] + r["vehiculos"], default=None)
            return [["Personas", "Vehículos", "Hora de mayor tráfico"],
                    [str(personas), str(vehiculos),
                     f"{pico['hora']:02d}:00 ({pico['zona']})" if pico else "—"]]
        if report_type in ("summary", "residents"):
            s = self.db.get_statistics()
            return [["Residentes", "Con rostro enrolado", "Vehículos", "Visitas dentro"],
                    [str(s.get("residentes", 0)), str(s.get("con_rostro", 0)),
                     str(s.get("vehiculos", 0)), str(s.get("visitas_activas", 0))]]
        return []

    # ─────────────────────────────────────────────────────────────────────
    # Datos con tags de color y anchos de columna ajustados
    # ─────────────────────────────────────────────────────────────────────

    def _get_data_with_tags(self, report_type, date_from, date_to, total_width):
        rows, headers, tags = self._rows(report_type, date_from, date_to)
        shares = {
            "faces":     [0.18, 0.30, 0.10, 0.15, 0.09, 0.18],
            "vehicles":  [0.18, 0.12, 0.12, 0.16, 0.10, 0.32],
            "traffic":   [0.40, 0.20, 0.20, 0.20],
            "summary":   [0.60, 0.40],
            "residents": [0.12, 0.28, 0.14, 0.18, 0.14, 0.14],
        }[report_type]
        return rows, headers, [total_width * s for s in shares], tags

    def _get_data(self, report_type, date_from, date_to):
        rows, headers, _ = self._rows(report_type, date_from, date_to)
        return rows, headers

    def _rows(self, report_type, date_from, date_to):
        """Retorna (filas, encabezados, tags de color) de cada tipo de reporte."""
        if report_type == "faces":
            headers = ["Fecha/Hora", "Persona", "Unidad", "Resultado", "Confianza", "Zona"]
            data = self.db.list_detecciones_rostro(date_from, date_to, 100000)
            rows = [[f"{r['fecha_hora']:%d/%m/%Y %H:%M:%S}", r["persona"] or "—",
                     r["unidad"] or "—", RESULTADOS[r["resultado"]],
                     f"{float(r['confianza']):.0%}" if r["confianza"] is not None else "—",
                     r["zona"]] for r in data]
            return rows, headers, [r["resultado"] for r in data]

        if report_type == "vehicles":
            headers = ["Fecha/Hora", "Patente", "Unidad", "Resultado", "Confianza", "Zona"]
            data = self.db.list_detecciones_vehiculo(date_from, date_to, 100000)
            rows = [[f"{r['fecha_hora']:%d/%m/%Y %H:%M:%S}", r["patente_leida"],
                     r["unidad"] or "—", RESULTADOS[r["resultado"]],
                     f"{float(r['confianza']):.0%}" if r["confianza"] is not None else "—",
                     r["zona"]] for r in data]
            return rows, headers, [r["resultado"] for r in data]

        if report_type == "traffic":
            headers = ["Zona", "Hora", "Personas", "Vehículos"]
            data = self.db.trafico_por_zona_hora(date_from, date_to)
            rows = [[r["zona"], f"{r['hora']:02d}:00 - {r['hora']:02d}:59",
                     int(r["personas"]), int(r["vehiculos"])] for r in data]
            return rows, headers, [""] * len(rows)

        if report_type == "summary":
            s = self.db.get_statistics()
            traffic = self.db.trafico_por_zona_hora(date_from, date_to)
            rows = [
                ["Residentes registrados", s.get("residentes", 0)],
                ["Residentes con rostro enrolado", s.get("con_rostro", 0)],
                ["Vehículos autorizados", s.get("vehiculos", 0)],
                ["Visitas dentro del condominio", s.get("visitas_activas", 0)],
                ["Accesos peatonales (período)", sum(int(r["personas"]) for r in traffic)],
                ["Accesos vehiculares (período)", sum(int(r["vehiculos"]) for r in traffic)],
                ["Solicitudes de derechos pendientes", s.get("solicitudes_pendientes", 0)],
                ["Período del reporte", f"{date_from} → {date_to}"],
            ]
            return rows, ["Métrica", "Valor"], [""] * len(rows)

        if report_type == "residents":
            headers = ["Unidad", "Nombre", "RUT", "Tipo", "Consentimiento", "Rostro"]
            data = self.db.list_residentes()
            rows = [[r["unidad"], f"{r['nombres']} {r['apellidos']}", mask_rut(r["rut"]),
                     r["tipo"], "Vigente" if r["consentimiento_vigente"] else "No",
                     "Sí" if r["plantillas"] else "No"] for r in data]
            return rows, headers, [""] * len(rows)

        raise ValueError(f"Tipo desconocido: {report_type}")

