# -*- coding: utf-8 -*-
"""
Registro desde el celular, de punta a punta: invitación en el nodo -> formulario y
fotos en la API -> paquete cifrado -> descarga en el nodo -> aprobación.

Base central TEMPORAL (umbral_central_pruebas_movil, se omite sin MySQL) y base
del nodo temporal (SQLite). El nodo habla con la API en el mismo proceso.
"""

import glob
import hashlib
import io
import json
import os
import re

import cv2
import numpy as np
import pytest

import config
from core import cifrado

ROOT = config.BASE_DIR
BD = "umbral_central_pruebas_movil"
CLAVE_NODO = "ugn_prueba_movil"


def test_cifrado_ida_y_vuelta_y_alteracion():
    priv, pub = cifrado.generar_par()
    p = cifrado.cifrar({"a": 1, "ñ": "José"}, pub)
    assert cifrado.descifrar(p, priv) == {"a": 1, "ñ": "José"}
    otro_priv, _ = cifrado.generar_par()
    with pytest.raises(Exception):
        cifrado.descifrar(p, otro_priv)                     # otra clave: no se lee
    roto = p[:-8] + ("A" if p[-8] != "A" else "B") + p[-7:]
    with pytest.raises(Exception):
        cifrado.descifrar(roto, priv)                       # alterado: se detecta


@pytest.fixture(scope="module")
def entorno(tmp_path_factory):
    mysql = pytest.importorskip("mysql.connector")
    from servidor import config_servidor as cfg
    try:
        srv = mysql.connect(**{k: v for k, v in cfg.CENTRAL_DB.items() if k != "database"})
    except mysql.Error as e:
        pytest.skip(f"MySQL no disponible: {e}")
    sql = open(os.path.join(ROOT, "sql", "central.sql"), encoding="utf-8").read()
    sql = re.sub(r"--[^\n]*", "", sql.replace("umbral_central", BD))
    cur = srv.cursor()
    for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
        cur.execute(stmt)
    srv.commit()

    orig_db, orig_path = cfg.CENTRAL_DB["database"], config.DB_PATH
    cfg.CENTRAL_DB["database"] = BD
    from servidor import api as api_mod
    from servidor.central_db import CentralDB
    api_mod._esquema_revisado = False
    with CentralDB() as db:
        idc = db.crear_condominio("76543210-3", "Condominio Prueba", "C 1", "Ovalle", "a@b.cl", None)
        db.crear_suscripcion(idc, 1, 30)
        db.reemplazar_nodo(idc, "Portería", hashlib.sha256(CLAVE_NODO.encode()).hexdigest())
    client = api_mod.app.test_client()

    # el nodo habla con la API por este cliente, como si fuera internet
    from core import cloud
    original_request = cloud._request

    def por_cliente(method, path, token=None, json=None):
        r = client.open(path, method=method, json=json, headers={"X-Nodo-Clave": CLAVE_NODO})
        data = r.get_json()
        if r.status_code >= 400:
            raise cloud.CloudError((data or {}).get("error", f"HTTP {r.status_code}"))
        return data
    cloud._request = por_cliente

    import database
    config.DB_PATH = str(tmp_path_factory.mktemp("nodo") / "nodo.db")
    database.DatabaseManager._schema_checked = False
    nodo = database.DatabaseManager()
    assert nodo.connect()
    idunidad = nodo.get_or_create_unidad("Casa 7")

    yield {"client": client, "nodo": nodo, "idunidad": idunidad}

    nodo.disconnect()
    cloud._request = original_request
    config.DB_PATH, cfg.CENTRAL_DB["database"] = orig_path, orig_db
    database.DatabaseManager._schema_checked = True
    cur.execute(f"DROP DATABASE IF EXISTS {BD}")
    srv.close()


def _evidencia_rostro():
    """Foto real de la evidencia PI-04a; no se publica en el repositorio porque muestra un rostro."""
    hallados = glob.glob(os.path.join(ROOT, "tests", "evidencias", "PI-04a*.png"))
    if not hallados:
        pytest.skip("falta la evidencia PI-04a (no se publica: contiene un rostro real)")
    return cv2.imread(hallados[0])


def _rostro_png(variante=0):
    img = _evidencia_rostro()
    if variante:
        h, w = img.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), variante * 2.5, 1 + variante * 0.03)
        img = cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REFLECT)
    return cv2.imencode(".png", img)[1].tobytes()


def _token(url):
    return url.rsplit("/", 1)[1]


def _fotos(client, token, n=5):
    fotos = []
    for i in range(n):
        r = client.post(f"/r/{token}/foto", data={
            "foto": (io.BytesIO(_rostro_png(i)), "f.png"), "previos": json.dumps(fotos)},
            content_type="multipart/form-data")
        assert r.status_code == 200, r.get_json()
        fotos.append({"emb": r.get_json()["emb"], "firma": r.get_json()["firma"]})
    return fotos


