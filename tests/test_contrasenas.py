# -*- coding: utf-8 -*-
"""
Contraseñas temporales: restablecer (proveedor y administrador), cambio obligatorio
al ingresar y cambio de la propia contraseña.

Las pruebas de la API usan una base central TEMPORAL (umbral_central_pruebas),
creada desde sql/central.sql y eliminada al terminar; se omiten si MySQL no está
disponible. Nunca tocan umbral_central.
"""

import hashlib
import os
import re

import pytest

from core.security import password_problem, temporary_password, verify_password

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BD = "umbral_central_pruebas"
CLAVE_NODO = "ugn_prueba_nodo"


def test_contrasena_temporal_valida_y_sin_caracteres_ambiguos():
    vistas = set()
    for _ in range(200):
        p = temporary_password()
        assert password_problem(p) is None
        assert not set(p) & set("0O1lI")
        vistas.add(p)
    assert len(vistas) == 200     # aleatorias


# ── API central ─────────────────────────────────────────────────────────────

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
        db.crear_suscripcion(idc, 1, 30)
        db.reemplazar_nodo(idc, "Portería", hashlib.sha256(CLAVE_NODO.encode()).hexdigest())
        ids = {
            "admin": db.crear_cuenta(idc, "administrador", "12345678-5", "Ad", "Min",
                                     "admin@prueba.cl", "Admin1234"),
            "admin2": db.crear_cuenta(idc, "administrador", "6-K", "Otro", "Admin",
                                      "admin2@prueba.cl", "Admin2345"),
            "conserje": db.crear_cuenta(idc, "conserje", "22222222-2", "Con", "Serje",
                                        "conserje@prueba.cl", "Conserje123"),
        }
        idc2 = db.crear_condominio("77777777-7", "Cond Dos", "Calle 2", "Ovalle", "c@d.cl", None)
        ids["ajeno"] = db.crear_cuenta(idc2, "conserje", "33333333-3", "Aje", "No",
                                       "ajeno@prueba.cl", "Ajeno1234")

    client = api_mod.app.test_client()
    yield client, ids, idc
    cfg.CENTRAL_DB["database"] = original
    cur.execute(f"DROP DATABASE IF EXISTS {BD}")
    srv.close()


def _login(client, email, pwd):
    r = client.post("/api/login", json={"email": email, "password": pwd},
                    headers={"X-Nodo-Clave": CLAVE_NODO})
    return r.status_code, r.get_json()


def _h(token):
    return {"Authorization": f"Bearer {token}", "X-Nodo-Clave": CLAVE_NODO}


