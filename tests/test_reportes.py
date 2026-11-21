# -*- coding: utf-8 -*-
"""Exportación de reportes."""

import csv
from datetime import datetime

from reports.report_generator import ReportGenerator


def test_csv_usa_punto_y_coma_para_excel_en_espanol(tmp_path, monkeypatch):
    gen = ReportGenerator(None)
    monkeypatch.setattr(gen, "_get_data", lambda *a: ([["Portón", "14:00", 9, 0]],
                                                      ["Zona", "Hora", "Personas", "Vehículos"]))
    ruta = tmp_path / "reporte.csv"
    gen.export_csv("traffic", str(ruta), "2026-11-18", "2026-11-18")
    assert ruta.read_bytes().startswith(b"\xef\xbb\xbf")     # Excel reconoce los acentos
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.reader(f, delimiter=";"))
    assert filas == [["Zona", "Hora", "Personas", "Vehículos"], ["Portón", "14:00", "9", "0"]]


def test_historial_no_reordena_lo_nuevo_si_el_reloj_retrocedio():
    from gui.view_history import mezclar_detecciones
    fila = lambda hora, tipo: ({"fecha_hora": datetime(2026, 11, 12, hora)}, tipo, "")
    personas = [fila(15, "nueva"), fila(17, "antigua con hora adelantada")]
    vehiculos = [fila(14, "vehiculo")]
    assert [f[1] for f in mezclar_detecciones(personas, vehiculos)][0] == "nueva"