DATOS = {"nombres": "Ana", "apellidos": "Pérez", "rut": "12.345.678-5", "idtipo_residente": "1",
         "telefono": "", "email": "ana@correo.cl", "fecha_nacimiento": "1990-05-04",
         "patente": "SGL45", "tipo_vehiculo": "moto", "marca": "Yamaha", "color": "azul",
         "modelo": ""}


class TestResidenteNuevo:
    def test_flujo_completo(self, entorno, monkeypatch):
        from core import registro_remoto
        client, nodo = entorno["client"], entorno["nodo"]
        monkeypatch.setattr(config, "MIN_CAPTURE_DIFF", 0.0)   # misma foto de prueba 5 veces
        url = registro_remoto.crear_invitacion(nodo, "residente", entorno["idunidad"], "Casa 7", 48)
        token = _token(url)

        pagina = client.get(f"/r/{token}")
        assert pagina.status_code == 200
        texto = pagina.get_data(as_text=True)
        assert "Condominio Prueba" in texto and "Amazon Web Services" in texto

        assert client.post(f"/r/{token}/validar", json=dict(DATOS, rut="1-1")).status_code == 400
        assert client.post(f"/r/{token}/validar",
                           json=dict(DATOS, fecha_nacimiento="2015-01-01")).status_code == 400
        assert client.post(f"/r/{token}/validar", json=DATOS).status_code == 200

        fotos = _fotos(client, token)
        falsa = [dict(fotos[0], firma="0" * 64)] + fotos[1:]
        r = client.post(f"/r/{token}/enviar", json={"datos": DATOS, "consentimiento": True,
                                                    "fotos": falsa})
        assert r.status_code == 400                        # vector no firmado por la nube
        r = client.post(f"/r/{token}/enviar", json={"datos": DATOS, "consentimiento": False,
                                                    "fotos": fotos})
        assert r.status_code == 400 and "consentimiento" in r.get_json()["error"]
        r = client.post(f"/r/{token}/enviar", json={"datos": DATOS, "consentimiento": True,
                                                    "fotos": fotos})
        assert r.status_code == 200
        assert client.post(f"/r/{token}/enviar", json={"datos": DATOS, "consentimiento": True,
                                                       "fotos": fotos}).status_code == 410
        assert client.get(f"/r/{token}").status_code == 410

        # en la nube solo hay un paquete cifrado; sin datos legibles
        envios = client.get("/api/nodo/registros", headers={"X-Nodo-Clave": CLAVE_NODO}).get_json()
        assert len(envios) == 1 and "Pérez" not in envios[0]["paquete"]

        assert registro_remoto.descargar(nodo) == 1
        assert client.get("/api/nodo/registros", headers={"X-Nodo-Clave": CLAVE_NODO}).get_json() == []
        [s] = nodo.list_solicitudes_registro("pendiente")
        assert s["fotos"] == 5 and s["datos"]["rut"] == "12345678-5"
        assert s["consentimiento_fecha"] is not None

        idres = nodo.aprobar_solicitud_residente(s["idsolicitud"])
        assert len([p for p in nodo.get_plantillas_activas() if p["idresidente"] == idres]) == 5
        cons = nodo.get_consentimiento_vigente(idres)
        assert cons["medio"] == "digital" and cons["version_formulario"] == config.VERSION_CONSENTIMIENTO
        assert "SGL45" in nodo.get_patentes_autorizadas()
        cerrada = nodo._query("SELECT datos FROM solicitud_registro WHERE idsolicitud = ?",
                              (s["idsolicitud"],), one=True)
        assert cerrada["datos"] == "{}"                     # minimización
        assert nodo._query("SELECT COUNT(*) n FROM solicitud_plantilla", one=True)["n"] == 0

    def test_foto_repetida_y_foto_sin_rostro(self, entorno):
        from core import registro_remoto
        client, nodo = entorno["client"], entorno["nodo"]
        token = _token(registro_remoto.crear_invitacion(nodo, "residente", entorno["idunidad"],
                                                        "Casa 7", 48))
        primera = client.post(f"/r/{token}/foto", data={
            "foto": (io.BytesIO(_rostro_png()), "f.png"), "previos": "[]"},
            content_type="multipart/form-data").get_json()
        r = client.post(f"/r/{token}/foto", data={
            "foto": (io.BytesIO(_rostro_png()), "f.png"),
            "previos": json.dumps([{"emb": primera["emb"], "firma": primera["firma"]}])},
            content_type="multipart/form-data")
        assert r.status_code == 422 and "casi igual" in r.get_json()["error"]
        negra = cv2.imencode(".png", np.zeros((480, 640, 3), np.uint8))[1].tobytes()
        r = client.post(f"/r/{token}/foto", data={"foto": (io.BytesIO(negra), "f.png"),
                                                  "previos": "[]"},
                        content_type="multipart/form-data")
        assert r.status_code == 422 and "rostro" in r.get_json()["error"]

    def test_rut_repetido_no_se_aprueba(self, entorno, monkeypatch):
        from core import registro_remoto
        client, nodo = entorno["client"], entorno["nodo"]
        monkeypatch.setattr(config, "MIN_CAPTURE_DIFF", 0.0)
        token = _token(registro_remoto.crear_invitacion(nodo, "residente", entorno["idunidad"],
                                                        "Casa 7", 48))
        fotos = _fotos(client, token)
        datos = dict(DATOS, patente="")
        assert client.post(f"/r/{token}/enviar", json={"datos": datos, "consentimiento": True,
                                                       "fotos": fotos}).status_code == 200
        registro_remoto.descargar(nodo)
        [s] = nodo.list_solicitudes_registro("pendiente")
        with pytest.raises(ValueError, match="Ya existe"):
            nodo.aprobar_solicitud_residente(s["idsolicitud"])
        nodo.rechazar_solicitud(s["idsolicitud"], observacion="duplicado")
        assert nodo.list_solicitudes_registro("pendiente") == []
        assert nodo._query("SELECT COUNT(*) n FROM solicitud_plantilla", one=True)["n"] == 0