class TestRestablecerPorAdministrador:
    def test_admin_restablece_y_el_usuario_debe_cambiarla(self, api):
        client, ids, _ = api
        _, adm = _login(client, "admin@prueba.cl", "Admin1234")
        r = client.post(f"/api/cuentas/{ids['admin2']}/password", headers=_h(adm["token"]))
        assert r.status_code == 200
        temporal = r.get_json()["password_temporal"]
        assert password_problem(temporal) is None

        # la contraseña anterior ya no sirve
        assert _login(client, "admin2@prueba.cl", "Admin2345")[0] == 401
        code, data = _login(client, "admin2@prueba.cl", temporal)
        assert code == 200 and data["cuenta"]["debe_cambiar_password"] is True

        # con clave temporal, la API solo permite cambiarla
        tok = data["token"]
        r = client.get("/api/cuentas", headers=_h(tok))
        assert r.status_code == 403 and "temporal" in r.get_json()["error"]

        r = client.post("/api/cuenta/password", headers=_h(tok),
                        json={"actual": "malacontra1", "nueva": "NuevaClave9"})
        assert r.status_code == 400 and "actual" in r.get_json()["error"]
        r = client.post("/api/cuenta/password", headers=_h(tok),
                        json={"actual": temporal, "nueva": "corta1"})
        assert r.status_code == 400
        r = client.post("/api/cuenta/password", headers=_h(tok),
                        json={"actual": temporal, "nueva": temporal})
        assert r.status_code == 400 and "distinta" in r.get_json()["error"]
        r = client.post("/api/cuenta/password", headers=_h(tok),
                        json={"actual": temporal, "nueva": "NuevaClave9"})
        assert r.status_code == 200

        assert client.get("/api/cuentas", headers=_h(tok)).status_code == 200
        assert _login(client, "admin2@prueba.cl", temporal)[0] == 401
        code, data = _login(client, "admin2@prueba.cl", "NuevaClave9")
        assert code == 200 and data["cuenta"]["debe_cambiar_password"] is False

    def test_admin_no_restablece_la_propia_ni_la_de_otro_condominio(self, api):
        client, ids, _ = api
        _, adm = _login(client, "admin@prueba.cl", "Admin1234")
        assert client.post(f"/api/cuentas/{ids['admin']}/password",
                           headers=_h(adm["token"])).status_code == 400
        assert client.post(f"/api/cuentas/{ids['ajeno']}/password",
                           headers=_h(adm["token"])).status_code == 404

    def test_conserje_no_puede_restablecer(self, api):
        client, ids, _ = api
        _, con = _login(client, "conserje@prueba.cl", "Conserje123")
        assert client.post(f"/api/cuentas/{ids['admin']}/password",
                           headers=_h(con["token"])).status_code == 403

    def test_cuenta_nueva_queda_con_clave_temporal(self, api):
        client, _, _ = api
        _, adm = _login(client, "admin@prueba.cl", "Admin1234")
        r = client.post("/api/cuentas", headers=_h(adm["token"]), json={
            "rut": "44444444-4", "nombres": "Nuevo", "apellidos": "Conserje",
            "email": "nuevo@prueba.cl", "password": "Inicial123", "rol": "conserje"})
        assert r.status_code == 201
        assert _login(client, "nuevo@prueba.cl", "Inicial123")[1]["cuenta"]["debe_cambiar_password"]

    def test_la_sincronizacion_del_nodo_lleva_la_marca(self, api):
        client, _, _ = api
        r = client.get("/api/nodo/sincronizar", headers={"X-Nodo-Clave": CLAVE_NODO})
        cuentas = {c["email"]: c for c in r.get_json()["cuentas"]}
        assert cuentas["nuevo@prueba.cl"]["debe_cambiar_password"] in (1, True)
        assert cuentas["admin@prueba.cl"]["debe_cambiar_password"] in (0, False)


class TestRestablecerPorProveedor:
    def test_proveedor_ve_las_cuentas_y_restablece_al_administrador(self, api):
        client, ids, idc = api
        _, pro = _login(client, "proveedor@prueba.cl", "Proveedor123")
        r = client.get(f"/api/proveedor/condominios/{idc}/cuentas", headers=_h(pro["token"]))
        assert r.status_code == 200
        assert "password_hash" not in r.get_json()[0]          # nunca se exponen los hashes
        r = client.post(f"/api/proveedor/cuentas/{ids['admin']}/password",
                        headers=_h(pro["token"]))
        temporal = r.get_json()["password_temporal"]
        code, data = _login(client, "admin@prueba.cl", temporal)
        assert code == 200 and data["cuenta"]["debe_cambiar_password"] is True

    def test_administrador_no_usa_endpoints_del_proveedor(self, api):
        client, ids, idc = api
        _, con = _login(client, "conserje@prueba.cl", "Conserje123")
        assert client.get(f"/api/proveedor/condominios/{idc}/cuentas",
                          headers=_h(con["token"])).status_code == 403


# ── nodo sin conexión ───────────────────────────────────────────────────────

def test_sin_conexion_una_clave_temporal_no_permite_ingresar(tmp_path):
    import config
    import database
    from core import session
    from core.security import hash_password
    original = config.DB_PATH
    try:
        config.DB_PATH = str(tmp_path / "nodo.db")
        database.DatabaseManager._schema_checked = False
        db = database.DatabaseManager()
        assert db.connect()
        db.sincronizar_cuentas([{"idcuenta": 7, "rol": "conserje", "rut": "1-9", "nombres": "A",
                                 "apellidos": "B", "email": "t@p.cl",
                                 "password_hash": hash_password("Temporal123"),
                                 "debe_cambiar_password": 1, "activa": 1}])
        with pytest.raises(session.LoginError, match="temporal"):
            session._login_sin_conexion(db, "t@p.cl", "Temporal123")
        db.disconnect()
    finally:
        config.DB_PATH = original
        database.DatabaseManager._schema_checked = True
