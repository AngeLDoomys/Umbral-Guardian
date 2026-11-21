# -*- coding: utf-8 -*-
"""
Pruebas de integración con la base local SQLite (punto XII del informe):
PI-04/05, PI-06, PI-08, PI-10, PI-12, PR-05 (integridad, en banco) y PS-02,
más las garantías del motor de base: claves foráneas, WAL y migraciones.

Se ejecutan sobre un archivo temporal creado desde migraciones/ y eliminado al
terminar: nunca modifican la base real (config.DB_PATH). PS-02 solo LEE la tabla
de cuentas de la base real.
"""

import json
import os
import re
import sqlite3

import numpy as np
import pytest

import config
import database
from core.plate_utils import load_registered_plates


def _nuevo_manager(path):
    config.DB_PATH = str(path)
    database.DatabaseManager._schema_checked = False
    manager = database.DatabaseManager()
    assert manager.connect()
    return manager


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    original = config.DB_PATH
    manager = _nuevo_manager(tmp_path_factory.mktemp("bd") / "umbral_pruebas.db")
    yield manager
    manager.disconnect()
    config.DB_PATH = original
    database.DatabaseManager._schema_checked = False


@pytest.fixture(scope="module")
def base(db):
    """Datos mínimos: unidad, zona, cámara y un residente con consentimiento y plantilla."""
    idunidad = db.get_or_create_unidad("Casa 12")
    idzona = db.get_or_create_zona("Acceso principal")
    db.create_camara(idzona, "Portón", "rtsp", "rtsp://prueba/102", 1280, 720, 15, True,
                     "rtsp://prueba/101")
    idcamara = db.list_camaras()[0]["idcamara"]
    idres = db.create_residente(idunidad, 1, "12345678-5", "Ana", "Prueba")
    db.registrar_consentimiento(idres, config.VERSION_CONSENTIMIENTO, "escrito")
    db.add_plantilla(idres, np.random.rand(512).tolist(), config.FACE_MODEL)
    return {"idunidad": idunidad, "idcamara": idcamara, "idres": idres}


def _contar(db, tabla, where="1=1", params=()):
    return db._query(f"SELECT COUNT(*) AS n FROM {tabla} WHERE {where}", params, one=True)["n"]


# ── Motor de base: claves foráneas, WAL, migraciones, embedding ───────────