class TestSoloRostroYVisita:
    def test_solo_rostro_para_residente_existente(self, entorno, monkeypatch):
        from core import registro_remoto
        client, nodo = entorno["client"], entorno["nodo"]
        monkeypatch.setattr(config, "MIN_CAPTURE_DIFF", 0.0)
        idres = nodo.create_residente(entorno["idunidad"], 2, "22222222-2", "Luis", "Soto")
        token = _token(registro_remoto.crear_invitacion(nodo, "residente", entorno["idunidad"],
                                                        "Casa 7", 24, idresidente=idres))
        assert "Registro de rostro" in client.get(f"/r/{token}").get_data(as_text=True)
        fotos = _fotos(client, token)
        assert client.post(f"/r/{token}/enviar", json={"consentimiento": True,
                                                       "fotos": fotos}).status_code == 200
        registro_remoto.descargar(nodo)
        [s] = nodo.list_solicitudes_registro("pendiente")
        assert nodo.aprobar_solicitud_residente(s["idsolicitud"]) == idres
        assert nodo._query("SELECT COUNT(*) n FROM residente WHERE rut = '22222222-2'",
                           one=True)["n"] == 1
        assert len([p for p in nodo.get_plantillas_activas() if p["idresidente"] == idres]) == 5

    def test_visita_ocasional_con_rostro_reconocida_y_borrada_al_vencer(self, entorno, monkeypatch):
        from datetime import date
        from core import registro_remoto
        from core import face_utils as fu
        client, nodo = entorno["client"], entorno["nodo"]
        monkeypatch.setattr(config, "MIN_CAPTURE_DIFF", 0.0)
        monkeypatch.setattr(config, "VISITA_ROSTRO_OBLIGATORIO", True)
        token = _token(registro_remoto.crear_invitacion(nodo, "visita", entorno["idunidad"],
                                                        "Casa 7", 24))
        pagina = client.get(f"/r/{token}").get_data(as_text=True)
        assert "reglamento del condominio" in pagina and "día siguiente" in pagina
        datos = {"nombres": "Carla", "apellidos": "Rojas", "rut": "33333333-3",
                 "fecha_visita": date.today().isoformat(), "patente": "BCDF12",
                 "tipo_vehiculo": "auto"}
        # el reglamento exige rostro: sin fotos ni consentimiento no se acepta
        assert client.post(f"/r/{token}/enviar", json={"datos": datos}).status_code == 400
        fotos = _fotos(client, token)
        assert client.post(f"/r/{token}/enviar", json={"datos": datos, "consentimiento": True,
                                                       "fotos": fotos}).status_code == 200
        registro_remoto.descargar(nodo)
        [s] = nodo.list_solicitudes_registro("pendiente")
        assert s["tipo"] == "visita" and s["fotos"] == 5 and not s["frecuente"]
        idaut = nodo.aprobar_solicitud_visita(s["idsolicitud"])

        # la patente queda autorizada y el rostro se carga para el reconocimiento de hoy
        assert "BCDF12" in nodo.get_patentes_visitas_activas()
        conocidos = fu.load_known_faces(nodo)
        visita = [k for k in conocidos if k["tipo"] == "visita"]
        assert len(visita) == 5 and visita[0]["idautorizacion"] == idaut

        # el motor la reconoce como VISITA y lo registra en el historial. (En esta base de
        # prueba la misma foto también está inscrita como residentes: con ellos el margen
        # impediría decidir, que es lo correcto; aquí se prueba solo a la visita.)
        from engine.security_engine import SecurityEngine
        eng = SecurityEngine()
        eng.db, eng._idcamara, eng.known_faces = nodo, nodo.list_camaras()[0]["idcamara"] \
            if nodo.list_camaras() else self._camara(nodo), visita
        eng._person_memory[1] = {"name": None, "display_name": "", "attempts": 0, "votes": {},
                                 "candidates": {}, "is_registered": False}
        img = _evidencia_rostro()
        eng._do_recognition(img, 1, 1)
        eng._do_recognition(img, 1, 2)
        p = eng._person_memory[1]
        assert p["is_registered"] and p["display_name"].startswith("VISITA: Carla Rojas")
        ultima = nodo.list_detecciones_rostro(limit=1)[0]
        assert ultima["resultado"] == "visita" and ultima["persona"] == "Visita: Carla Rojas"

        # al día siguiente de la visita se borra con su rostro
        nodo._exec("UPDATE visita_autorizada SET fecha_desde = date('now', 'localtime', '-2 days'), "
                   "fecha_hasta = date('now', 'localtime', '-1 days') WHERE idautorizacion = ?",
                   (idaut,))
        assert nodo.purgar_autorizaciones_vencidas() == 1
        assert nodo._query("SELECT COUNT(*) n FROM plantilla_visita", one=True)["n"] == 0
        assert ultima["resultado"] == "visita"   # el evento queda (sin vínculo a la persona)

    @staticmethod
    def _camara(nodo):
        idz = nodo.get_or_create_zona("Acceso")
        return nodo.create_camara(idz, "Portón", "rtsp", "rtsp://x", 640, 360, 15, True)

    def test_visita_frecuente_no_se_borra_hasta_revocarla(self, entorno, monkeypatch):
        from core import registro_remoto
        client, nodo = entorno["client"], entorno["nodo"]
        monkeypatch.setattr(config, "MIN_CAPTURE_DIFF", 0.0)
        token = _token(registro_remoto.crear_invitacion(nodo, "visita", entorno["idunidad"],
                                                        "Casa 7", 24, frecuente=True))
        pagina = client.get(f"/r/{token}").get_data(as_text=True)
        assert "frecuente" in pagina and 'id=fecha_visita' not in pagina
        datos = {"nombres": "Rosa", "apellidos": "Díaz", "rut": "44444444-4"}
        fotos = _fotos(client, token)
        assert client.post(f"/r/{token}/enviar", json={"datos": datos, "consentimiento": True,
                                                       "fotos": fotos}).status_code == 200
        registro_remoto.descargar(nodo)
        [s] = nodo.list_solicitudes_registro("pendiente")
        idaut = nodo.aprobar_solicitud_visita(s["idsolicitud"])
        a = nodo.get_autorizacion_visita(idaut)
        assert a["frecuente"] == 1 and a["fecha_hasta"] is None
        assert nodo.purgar_autorizaciones_vencidas() == 0
        nodo.purgar_datos_vencidos(90, 30)          # no borra al visitante frecuente
        assert nodo.get_autorizacion_visita(idaut) is not None
        nodo.revocar_autorizacion_visita(idaut)
        assert nodo.get_autorizacion_visita(idaut) is None
        assert nodo._query("SELECT COUNT(*) n FROM plantilla_visita", one=True)["n"] == 0

    def test_sin_reglamento_la_visita_no_registra_rostro(self, entorno, monkeypatch):
        from datetime import date
        from core import registro_remoto
        client, nodo = entorno["client"], entorno["nodo"]
        monkeypatch.setattr(config, "VISITA_ROSTRO_OBLIGATORIO", False)
        token = _token(registro_remoto.crear_invitacion(nodo, "visita", entorno["idunidad"],
                                                        "Casa 7", 24))
        assert "<section id=paso-fotos" not in client.get(f"/r/{token}").get_data(as_text=True)
        assert client.post(f"/r/{token}/foto", data={}).status_code == 410
        datos = {"nombres": "Juan", "apellidos": "Paz", "rut": "55555555-5",
                 "fecha_visita": date.today().isoformat()}
        assert client.post(f"/r/{token}/enviar", json={"datos": datos}).status_code == 200
        registro_remoto.descargar(nodo)
        [s] = nodo.list_solicitudes_registro("pendiente")
        assert s["fotos"] == 0
        nodo.aprobar_solicitud_visita(s["idsolicitud"])

    def test_la_nube_solo_conoce_la_clave_publica(self, entorno):
        from servidor.central_db import CentralDB
        with CentralDB() as db:
            clave = db._q("SELECT clave_registro FROM nodo WHERE activo", one=True)["clave_registro"]
        assert "PUBLIC KEY" in clave and "PRIVATE" not in clave
        assert os.path.exists(os.path.join(os.path.dirname(config.DB_PATH), "registro_privada.pem"))
