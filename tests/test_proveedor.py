# -*- coding: utf-8 -*-
"""
Panel del proveedor: planes y precios, cambio de plan, historial y anulación de
pagos, y gestión de cuentas de los condominios.

Usa una base central TEMPORAL (umbral_central_pruebas_prov), creada desde
sql/central.sql y eliminada al terminar; se omite si MySQL no está disponible.
"""

import hashlib
import os
import re
from datetime import date

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BD = "umbral_central_pruebas_prov"
CLAVE_NODO = "ugn_prueba_prov"


@pytest.fixture(scope="module")
def api():
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

    original = cfg.CENTRAL_DB["database"]
    cfg.CENTRAL_DB["database"] = BD
    from servidor import api as api_mod
    from servidor.central_db import CentralDB
    api_mod._esquema_revisado = False
    with CentralDB() as db:
        db.crear_cuenta(None, "superadmin", "11111111-1", "Pro", "Veedor",
                        "proveedor@prueba.cl", "Proveedor123")
        idc = db.crear_condominio("76543210-3", "Cond Uno", "Calle 1", "Ovalle", "a@b.cl", None)
        idsusc = db.crear_suscripcion(idc, 1, 30)
        db.reemplazar_nodo(idc, "Portería", hashlib.sha256(CLAVE_NODO.encode()).hexdigest())
        idadm = db.crear_cuenta(idc, "administrador", "12345678-5", "Ad", "Min",
                                "admin@prueba.cl", "Admin1234")
    client = api_mod.app.test_client()
    r = client.post("/api/login", json={"email": "proveedor@prueba.cl", "password": "Proveedor123"})
    token = r.get_json()["token"]
    yield client, {"Authorization": f"Bearer {token}"}, {"idc": idc, "idsusc": idsusc,
                                                         "idadm": idadm}
    cfg.CENTRAL_DB["database"] = original
    cur.execute(f"DROP DATABASE IF EXISTS {BD}")
    srv.close()


def _condominio(client, h, idc):
    return next(c for c in client.get("/api/proveedor/condominios", headers=h).get_json()
                if c["idcondominio"] == idc)


class TestPlanes:
    def test_crear_editar_y_desactivar_plan(self, api):
        client, h, _ = api
        r = client.post("/api/proveedor/planes", headers=h,
                        json={"nombre": "Premium", "precio_mensual": "249990", "max_camaras": 12})
        assert r.status_code == 201
        idplan = r.get_json()["idplan"]
        r = client.post(f"/api/proveedor/planes/{idplan}", headers=h, json={
            "nombre": "Premium", "precio_mensual": 259990, "max_camaras": 16, "activo": False})
        assert r.status_code == 200
        activos = {p["nombre"] for p in client.get("/api/proveedor/planes", headers=h).get_json()}
        todos = {p["nombre"]: p for p in
                 client.get("/api/proveedor/planes?todos=1", headers=h).get_json()}
        assert "Premium" not in activos                     # no se ofrece a clientes nuevos
        assert todos["Premium"]["precio_mensual"] == 259990 and todos["Premium"]["max_camaras"] == 16

    @pytest.mark.parametrize("body, error", [
        ({"nombre": "", "precio_mensual": 1, "max_camaras": 2}, "nombre"),
        ({"nombre": "X", "precio_mensual": "abc", "max_camaras": 2}, "enteros"),
        ({"nombre": "X", "precio_mensual": -5, "max_camaras": 2}, "Precio"),
        ({"nombre": "X", "precio_mensual": 5, "max_camaras": 0}, "cámaras"),
    ])
    def test_validaciones(self, api, body, error):
        client, h, _ = api
        r = client.post("/api/proveedor/planes", headers=h, json=body)
        assert r.status_code == 400 and error in r.get_json()["error"]

    def test_nombre_repetido(self, api):
        client, h, _ = api
        r = client.post("/api/proveedor/planes", headers=h,
                        json={"nombre": "Básico", "precio_mensual": 1, "max_camaras": 1})
        assert r.status_code == 409


class TestCambioDePlan:
    def test_cambiar_plan_y_la_licencia_lo_refleja(self, api):
        client, h, ids = api
        estandar = next(p for p in client.get("/api/proveedor/planes", headers=h).get_json()
                        if p["nombre"] == "Estándar")
        r = client.post(f"/api/proveedor/suscripciones/{ids['idsusc']}/plan", headers=h,
                        json={"idplan": estandar["idplan"]})
        assert r.status_code == 200
        c = _condominio(client, h, ids["idc"])
        assert c["plan"] == "Estándar" and c["max_camaras"] == estandar["max_camaras"]
        lic = client.get("/api/nodo/sincronizar", headers={"X-Nodo-Clave": CLAVE_NODO}).get_json()
        assert f'"max_camaras": {estandar["max_camaras"]}' in lic["licencia"]["contenido"] or \
            f'"max_camaras":{estandar["max_camaras"]}' in lic["licencia"]["contenido"]

    def test_no_se_asigna_un_plan_desactivado(self, api):
        client, h, ids = api
        premium = next(p for p in client.get("/api/proveedor/planes?todos=1", headers=h).get_json()
                       if p["nombre"] == "Premium")
        r = client.post(f"/api/proveedor/suscripciones/{ids['idsusc']}/plan", headers=h,
                        json={"idplan": premium["idplan"]})
        assert r.status_code == 400


