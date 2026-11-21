# -*- coding: utf-8 -*-
"""Herramientas usadas para obtener evidencia de pruebas."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools"))

import auditar_red  # noqa: E402
import medir_reconocimiento as medir  # noqa: E402


class Conexion:
    host, port = "nube.ejemplo", 443


def test_auditoria_guarda_campos_pero_nunca_valores(tmp_path):
    salida = tmp_path / "auditoria.json"
    a = auditar_red.Auditor(str(salida))
    cuerpo = json.dumps({"rut": "VALOR-SECRETO", "datos": {"embedding": [1, 2]}}).encode()
    a("http.client.send", (Conexion(), b"POST /api/x?t=1 HTTP/1.1\r\nAuthorization: CLAVE\r\n\r\n" + cuerpo))
    a("socket.connect", (None, ("192.168.1.10", 554)))
    datos = a.guardar()
    texto = salida.read_text(encoding="utf-8")
    assert "VALOR-SECRETO" not in texto and "CLAVE" not in texto
    assert datos["peticiones_http"]["POST nube.ejemplo:443/api/x"]["campos"] == ["datos", "embedding", "rut"]
    assert len(datos["campos_sensibles"]) == 2
    assert any(k.startswith("red local | 192.168.1.10:554") for k in datos["conexiones"])


def test_clasificacion_de_intentos_de_reconocimiento():
    assert medir.clasificar({"status": "match", "idresidente": 1}, 1) == ("correcto", 1)
    assert medir.clasificar({"status": "match", "idresidente": 2}, 1) == ("otra_persona", 0)
    assert medir.clasificar({"status": "no_match"}, 1) == ("no_reconocido", 0)
    assert medir.clasificar({"status": "no_match"}, None) == ("rechazado_correctamente", 1)
    assert medir.clasificar({"status": "match", "idresidente": 1}, None) == ("aceptado_por_error", 0)