class TestMotorSQLite:
    def test_claves_foraneas_activas_en_cada_conexion(self, db):
        assert db._query("PRAGMA foreign_keys", one=True)["foreign_keys"] == 1
        otra = database.DatabaseManager()
        assert otra.connect()
        try:
            assert otra._query("PRAGMA foreign_keys", one=True)["foreign_keys"] == 1
        finally:
            otra.disconnect()

    def test_modo_wal(self, db):
        assert db._query("PRAGMA journal_mode", one=True)["journal_mode"] == "wal"

    def test_version_de_esquema_es_la_ultima_migracion(self, db):
        ultima = max(int(f[:3]) for f in os.listdir(config.MIGRATIONS_DIR)
                     if re.match(r"^\d{3}_.+\.sql$", f))
        assert db._query("PRAGMA user_version", one=True)["user_version"] == ultima

    def test_migraciones_no_se_reaplican(self, db, tmp_path):
        original = config.DB_PATH
        try:
            m1 = _nuevo_manager(tmp_path / "dos_arranques.db")
            m1.get_or_create_unidad("Casa 1")
            m1.disconnect()
            m2 = _nuevo_manager(tmp_path / "dos_arranques.db")   # segundo arranque del nodo
            assert _contar(m2, "unidad") == 1
            m2.disconnect()
        finally:
            config.DB_PATH = original
            database.DatabaseManager._schema_checked = True

    def test_migracion_002_borra_plantillas_arcface(self, tmp_path):
        """Un nodo en la versión 1 con residentes ArcFace: al actualizar se borran sus
        vectores (minimización) y se conservan el residente y su consentimiento."""
        original = config.DB_PATH
        try:
            ruta = tmp_path / "nodo_v1.db"
            conn = sqlite3.connect(ruta)
            conn.execute("PRAGMA foreign_keys = ON")
            with open(os.path.join(config.MIGRATIONS_DIR, "001_esquema_inicial.sql"),
                      encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.execute("PRAGMA user_version = 1")
            conn.execute("INSERT INTO unidad (codigo) VALUES ('Casa 1')")
            conn.execute("INSERT INTO residente (idunidad, idtipo_residente, rut, nombres, apellidos) "
                         "VALUES (1, 1, '12345678-5', 'Ana', 'Prueba')")
            conn.execute("INSERT INTO consentimiento (idresidente, version_formulario, medio) "
                         "VALUES (1, 'v1.0', 'escrito')")
            conn.execute("INSERT INTO plantilla_facial (idresidente, embedding, modelo) "
                         "VALUES (1, ?, 'ArcFace')", (np.zeros(512, np.float32).tobytes(),))
            conn.execute("INSERT INTO plantilla_facial (idresidente, embedding, modelo) "
                         "VALUES (1, ?, 'SFace')", (np.zeros(128, np.float32).tobytes(),))
            conn.commit()
            conn.close()

            m = _nuevo_manager(ruta)
            assert m._query("PRAGMA user_version", one=True)["user_version"] >= 2
            modelos = [r["modelo"] for r in m._query("SELECT modelo FROM plantilla_facial")]
            assert modelos == ["SFace"]
            assert _contar(m, "residente") == 1 and _contar(m, "consentimiento") == 1
            m.disconnect()
        finally:
            config.DB_PATH = original
            database.DatabaseManager._schema_checked = True

    def test_base_mas_nueva_que_el_programa_no_se_abre(self, tmp_path):
        original = config.DB_PATH
        try:
            ruta = tmp_path / "futura.db"
            conn = sqlite3.connect(ruta)
            conn.execute("PRAGMA user_version = 999")
            conn.close()
            config.DB_PATH = str(ruta)
            database.DatabaseManager._schema_checked = False
            assert database.DatabaseManager().connect() is False
        finally:
            config.DB_PATH = original
            database.DatabaseManager._schema_checked = True

    def test_embedding_float32_en_bytes(self, db, base):
        vector = np.random.rand(512).astype(np.float32)
        db.add_plantilla(base["idres"], vector.tolist(), config.FACE_MODEL)
        blob = db._query("SELECT embedding FROM plantilla_facial ORDER BY idplantilla DESC LIMIT 1",
                         one=True)["embedding"]
        assert isinstance(blob, bytes) and len(blob) == 2048
        guardado = [p for p in db.get_plantillas_activas(config.FACE_MODEL)
                    if np.array_equal(p["embedding"], vector)]
        assert guardado and guardado[0]["embedding"].dtype == np.float32

    def test_fechas_vuelven_como_datetime(self, db, base):
        fila = db._query("SELECT fecha_alta FROM residente WHERE idresidente = ?",
                         (base["idres"],), one=True)
        assert hasattr(fila["fecha_alta"], "hour")

    def test_listas_en_orden_alfabetico_espanol(self, db, base):
        for nombre in ("Órdenes", "zeta", "Ñandú", "Norte"):
            db.get_or_create_zona(nombre)
        assert [z["nombre"] for z in db.list_zonas()] == \
            ["Acceso principal", "Norte", "Ñandú", "Órdenes", "zeta"]

    def test_filtro_de_fecha_acepta_texto_sin_ceros(self, db, base):
        db.add_deteccion_rostro(base["idcamara"], "no_reconocido")
        hoy = db._query("SELECT date('now', 'localtime') AS d", one=True)["d"]
        a, m, d = (int(x) for x in hoy.split("-"))
        assert db.list_detecciones_rostro(f"{a}-{m}-{d}", f"{a}-{m}-{d}")


# ── PI-04 / PI-05 Registro de detecciones de rostro ────────────────────────

class TestPI04_05RegistroRostros:
    def test_residente_reconocido_queda_registrado_con_camara_y_confianza(self, db, base):
        db.add_deteccion_rostro(base["idcamara"], "reconocido", 0.71, base["idres"])
        fila = db._query("SELECT * FROM deteccion_rostro ORDER BY iddeteccion DESC LIMIT 1", one=True)
        assert fila["resultado"] == "reconocido"
        assert fila["idresidente"] == base["idres"]
        assert fila["idcamara"] == base["idcamara"]
        assert fila["fecha_hora"] is not None

    def test_no_reconocido_se_registra_sin_dato_biometrico(self, db, base):
        plantillas_antes = _contar(db, "plantilla_facial")
        db.add_deteccion_rostro(base["idcamara"], "no_reconocido")
        fila = db._query("SELECT * FROM deteccion_rostro ORDER BY iddeteccion DESC LIMIT 1", one=True)
        assert fila["resultado"] == "no_reconocido" and fila["idresidente"] is None
        assert _contar(db, "plantilla_facial") == plantillas_antes   # RNF-09

    def test_historial_muestra_zona(self, db, base):
        filas = db.list_detecciones_rostro()
        assert filas and all(f["zona"] == "Acceso principal" for f in filas)

    def test_historial_muestra_primero_lo_ultimo_registrado_aunque_cambie_el_reloj(self, db, base):
        db.add_deteccion_rostro(base["idcamara"], "reconocido", 0.71, base["idres"])
        db.connection.execute("UPDATE deteccion_rostro SET fecha_hora = '2099-01-01 12:00:00'")
        db.connection.commit()
        db.add_deteccion_rostro(base["idcamara"], "no_reconocido")
        assert db.list_detecciones_rostro(limit=1)[0]["resultado"] == "no_reconocido"


# ── PI-06 Patentes de residentes y de visitas ──────────────────────────────

class TestPI06Patentes:
    def test_patente_de_residente_y_de_visita_activa(self, db, base):
        db.create_vehiculo(base["idunidad"], "BC-DF-12")
        idvisita = db.registrar_visita("11111111-1", "Visita", "Prueba", base["idunidad"], "YC-47-33")
        residentes, visitas = load_registered_plates(db)
        assert "BCDF12" in residentes
        assert "YC4733" in visitas

        db.marcar_salida(idvisita)
        _, visitas = load_registered_plates(db)
        assert "YC4733" not in visitas      # al salir, la patente deja de estar autorizada

    def test_patente_repetida_es_rechazada(self, db, base):
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
            db.create_vehiculo(base["idunidad"], "BC-DF-12")

    def test_visitante_que_vuelve_conserva_su_registro(self, db, base):
        v1 = db.registrar_visita("33333333-3", "Juan", "Uno", base["idunidad"])
        v2 = db.registrar_visita("33333333-3", "Juan", "Actualizado", base["idunidad"])
        assert v1 != v2
        assert _contar(db, "visitante", "rut = ?", ("33333333-3",)) == 1
        fila = db._query("SELECT apellidos FROM visitante WHERE rut = ?", ("33333333-3",), one=True)
        assert fila["apellidos"] == "Actualizado"

    def test_deteccion_de_vehiculo_guarda_patente_normalizada(self, db, base):
        db.add_deteccion_vehiculo(base["idcamara"], "zz-yy-99", "no_registrado", 0.95)
        fila = db._query("SELECT * FROM deteccion_vehiculo ORDER BY iddeteccion DESC LIMIT 1", one=True)
        assert fila["patente_leida"] == "ZZYY99" and fila["resultado"] == "no_registrado"


# ── PI-08 Bloqueo y revocación ─────────────────────────────────────────────

class TestPI08BloqueoYRevocacion:
    def _ids_activos(self, db):
        return {p["idresidente"] for p in db.get_plantillas_activas(config.FACE_MODEL)}

    def test_bloqueo_suspende_sin_borrar(self, db, base):
        idres = base["idres"]
        assert idres in self._ids_activos(db)
        db.set_bloqueo(idres, True)
        assert idres not in self._ids_activos(db)
        assert _contar(db, "plantilla_facial", "idresidente = ?", (idres,)) > 0  # se conserva
        db.set_bloqueo(idres, False)
        assert idres in self._ids_activos(db)

    def test_sin_consentimiento_no_se_usa_la_plantilla(self, db, base):
        idres = db.create_residente(base["idunidad"], 2, "6-K", "Sin", "Consentimiento")
        db.add_plantilla(idres, np.random.rand(512).tolist(), config.FACE_MODEL)
        assert idres not in self._ids_activos(db)

    def test_revocacion_elimina_las_plantillas(self, db, base):
        idres = db.create_residente(base["idunidad"], 1, "11111111-1", "Revoca", "Prueba")
        db.registrar_consentimiento(idres, config.VERSION_CONSENTIMIENTO, "digital")
        db.add_plantilla(idres, np.random.rand(512).tolist(), config.FACE_MODEL)
        assert idres in self._ids_activos(db)
        db.revocar_consentimiento(idres)
        assert _contar(db, "plantilla_facial", "idresidente = ?", (idres,)) == 0
        assert db.get_consentimiento_vigente(idres) is None


# ── PI-10 Política de retención ────────────────────────────────────────────

class TestPI10Retencion:
    def test_purga_solo_lo_vencido(self, db, base):
        cam = base["idcamara"]
        hace = "datetime('now', 'localtime', '-{} days')".format
        db._exec("INSERT INTO deteccion_rostro (idcamara, resultado, fecha_hora) "
                 f"VALUES (?, 'no_reconocido', {hace(100)})", (cam,))
        db._exec("INSERT INTO deteccion_vehiculo (idcamara, patente_leida, resultado, fecha_hora) "
                 f"VALUES (?, 'AB1234', 'no_registrado', {hace(100)})", (cam,))
        idv = db.registrar_visita("12345678-5", "Antigua", "Visita", base["idunidad"])
        db._exec(f"UPDATE visita SET fecha_ingreso = {hace(40)} WHERE idvisita = ?", (idv,))
        recientes = _contar(db, "deteccion_rostro", f"fecha_hora > {hace(1)}")

        borrados = db.purgar_datos_vencidos(config.DIAS_RETENCION_DETECCIONES,
                                            config.DIAS_RETENCION_VISITAS)
        assert borrados["detecciones_rostro"] >= 1
        assert borrados["detecciones_vehiculo"] >= 1
        assert borrados["visitas"] >= 1
        assert _contar(db, "deteccion_rostro", f"fecha_hora < {hace(90)}") == 0
        assert _contar(db, "deteccion_rostro", f"fecha_hora > {hace(1)}") == recientes


# ── PI-12 Derechos del titular ─────────────────────────────────────────────

class TestPI12DerechosDelTitular:
    def test_exportacion_estructurada_sin_vectores_biometricos(self, db, base):
        datos = db.exportar_residente(base["idres"])
        assert {"titular", "consentimientos", "plantillas_faciales",
                "registros_de_acceso", "finalidad"} <= datos.keys()
        texto = json.dumps(datos, default=str, ensure_ascii=False)   # formato de uso común
        assert "embedding" not in texto
        assert datos["titular"]["rut"] == "12345678-5"

    def test_supresion_anonimiza_el_historial_y_deja_constancia(self, db, base):
        idunidad = base["idunidad"]
        idres = db.create_residente(idunidad, 1, "22222222-2", "Suprime", "Prueba")
        db.add_deteccion_rostro(base["idcamara"], "reconocido", 0.8, idres)
        idsol = db.create_solicitud(idres, "22222222-2", "supresion")

        db.delete_residente(idres)
        db.cerrar_solicitud(idsol, "acogida", "Datos suprimidos", None)

        assert _contar(db, "residente", "idresidente = ?", (idres,)) == 0
        assert _contar(db, "deteccion_rostro", "idresidente = ?", (idres,)) == 0
        assert _contar(db, "deteccion_rostro", "idresidente IS NULL AND resultado = 'reconocido'") >= 1
        sol = db._query("SELECT * FROM solicitud_derecho WHERE idsolicitud = ?", (idsol,), one=True)
        # ON DELETE SET NULL (art. 12): el vínculo se rompe, la constancia queda
        assert sol["idresidente"] is None
        assert sol["rut_titular"] == "22222222-2" and sol["estado"] == "acogida"


# ── PR-05 Integridad del registro (en banco) ───────────────────────────────

class TestPR05Integridad:
    def test_cada_evento_del_motor_queda_persistido(self, db, base, monkeypatch):
        from engine import security_engine as se
        eng = se.SecurityEngine()
        eng.db, eng._idcamara = db, base["idcamara"]
        antes_v = _contar(db, "deteccion_vehiculo")
        antes_r = _contar(db, "deteccion_rostro")

        for cid, patente in enumerate(["BC-DF-12", "KL-MN-34", "AB-12-34"], start=100):
            eng._vote_plate(patente, 0.97, cid, (0, 0, 10, 10), 1)
            eng._vote_plate(patente, 0.97, cid, (0, 0, 10, 10), 2)

        cara = np.zeros((80, 80, 3), np.uint8)
        seq = iter([{"status": "no_match", "face": cara, "distance": 0.9}] * config.FACE_MAX_ATTEMPTS)
        monkeypatch.setattr(se, "recognize_face", lambda img, known: next(seq))
        eng._person_memory[1] = {"name": None, "display_name": "", "attempts": 0, "votes": {},
                                 "candidates": {}, "is_registered": False}
        for _ in range(config.FACE_MAX_ATTEMPTS):
            eng._do_recognition(None, 1, 1)

        eventos_vehiculo = (eng._stats["plates_registered"] + eng._stats["plates_visit"]
                            + eng._stats["plates_unregistered"])
        eventos_rostro = eng._stats["faces_registered"] + eng._stats["faces_unknown"]
        assert eventos_vehiculo == 3 and eventos_rostro == 1
        assert _contar(db, "deteccion_vehiculo") - antes_v == eventos_vehiculo
        assert _contar(db, "deteccion_rostro") - antes_r == eventos_rostro


# ── PS-02 Contraseñas en la base real (solo lectura) ───────────────────────

class TestPS02Contrasenas:
    def test_cuentas_sin_claves_en_texto_plano(self):
        real = config._DEFAULTS["DB_PATH"]
        if not os.path.exists(real):
            pytest.skip(f"Base local {real} aún no existe")
        conn = sqlite3.connect(f"file:{real}?mode=ro", uri=True)
        try:
            hashes = [r[0] for r in conn.execute("SELECT password_hash FROM cuenta_local")]
        except sqlite3.Error as e:
            pytest.skip(f"Base local no legible: {e}")
        finally:
            conn.close()
        if not hashes:
            pytest.skip("La base local aún no tiene cuentas sincronizadas")
        assert all(re.fullmatch(r"pbkdf2_sha256\$\d+\$[0-9a-f]{32}\$[0-9a-f]{64}", h) for h in hashes)