class TestPagos:
    def test_pago_historial_y_anulacion_restaura_la_vigencia(self, api):
        client, h, ids = api
        antes = _condominio(client, h, ids["idc"])["fecha_fin"]
        r = client.post(f"/api/proveedor/suscripciones/{ids['idsusc']}/pagos", headers=h,
                        json={"meses": 2, "referencia": "TRX-1", "medio": "efectivo"})
        assert r.status_code == 200
        despues = _condominio(client, h, ids["idc"])["fecha_fin"]
        assert date.fromisoformat(despues) > date.fromisoformat(antes)

        pagos = client.get(f"/api/proveedor/condominios/{ids['idc']}/pagos", headers=h).get_json()
        p = pagos[0]
        assert p["medio"] == "efectivo" and p["meses"] == 2 and not p["anulado"]
        assert p["monto"] == 2 * _condominio(client, h, ids["idc"])["precio_mensual"]

        assert client.post(f"/api/proveedor/pagos/{p['idpago']}/anular", headers=h,
                           json={"motivo": ""}).status_code == 400      # motivo obligatorio
        r = client.post(f"/api/proveedor/pagos/{p['idpago']}/anular", headers=h,
                        json={"motivo": "Transferencia rechazada"})
        assert r.status_code == 200
        assert _condominio(client, h, ids["idc"])["fecha_fin"] == antes   # vigencia restaurada
        p = client.get(f"/api/proveedor/condominios/{ids['idc']}/pagos", headers=h).get_json()[0]
        assert p["anulado"] and p["motivo_anulacion"] == "Transferencia rechazada"
        # no se anula dos veces
        assert client.post(f"/api/proveedor/pagos/{p['idpago']}/anular", headers=h,
                           json={"motivo": "otra vez"}).status_code == 400

    def test_solo_se_anula_el_ultimo_pago_vigente(self, api):
        client, h, ids = api
        for ref in ("A", "B"):
            client.post(f"/api/proveedor/suscripciones/{ids['idsusc']}/pagos", headers=h,
                        json={"meses": 1, "referencia": ref})
        pagos = [p for p in client.get(f"/api/proveedor/condominios/{ids['idc']}/pagos",
                                       headers=h).get_json() if not p["anulado"]]
        ultimo, anterior = pagos[0], pagos[1]
        r = client.post(f"/api/proveedor/pagos/{anterior['idpago']}/anular", headers=h,
                        json={"motivo": "error"})
        assert r.status_code == 400 and "último" in r.get_json()["error"]
        assert client.post(f"/api/proveedor/pagos/{ultimo['idpago']}/anular", headers=h,
                           json={"motivo": "error"}).status_code == 200
        assert client.post(f"/api/proveedor/pagos/{anterior['idpago']}/anular", headers=h,
                           json={"motivo": "error"}).status_code == 200

    def test_medio_de_pago_invalido(self, api):
        client, h, ids = api
        r = client.post(f"/api/proveedor/suscripciones/{ids['idsusc']}/pagos", headers=h,
                        json={"meses": 1, "medio": "bitcoin"})
        assert r.status_code == 400


class TestCuentas:
    def test_proveedor_desactiva_y_reactiva_una_cuenta(self, api):
        client, h, ids = api
        r = client.post(f"/api/proveedor/cuentas/{ids['idadm']}/activa", headers=h,
                        json={"activa": False})
        assert r.status_code == 200
        r = client.post("/api/login", json={"email": "admin@prueba.cl", "password": "Admin1234"},
                        headers={"X-Nodo-Clave": CLAVE_NODO})
        assert r.status_code == 401 and "desactivada" in r.get_json()["error"]
        client.post(f"/api/proveedor/cuentas/{ids['idadm']}/activa", headers=h,
                    json={"activa": True})
        r = client.post("/api/login", json={"email": "admin@prueba.cl", "password": "Admin1234"},
                        headers={"X-Nodo-Clave": CLAVE_NODO})
        assert r.status_code == 200

    def test_endpoints_del_proveedor_exigen_rol_superadmin(self, api):
        client, _, ids = api
        r = client.post("/api/login", json={"email": "admin@prueba.cl", "password": "Admin1234"},
                        headers={"X-Nodo-Clave": CLAVE_NODO})
        h_adm = {"Authorization": f"Bearer {r.get_json()['token']}", "X-Nodo-Clave": CLAVE_NODO}
        for metodo, ruta in [("post", "/api/proveedor/planes"),
                             ("post", f"/api/proveedor/suscripciones/{ids['idsusc']}/plan"),
                             ("get", f"/api/proveedor/condominios/{ids['idc']}/pagos"),
                             ("post", "/api/proveedor/pagos/1/anular"),
                             ("post", f"/api/proveedor/cuentas/{ids['idadm']}/activa")]:
            assert getattr(client, metodo)(ruta, headers=h_adm, json={}).status_code == 403
