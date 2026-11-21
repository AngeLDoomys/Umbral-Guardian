# -*- coding: utf-8 -*-
"""
database.py - Base LOCAL del nodo de Umbral Guardian (SQLite, PC de la portería).
Esquema: migraciones/NNN_*.sql, aplicadas al conectar según PRAGMA user_version.
Contiene los datos de UN condominio: residentes, consentimientos, plantillas
faciales, vehículos, visitas, cámaras y detecciones.
Las cuentas y la suscripción viven en la nube (ver core/cloud.py); aquí solo hay
una réplica para operar sin conexión.
"""

import functools
import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
from datetime import date, datetime

import numpy as np

import config
from core import events
from core.security import clean_plate
from core.texto import comparar_es

Error = sqlite3.Error

# ── fechas: se guardan como texto en hora local y se leen como date/datetime ──
# (el mismo formato y los mismos tipos que entregaba MySQL a la interfaz)
sqlite3.register_adapter(datetime, lambda d: d.isoformat(" ", timespec="seconds"))
sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_converter("DATETIME", lambda b: datetime.fromisoformat(b.decode()))
sqlite3.register_converter("DATE", lambda b: date.fromisoformat(b.decode()))

_NOW = "datetime('now', 'localtime')"
_MIGRATION_FILE = re.compile(r"^(\d{3})_[\w-]+\.sql$")


def _fecha(valor):
    """Filtro de fecha como 'AAAA-MM-DD'. MySQL convertía por su cuenta textos como
    '2026-11-7' o un datetime; SQLite compara texto, así que se normaliza aquí."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    try:
        return datetime.strptime(str(valor).strip()[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return valor


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _dict_row(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def _changes_data(method):
    """Marca una escritura que cambia lo que reconocen los motores (rostros,
    patentes, visitas): al confirmarse, se recargan sin esperar la recarga periódica."""
    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        result = method(*args, **kwargs)
        events.data_changed()
        return result
    return wrapper


def _migrations() -> list:
    """[(número, ruta)] de migraciones/, en orden. Los números deben ser 001, 002, ...
    sin saltos ni repetidos: un hueco indicaría un archivo faltante en la instalación."""
    found = []
    for name in os.listdir(config.MIGRATIONS_DIR):
        m = _MIGRATION_FILE.match(name)
        if m:
            found.append((int(m.group(1)), os.path.join(config.MIGRATIONS_DIR, name)))
    found.sort()
    numbers = [n for n, _ in found]
    if numbers != list(range(1, len(numbers) + 1)):
        raise RuntimeError(f"Migraciones incompletas o repetidas en {config.MIGRATIONS_DIR}: {numbers}")
    return found


def _statements(script: str):
    """Separa un archivo .sql en sentencias completas (respeta ';' dentro de textos y triggers)."""
    buf = ""
    for line in script.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                yield buf
            buf = ""
    if buf.strip() and not all(l.strip().startswith("--") or not l.strip()
                               for l in buf.splitlines()):
        raise RuntimeError(f"Sentencia SQL incompleta al final de la migración: {buf[:80]!r}")


class DatabaseManager:
    """Conexión SQLite a la base local y operaciones del nodo."""

    _migrate_lock = threading.Lock()
    _schema_checked = False  # migraciones revisadas una vez por proceso

    def __init__(self):
        self.connection = None

    # ── conexión ──────────────────────────────────────────────────────────

    def connect(self) -> bool:
        try:
            nueva = not os.path.exists(config.DB_PATH)
            os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
            # check_same_thread=False: el motor comparte su conexión entre el hilo de
            # video y los de OCR y rostros, siempre bajo su propio candado (_db_lock)
            conn = sqlite3.connect(config.DB_PATH, timeout=config.DB_TIMEOUT_S,
                                   detect_types=sqlite3.PARSE_DECLTYPES,
                                   check_same_thread=False)
            conn.row_factory = _dict_row
            # orden alfabético en español («Ávila» con las A, la ñ después de la n).
            # Solo se usa en los ORDER BY de este archivo, no en el esquema: así la base
            # se puede abrir con cualquier herramienta de SQLite.
            conn.create_collation("ES", comparar_es)
            # SQLite trae las claves foráneas apagadas y el ajuste es por conexión.
            # Sin esto, ON DELETE CASCADE / SET NULL dejan de funcionar en silencio
            # (p. ej. la anonimización y la constancia de supresión, art. 12).
            conn.execute("PRAGMA foreign_keys = ON")
            if conn.execute("PRAGMA foreign_keys").fetchone()["foreign_keys"] != 1:
                raise RuntimeError("SQLite no aceptó PRAGMA foreign_keys = ON")
            if nueva:
                # WAL: el hilo de captura escribe mientras la interfaz lee, sin
                # "database is locked". Queda guardado en el archivo de la base.
                conn.execute("PRAGMA journal_mode = WAL")
            self.connection = conn
            self._ensure_schema()
            print(f"[DB] Conectado a {config.DB_PATH}")
            return True
        except (sqlite3.Error, OSError, RuntimeError) as e:
            print(f"[DB ERROR] No se pudo abrir la base local: {e}")
            if self.connection is not None:
                self.connection.close()
            self.connection = None
            return False

    def _ensure_schema(self):
        """Aplica las migraciones pendientes (número > PRAGMA user_version), cada una
        en su propia transacción: si falla, la base queda en la versión anterior."""
        with DatabaseManager._migrate_lock:
            if DatabaseManager._schema_checked:
                return
            conn = self.connection
            files = _migrations()
            latest = files[-1][0] if files else 0
            previo = conn.isolation_level
            conn.isolation_level = None  # transacciones explícitas
            try:
                for number, path in files:
                    # BEGIN IMMEDIATE: si dos procesos arrancan a la vez, el segundo
                    # espera y luego ve la versión ya aplicada
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        version = conn.execute("PRAGMA user_version").fetchone()["user_version"]
                        if version > latest:
                            raise RuntimeError(
                                f"La base está en la versión {version} y este programa solo "
                                f"conoce hasta la {latest}: actualice el programa")
                        if number <= version:
                            conn.execute("ROLLBACK")
                            continue
                        with open(path, encoding="utf-8") as f:
                            for stmt in _statements(f.read()):
                                conn.execute(stmt)
                        conn.execute(f"PRAGMA user_version = {number}")
                        conn.execute("COMMIT")
                        print(f"[DB] Migración {os.path.basename(path)} aplicada")
                    except BaseException:
                        conn.execute("ROLLBACK")
                        raise
            finally:
                conn.isolation_level = previo
            DatabaseManager._schema_checked = True

    def is_connected(self) -> bool:
        if self.connection is None:
            return False
        try:
            self.connection.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False

    def disconnect(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    # ── helpers ───────────────────────────────────────────────────────────

    def _query(self, sql: str, params=(), one: bool = False):
        cur = self.connection.execute(sql, params)
        try:
            return cur.fetchone() if one else cur.fetchall()
        finally:
            cur.close()

    def _exec(self, sql: str, params=()) -> int:
        """Ejecuta INSERT/UPDATE/DELETE, confirma y retorna lastrowid."""
        try:
            cur = self.connection.execute(sql, params)
            self.connection.commit()
            return cur.lastrowid
        except sqlite3.Error:
            self.connection.rollback()
            raise

    def _transaction(self, statements):
        """Ejecuta [(sql, params), ...] de forma atómica."""
        try:
            for sql, params in statements:
                self.connection.execute(sql, params)
            self.connection.commit()
        except sqlite3.Error:
            self.connection.rollback()
            raise

    # ── réplicas de la nube: licencia y cuentas ───────────────────────────

    def guardar_licencia(self, contenido: str, firma: str):
        self._exec(f"""
            INSERT INTO licencia (idlicencia, contenido, firma, verificada_en)
            VALUES (1, ?, ?, {_NOW})
            ON CONFLICT (idlicencia) DO UPDATE SET contenido = excluded.contenido,
                firma = excluded.firma, verificada_en = excluded.verificada_en
        """, (contenido, firma))

    def get_licencia(self):
        return self._query("SELECT * FROM licencia WHERE idlicencia = 1", one=True)

    def sincronizar_cuentas(self, cuentas: list):
        """Reemplaza la réplica local por las cuentas vigentes en la nube."""
        ids = [c["idcuenta"] for c in cuentas] or [0]
        # primero se quitan las cuentas que ya no existen: así un correo que pasó a
        # otra cuenta no choca con la restricción UNIQUE al insertar
        stmts = [(f"DELETE FROM cuenta_local WHERE idcuenta NOT IN "
                  f"({', '.join(['?'] * len(ids))})", tuple(ids))]
        stmts += [(f"""
            INSERT INTO cuenta_local (idcuenta, rol, rut, nombres, apellidos, email,
                                      password_hash, debe_cambiar_password, activa,
                                      sincronizada_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, {_NOW})
            ON CONFLICT (idcuenta) DO UPDATE SET rol = excluded.rol, rut = excluded.rut,
                nombres = excluded.nombres, apellidos = excluded.apellidos,
                email = excluded.email, password_hash = excluded.password_hash,
                debe_cambiar_password = excluded.debe_cambiar_password,
                activa = excluded.activa, sincronizada_en = excluded.sincronizada_en
        """, (c["idcuenta"], c["rol"], c["rut"], c["nombres"], c["apellidos"], c["email"],
              c["password_hash"], bool(c.get("debe_cambiar_password")), bool(c["activa"])))
            for c in cuentas]
        self._transaction(stmts)

    def get_cuenta_local(self, email: str):
        return self._query("SELECT * FROM cuenta_local WHERE email = ?", (email,), one=True)

    # ── unidades ──────────────────────────────────────────────────────────

    def list_unidades(self):
        return self._query("SELECT * FROM unidad ORDER BY codigo COLLATE ES")

    def get_or_create_unidad(self, codigo: str) -> int:
        codigo = codigo.strip()
        row = self._query("SELECT idunidad FROM unidad WHERE codigo = ?", (codigo,), one=True)
        if row:
            return row["idunidad"]
        return self._exec("INSERT INTO unidad (codigo) VALUES (?)", (codigo,))

    # ── residentes ────────────────────────────────────────────────────────

    def list_tipos_residente(self):
        return self._query("SELECT * FROM tipo_residente ORDER BY idtipo_residente")

    def list_residentes(self):
        return self._query("""
            SELECT r.*, u.codigo AS unidad, t.nombre AS tipo,
                   (SELECT COUNT(*) FROM plantilla_facial p
                    WHERE p.idresidente = r.idresidente
                      AND p.modelo = ?) AS plantillas,
                   EXISTS (SELECT 1 FROM consentimiento c
                           WHERE c.idresidente = r.idresidente
                             AND c.fecha_revocacion IS NULL) AS consentimiento_vigente
            FROM residente r
            JOIN unidad u ON u.idunidad = r.idunidad
            JOIN tipo_residente t ON t.idtipo_residente = r.idtipo_residente
            ORDER BY u.codigo COLLATE ES, r.apellidos COLLATE ES
        """, (config.FACE_MODEL,))

    def find_residente_by_rut(self, rut: str):
        return self._query("SELECT * FROM residente WHERE rut = ?", (rut,), one=True)

    @_changes_data
    def create_residente(self, idunidad, idtipo, rut, nombres, apellidos,
                         fecha_nacimiento=None, telefono=None, email=None) -> int:
        return self._exec("""
            INSERT INTO residente (idunidad, idtipo_residente, rut, nombres, apellidos,
                                   fecha_nacimiento, telefono, email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (idunidad, idtipo, rut, nombres, apellidos, fecha_nacimiento, telefono, email))

    @_changes_data
    def update_residente(self, idresidente, idunidad, idtipo, nombres, apellidos,
                         fecha_nacimiento=None, telefono=None, email=None):
        """Rectificación de datos (art. 6)."""
        self._exec("""
            UPDATE residente SET idunidad = ?, idtipo_residente = ?, nombres = ?,
                   apellidos = ?, fecha_nacimiento = ?, telefono = ?, email = ?
            WHERE idresidente = ?
        """, (idunidad, idtipo, nombres, apellidos, fecha_nacimiento, telefono, email,
              idresidente))

    @_changes_data
    def delete_residente(self, idresidente: int):
        """Supresión (art. 7): borra datos, consentimientos y plantillas; anonimiza sus eventos."""
        self._exec("DELETE FROM residente WHERE idresidente = ?", (idresidente,))

    @_changes_data
    def set_bloqueo(self, idresidente: int, bloqueado: bool):
        self._exec("UPDATE residente SET tratamiento_bloqueado = ? WHERE idresidente = ?",
                   (bool(bloqueado), idresidente))

    # ── consentimiento y plantillas faciales ──────────────────────────────

    @_changes_data
    def registrar_consentimiento(self, idresidente, version, medio,
                                 idrepresentante=None, idcuenta=None) -> int:
        return self._exec("""
            INSERT INTO consentimiento (idresidente, idrepresentante, idcuenta_registro,
                                        version_formulario, medio)
            VALUES (?, ?, ?, ?, ?)
        """, (idresidente, idrepresentante, idcuenta, version, medio))

    def get_consentimiento_vigente(self, idresidente: int):
        return self._query("""
            SELECT * FROM consentimiento
            WHERE idresidente = ? AND fecha_revocacion IS NULL
            ORDER BY fecha_otorgamiento DESC LIMIT 1
        """, (idresidente,), one=True)

    @_changes_data
    def revocar_consentimiento(self, idresidente: int):
        """Revocación (art. 12): cierra el consentimiento y elimina las plantillas."""
        self._transaction([
            (f"""UPDATE consentimiento SET fecha_revocacion = {_NOW}
                 WHERE idresidente = ? AND fecha_revocacion IS NULL""", (idresidente,)),
            ("DELETE FROM plantilla_facial WHERE idresidente = ?", (idresidente,)),
        ])

    @_changes_data
    def add_plantilla(self, idresidente: int, embedding, modelo: str) -> int:
        # float32 crudo (.tobytes()): 4 bytes por componente, sin pickle
        blob = np.asarray(embedding, dtype=np.float32).tobytes()
        return self._exec("""
            INSERT INTO plantilla_facial (idresidente, embedding, modelo) VALUES (?, ?, ?)
        """, (idresidente, blob, modelo))

    def get_plantillas_activas(self, modelo: str = None) -> list:
        """Plantillas utilizables: consentimiento vigente y tratamiento no bloqueado.
        Solo las del modelo facial indicado (por defecto el vigente): vectores de
        modelos distintos no son comparables."""
        rows = self._query("""
            SELECT p.idplantilla, p.embedding, r.idresidente, r.nombres, r.apellidos,
                   u.codigo AS unidad
            FROM plantilla_facial p
            JOIN residente r ON r.idresidente = p.idresidente
            JOIN unidad u ON u.idunidad = r.idunidad
            WHERE r.tratamiento_bloqueado = 0
              AND p.modelo = ?
              AND EXISTS (SELECT 1 FROM consentimiento c
                          WHERE c.idresidente = r.idresidente
                            AND c.fecha_revocacion IS NULL)
        """, (modelo or config.FACE_MODEL,))
        for r in rows:
            r["embedding"] = np.frombuffer(r["embedding"], dtype=np.float32)
        return rows

    # ── vehículos ─────────────────────────────────────────────────────────

    def list_vehiculos(self):
        return self._query("""
            SELECT v.*, u.codigo AS unidad
            FROM vehiculo v JOIN unidad u ON u.idunidad = v.idunidad
            ORDER BY u.codigo COLLATE ES, v.patente
        """)

    @_changes_data
    def create_vehiculo(self, idunidad, patente, tipo="auto", marca=None,
                        modelo=None, color=None) -> int:
        return self._exec("""
            INSERT INTO vehiculo (idunidad, patente, tipo, marca, modelo, color)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (idunidad, clean_plate(patente), tipo, marca, modelo, color))

    @_changes_data
    def delete_vehiculo(self, idvehiculo: int):
        self._exec("DELETE FROM vehiculo WHERE idvehiculo = ?", (idvehiculo,))

    def get_patentes_autorizadas(self) -> dict:
        """{patente: {'idvehiculo', 'unidad'}} de vehículos de residentes."""
        rows = self._query("""
            SELECT v.idvehiculo, v.patente, u.codigo AS unidad
            FROM vehiculo v JOIN unidad u ON u.idunidad = v.idunidad
        """)
        return {r["patente"]: r for r in rows}

    # ── visitas ───────────────────────────────────────────────────────────

    @_changes_data
    def registrar_visita(self, rut, nombres, apellidos, idunidad,
                         patente=None, idcuenta=None) -> int:
        conn = self.connection
        try:
            conn.execute("""
                INSERT INTO visitante (rut, nombres, apellidos) VALUES (?, ?, ?)
                ON CONFLICT (rut) DO UPDATE SET nombres = excluded.nombres,
                                                apellidos = excluded.apellidos
            """, (rut, nombres, apellidos))
            idvisitante = conn.execute(
                "SELECT idvisitante FROM visitante WHERE rut = ?", (rut,)).fetchone()["idvisitante"]
            cur = conn.execute("""
                INSERT INTO visita (idvisitante, idunidad, idcuenta_registro, patente)
                VALUES (?, ?, ?, ?)
            """, (idvisitante, idunidad, idcuenta, clean_plate(patente) or None))
            idvisita = cur.lastrowid
            conn.commit()
            return idvisita
        except sqlite3.Error:
            conn.rollback()
            raise

    def list_visitas(self, solo_activas: bool = False, limit: int = 200):
        filtro = "WHERE v.fecha_salida IS NULL" if solo_activas else ""
        return self._query(f"""
            SELECT v.idvisita, v.patente, v.fecha_ingreso, v.fecha_salida,
                   vt.rut, vt.nombres, vt.apellidos, u.codigo AS unidad
            FROM visita v
            JOIN visitante vt ON vt.idvisitante = v.idvisitante
            JOIN unidad u ON u.idunidad = v.idunidad
            {filtro}
            ORDER BY v.fecha_ingreso DESC LIMIT ?
        """, (limit,))

    @_changes_data
    def marcar_salida(self, idvisita: int):
        self._exec(f"UPDATE visita SET fecha_salida = {_NOW} WHERE idvisita = ?", (idvisita,))

    def get_patentes_visitas_activas(self) -> dict:
        """{patente: {'idvisita', 'unidad'}} de visitas que no han salido y de visitas
        autorizadas para hoy (estas últimas sin idvisita hasta registrar su ingreso)."""
        rows = self._query(f"""
            SELECT NULL AS idvisita, a.patente, u.codigo AS unidad
            FROM visita_autorizada a JOIN unidad u ON u.idunidad = a.idunidad
            WHERE a.patente IS NOT NULL AND {self._VIGENTE}
        """) + self._query("""
            SELECT v.idvisita, v.patente, u.codigo AS unidad
            FROM visita v JOIN unidad u ON u.idunidad = v.idunidad
            WHERE v.fecha_salida IS NULL AND v.patente IS NOT NULL
        """)
        return {r["patente"]: r for r in rows}   # una visita ya ingresada prevalece

    # ── zonas y cámaras ───────────────────────────────────────────────────

    def list_zonas(self):
        return self._query("SELECT * FROM zona ORDER BY nombre COLLATE ES")

    def get_or_create_zona(self, nombre: str) -> int:
        nombre = nombre.strip()
        row = self._query("SELECT idzona FROM zona WHERE nombre = ?", (nombre,), one=True)
        if row:
            return row["idzona"]
        return self._exec("INSERT INTO zona (nombre) VALUES (?)", (nombre,))

    def list_camaras(self):
        return self._query("""
            SELECT c.*, z.nombre AS zona FROM camara c JOIN zona z ON z.idzona = c.idzona
            ORDER BY c.idcamara
        """)

    def create_camara(self, idzona, nombre, tipo_fuente, fuente, ancho, alto, fps, activa,
                      fuente_alta=None) -> int:
        return self._exec("""
            INSERT INTO camara (idzona, nombre, tipo_fuente, fuente, fuente_alta,
                                ancho, alto, fps, activa)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (idzona, nombre, tipo_fuente, str(fuente), fuente_alta or None,
              ancho, alto, fps, bool(activa)))

    def update_camara(self, idcamara, idzona, nombre, tipo_fuente, fuente, ancho, alto, fps, activa,
                      fuente_alta=None):
        self._exec("""
            UPDATE camara SET idzona = ?, nombre = ?, tipo_fuente = ?, fuente = ?,
                   fuente_alta = ?, ancho = ?, alto = ?, fps = ?, activa = ?
            WHERE idcamara = ?
        """, (idzona, nombre, tipo_fuente, str(fuente), fuente_alta or None,
              ancho, alto, fps, bool(activa), idcamara))

    def delete_camara(self, idcamara: int):
        self._exec("DELETE FROM camara WHERE idcamara = ?", (idcamara,))

    # ── detecciones ───────────────────────────────────────────────────────

    def add_deteccion_rostro(self, idcamara, resultado, confianza=None, idresidente=None,
                             idautorizacion=None):
        self._exec("""
            INSERT INTO deteccion_rostro (idcamara, idresidente, idautorizacion, resultado, confianza)
            VALUES (?, ?, ?, ?, ?)
        """, (idcamara, idresidente, idautorizacion, resultado,
              None if confianza is None else round(float(confianza), 4)))

    def add_deteccion_vehiculo(self, idcamara, patente, resultado, confianza=None,
                               idvehiculo=None, idvisita=None):
        self._exec("""
            INSERT INTO deteccion_vehiculo (idcamara, idvehiculo, idvisita, patente_leida,
                                            resultado, confianza)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (idcamara, idvehiculo, idvisita, clean_plate(patente), resultado,
              None if confianza is None else round(float(confianza), 4)))

    def list_detecciones_rostro(self, desde=None, hasta=None, limit=500):
        return self._query("""
            SELECT d.fecha_hora, d.resultado, d.confianza, c.nombre AS camara, z.nombre AS zona,
                   COALESCE(r.nombres || ' ' || r.apellidos,
                            'Visita: ' || vt.nombres || ' ' || vt.apellidos) AS persona,
                   COALESCE(u.codigo, ua.codigo) AS unidad
            FROM deteccion_rostro d
            JOIN camara c ON c.idcamara = d.idcamara
            JOIN zona z ON z.idzona = c.idzona
            LEFT JOIN residente r ON r.idresidente = d.idresidente
            LEFT JOIN unidad u ON u.idunidad = r.idunidad
            LEFT JOIN visita_autorizada a ON a.idautorizacion = d.idautorizacion
            LEFT JOIN visitante vt ON vt.idvisitante = a.idvisitante
            LEFT JOIN unidad ua ON ua.idunidad = a.idunidad
            WHERE (?1 IS NULL OR date(d.fecha_hora) >= ?1)
              AND (?2 IS NULL OR date(d.fecha_hora) <= ?2)
            ORDER BY d.iddeteccion DESC LIMIT ?3  -- orden de registro: no depende del reloj
        """, (_fecha(desde), _fecha(hasta), limit))

    def list_detecciones_vehiculo(self, desde=None, hasta=None, limit=500):
        return self._query("""
            SELECT d.fecha_hora, d.patente_leida, d.resultado, d.confianza,
                   c.nombre AS camara, z.nombre AS zona,
                   COALESCE(uv.codigo, uvi.codigo) AS unidad
            FROM deteccion_vehiculo d
            JOIN camara c ON c.idcamara = d.idcamara
            JOIN zona z ON z.idzona = c.idzona
            LEFT JOIN vehiculo v ON v.idvehiculo = d.idvehiculo
            LEFT JOIN unidad uv ON uv.idunidad = v.idunidad
            LEFT JOIN visita vi ON vi.idvisita = d.idvisita
            LEFT JOIN unidad uvi ON uvi.idunidad = vi.idunidad
            WHERE (?1 IS NULL OR date(d.fecha_hora) >= ?1)
              AND (?2 IS NULL OR date(d.fecha_hora) <= ?2)
            ORDER BY d.iddeteccion DESC LIMIT ?3
        """, (_fecha(desde), _fecha(hasta), limit))

    def historial_residente(self, idresidente: int):
        return self._query("""
            SELECT d.fecha_hora, d.resultado, d.confianza, c.nombre AS camara, z.nombre AS zona
            FROM deteccion_rostro d
            JOIN camara c ON c.idcamara = d.idcamara
            JOIN zona z ON z.idzona = c.idzona
            WHERE d.idresidente = ?
            ORDER BY d.iddeteccion DESC
        """, (idresidente,))

    def trafico_por_zona_hora(self, desde, hasta):
        """Eventos agrupados por zona y hora del día (RF-06)."""
        return self._query("""
            SELECT zona, hora, SUM(personas) AS personas, SUM(vehiculos) AS vehiculos
            FROM (
                SELECT z.nombre AS zona, CAST(strftime('%H', d.fecha_hora) AS INTEGER) AS hora,
                       1 AS personas, 0 AS vehiculos
                FROM deteccion_rostro d JOIN camara c ON c.idcamara = d.idcamara
                JOIN zona z ON z.idzona = c.idzona
                WHERE date(d.fecha_hora) BETWEEN ?1 AND ?2
                UNION ALL
                SELECT z.nombre, CAST(strftime('%H', d.fecha_hora) AS INTEGER), 0, 1
                FROM deteccion_vehiculo d JOIN camara c ON c.idcamara = d.idcamara
                JOIN zona z ON z.idzona = c.idzona
                WHERE date(d.fecha_hora) BETWEEN ?1 AND ?2
            ) t
            GROUP BY zona, hora
            ORDER BY zona COLLATE ES, hora
        """, (_fecha(desde), _fecha(hasta)))

    # ── derechos del titular ─────────────────────────────────────────────

    def list_solicitudes(self):
        return self._query("""
            SELECT s.*, r.nombres || ' ' || r.apellidos AS titular,
                   c.nombres || ' ' || c.apellidos AS gestionada_por
            FROM solicitud_derecho s
            LEFT JOIN residente r ON r.idresidente = s.idresidente
            LEFT JOIN cuenta_local c ON c.idcuenta = s.idcuenta_gestion
            ORDER BY s.estado = 'pendiente' DESC, s.fecha_solicitud DESC
        """)

    def create_solicitud(self, idresidente, rut_titular, tipo) -> int:
        return self._exec("""
            INSERT INTO solicitud_derecho (idresidente, rut_titular, tipo) VALUES (?, ?, ?)
        """, (idresidente, rut_titular, tipo))

    def cerrar_solicitud(self, idsolicitud, estado, observacion, idcuenta):
        self._exec(f"""
            UPDATE solicitud_derecho
            SET estado = ?, observacion = ?, idcuenta_gestion = ?, fecha_respuesta = {_NOW}
            WHERE idsolicitud = ?
        """, (estado, observacion, idcuenta, idsolicitud))

    def exportar_residente(self, idresidente: int) -> dict:
        """Datos del titular en formato estructurado (acceso y portabilidad, arts. 5 y 9)."""
        res = self._query("""
            SELECT r.rut, r.nombres, r.apellidos, r.fecha_nacimiento, r.telefono, r.email,
                   r.fecha_alta, r.tratamiento_bloqueado, u.codigo AS unidad,
                   t.nombre AS tipo_residente
            FROM residente r
            JOIN unidad u ON u.idunidad = r.idunidad
            JOIN tipo_residente t ON t.idtipo_residente = r.idtipo_residente
            WHERE r.idresidente = ?
        """, (idresidente,), one=True)
        if not res:
            return {}
        return {
            "titular": res,
            "consentimientos": self._query("""
                SELECT version_formulario, medio, fecha_otorgamiento, fecha_revocacion
                FROM consentimiento WHERE idresidente = ?
            """, (idresidente,)),
            "plantillas_faciales": self._query("""
                SELECT modelo, fecha_captura FROM plantilla_facial WHERE idresidente = ?
            """, (idresidente,)),
            "vehiculos_de_la_unidad": self._query("""
                SELECT v.patente, v.tipo, v.marca, v.modelo, v.color
                FROM vehiculo v JOIN residente r ON r.idunidad = v.idunidad
                WHERE r.idresidente = ?
            """, (idresidente,)),
            "registros_de_acceso": self.historial_residente(idresidente),
            "finalidad": "Control de acceso del condominio (Ley 19.628 art. 3 b)",
        }

    # ── retención (art. 3 c) ──────────────────────────────────────────────

    @_changes_data
    def purgar_datos_vencidos(self, dias_detecciones: int, dias_visitas: int) -> dict:
        """Elimina eventos y visitas más antiguos que el plazo de la política de retención."""
        conn = self.connection
        out = {}
        limite = "datetime('now', 'localtime', '-' || ? || ' days')"
        try:
            for key, sql, dias in [
                ("detecciones_rostro",
                 f"DELETE FROM deteccion_rostro WHERE fecha_hora < {limite}", dias_detecciones),
                ("detecciones_vehiculo",
                 f"DELETE FROM deteccion_vehiculo WHERE fecha_hora < {limite}", dias_detecciones),
                ("visitas",
                 f"DELETE FROM visita WHERE fecha_ingreso < {limite}", dias_visitas),
            ]:
                out[key] = conn.execute(sql, (int(dias),)).rowcount
            # sin visitas ni autorizaciones vigentes (no se borra a las visitas frecuentes)
            out["visitantes"] = conn.execute("""
                DELETE FROM visitante
                WHERE NOT EXISTS (SELECT 1 FROM visita v WHERE v.idvisitante = visitante.idvisitante)
                  AND NOT EXISTS (SELECT 1 FROM visita_autorizada a
                                  WHERE a.idvisitante = visitante.idvisitante)
            """).rowcount
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        return out

    # ── registro desde el celular (portal local) ──────────────────────────

    def crear_invitacion(self, tipo, idunidad, horas, idcuenta=None, idresidente=None,
                         frecuente=False) -> tuple:
        """Invitación de un solo uso. Retorna (idinvitacion, token); del token
        (que va en el enlace) solo se guarda su hash."""
        token = secrets.token_urlsafe(16)
        idinv = self._exec(f"""
            INSERT INTO invitacion (token_hash, tipo, idunidad, idresidente, idcuenta_creacion,
                                    vence, frecuente)
            VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime', '+' || ? || ' hours'), ?)
        """, (_hash_token(token), tipo, idunidad, idresidente, idcuenta, int(horas),
              bool(frecuente)))
        return idinv, token

    def get_invitacion(self, idinvitacion):
        return self._query("SELECT * FROM invitacion WHERE idinvitacion = ?", (idinvitacion,),
                           one=True)

    def anular_invitacion(self, idinvitacion):
        self._exec("DELETE FROM invitacion WHERE idinvitacion = ?", (idinvitacion,))

    def invitacion_por_token(self, token: str):
        """Invitación con su unidad, residente (si es solo captura de rostro) y
        solicitud asociada; 'vigente' indica si aún puede usarse."""
        return self._query(f"""
            SELECT i.*, u.codigo AS unidad,
                   r.nombres || ' ' || r.apellidos AS residente,
                   s.idsolicitud, s.estado AS estado_solicitud,
                   (i.usada IS NULL AND i.vence > {_NOW}) AS vigente
            FROM invitacion i
            JOIN unidad u ON u.idunidad = i.idunidad
            LEFT JOIN residente r ON r.idresidente = i.idresidente
            LEFT JOIN solicitud_registro s ON s.idinvitacion = i.idinvitacion
            WHERE i.token_hash = ?
        """, (_hash_token(token),), one=True)

    def guardar_solicitud(self, idinvitacion, tipo, datos: dict, consentimiento_version=None,
                          consentimiento_fecha=None) -> int:
        """Crea o reemplaza la solicitud (aún incompleta) de una invitación.
        consentimiento_fecha: cuando se aceptó en el celular (hora local)."""
        self._exec("""
            INSERT INTO solicitud_registro (idinvitacion, tipo, datos, consentimiento_version,
                                            consentimiento_fecha)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (idinvitacion) DO UPDATE SET datos = excluded.datos,
                consentimiento_version = excluded.consentimiento_version,
                consentimiento_fecha = excluded.consentimiento_fecha
            WHERE solicitud_registro.estado = 'incompleta'
        """, (idinvitacion, tipo, json.dumps(datos, ensure_ascii=False), consentimiento_version,
              consentimiento_fecha))
        return self._query("SELECT idsolicitud FROM solicitud_registro WHERE idinvitacion = ?",
                           (idinvitacion,), one=True)["idsolicitud"]

    def solicitud_plantillas(self, idsolicitud) -> list:
        rows = self._query("SELECT embedding FROM solicitud_plantilla WHERE idsolicitud = ? "
                           "ORDER BY idsolplantilla", (idsolicitud,))
        return [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]

    def add_solicitud_plantilla(self, idsolicitud, embedding, modelo) -> int:
        self._exec("INSERT INTO solicitud_plantilla (idsolicitud, embedding, modelo) VALUES (?, ?, ?)",
                   (idsolicitud, np.asarray(embedding, dtype=np.float32).tobytes(), modelo))
        return self._query("SELECT COUNT(*) AS n FROM solicitud_plantilla WHERE idsolicitud = ?",
                           (idsolicitud,), one=True)["n"]

    @_changes_data
    def completar_solicitud(self, idsolicitud):
        """El formulario quedó completo: pasa a revisión y la invitación se consume."""
        self._transaction([
            (f"""UPDATE solicitud_registro SET estado = 'pendiente', fecha_envio = {_NOW}
                 WHERE idsolicitud = ? AND estado = 'incompleta'""", (idsolicitud,)),
            (f"""UPDATE invitacion SET usada = {_NOW} WHERE idinvitacion =
                 (SELECT idinvitacion FROM solicitud_registro WHERE idsolicitud = ?)""",
             (idsolicitud,)),
        ])

    def list_solicitudes_registro(self, estado: str = "pendiente") -> list:
        rows = self._query("""
            SELECT s.*, i.idunidad, i.idresidente, i.frecuente, u.codigo AS unidad,
                   r.nombres || ' ' || r.apellidos AS residente_existente,
                   (SELECT COUNT(*) FROM solicitud_plantilla p
                    WHERE p.idsolicitud = s.idsolicitud) AS fotos
            FROM solicitud_registro s
            JOIN invitacion i ON i.idinvitacion = s.idinvitacion
            JOIN unidad u ON u.idunidad = i.idunidad
            LEFT JOIN residente r ON r.idresidente = i.idresidente
            WHERE s.estado = ?
            ORDER BY s.fecha_envio
        """, (estado,))
        for r in rows:
            r["datos"] = json.loads(r["datos"] or "{}")
        return rows

    def _cerrar_solicitud(self, conn, idsolicitud, estado, idcuenta, observacion=None):
        # minimización: los datos ya quedaron en sus tablas (o se descartan)
        conn.execute(f"""
            UPDATE solicitud_registro SET estado = ?, datos = '{{}}', fecha_revision = {_NOW},
                   idcuenta_revision = ?, observacion = ?
            WHERE idsolicitud = ?
        """, (estado, idcuenta, observacion, idsolicitud))
        conn.execute("DELETE FROM solicitud_plantilla WHERE idsolicitud = ?", (idsolicitud,))

    @_changes_data
    def rechazar_solicitud(self, idsolicitud, idcuenta=None, observacion=None):
        conn = self.connection
        try:
            self._cerrar_solicitud(conn, idsolicitud, "rechazada", idcuenta, observacion)
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise

    @_changes_data
    def aprobar_solicitud_residente(self, idsolicitud, idcuenta=None) -> int:
        """Crea el residente (o usa el existente), su consentimiento digital, sus
        plantillas faciales y su vehículo, en una sola transacción. Retorna idresidente.
        Lanza ValueError con un mensaje para la administración si algo no cuadra."""
        conn = self.connection
        s = conn.execute("""
            SELECT s.*, i.idunidad, i.idresidente FROM solicitud_registro s
            JOIN invitacion i ON i.idinvitacion = s.idinvitacion
            WHERE s.idsolicitud = ? AND s.estado = 'pendiente' AND s.tipo = 'residente'
        """, (idsolicitud,)).fetchone()
        if not s:
            raise ValueError("La solicitud ya no está pendiente")
        d = json.loads(s["datos"])
        plantillas = conn.execute("SELECT embedding, modelo FROM solicitud_plantilla "
                                  "WHERE idsolicitud = ?", (idsolicitud,)).fetchall()
        try:
            if s["idresidente"]:
                idres = s["idresidente"]
            else:
                if conn.execute("SELECT 1 FROM residente WHERE rut = ?", (d["rut"],)).fetchone():
                    raise ValueError(f"Ya existe un residente con RUT {d['rut']}. Rechace la "
                                     "solicitud o genere una invitación «solo rostro» para él.")
                idres = conn.execute("""
                    INSERT INTO residente (idunidad, idtipo_residente, rut, nombres, apellidos,
                                           fecha_nacimiento, telefono, email)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (s["idunidad"], d["idtipo_residente"], d["rut"], d["nombres"], d["apellidos"],
                      d.get("fecha_nacimiento"), d.get("telefono"), d.get("email"))).lastrowid
            if plantillas:
                # consentimiento otorgado en el celular, con la fecha en que se aceptó
                conn.execute("""
                    INSERT INTO consentimiento (idresidente, idcuenta_registro, version_formulario,
                                                medio, fecha_otorgamiento)
                    VALUES (?, ?, ?, 'digital', ?)
                """, (idres, idcuenta, s["consentimiento_version"], s["consentimiento_fecha"]))
                for p in plantillas:
                    conn.execute("INSERT INTO plantilla_facial (idresidente, embedding, modelo) "
                                 "VALUES (?, ?, ?)", (idres, p["embedding"], p["modelo"]))
            veh = d.get("vehiculo")
            if veh and not conn.execute("SELECT 1 FROM vehiculo WHERE patente = ?",
                                        (veh["patente"],)).fetchone():
                conn.execute("""
                    INSERT INTO vehiculo (idunidad, patente, tipo, marca, modelo, color)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (s["idunidad"], veh["patente"], veh.get("tipo", "auto"), veh.get("marca"),
                      veh.get("modelo"), veh.get("color")))
            self._cerrar_solicitud(conn, idsolicitud, "aprobada", idcuenta)
            conn.commit()
            return idres
        except BaseException:
            conn.rollback()
            raise

    @_changes_data
    def aprobar_solicitud_visita(self, idsolicitud, idcuenta=None) -> int:
        """Autoriza a la visita (con su rostro, si lo registró): ocasional para la
        fecha indicada, o frecuente sin término. El ingreso se registra cuando llega.
        Retorna idautorizacion."""
        conn = self.connection
        s = conn.execute("""
            SELECT s.*, i.idunidad, i.frecuente FROM solicitud_registro s
            JOIN invitacion i ON i.idinvitacion = s.idinvitacion
            WHERE s.idsolicitud = ? AND s.estado = 'pendiente' AND s.tipo = 'visita'
        """, (idsolicitud,)).fetchone()
        if not s:
            raise ValueError("La solicitud ya no está pendiente")
        d = json.loads(s["datos"])
        hoy = date.today().isoformat()
        desde = hoy if s["frecuente"] else (d.get("fecha_visita") or hoy)
        hasta = None if s["frecuente"] else desde
        try:
            conn.execute("""
                INSERT INTO visitante (rut, nombres, apellidos) VALUES (?, ?, ?)
                ON CONFLICT (rut) DO UPDATE SET nombres = excluded.nombres,
                                                apellidos = excluded.apellidos
            """, (d["rut"], d["nombres"], d["apellidos"]))
            idvisitante = conn.execute("SELECT idvisitante FROM visitante WHERE rut = ?",
                                       (d["rut"],)).fetchone()["idvisitante"]
            plantillas = conn.execute("SELECT embedding, modelo FROM solicitud_plantilla "
                                      "WHERE idsolicitud = ?", (idsolicitud,)).fetchall()
            idaut = conn.execute("""
                INSERT INTO visita_autorizada (idvisitante, idunidad, frecuente, fecha_desde,
                    fecha_hasta, patente, consentimiento_version, consentimiento_fecha,
                    idcuenta_aprobacion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (idvisitante, s["idunidad"], s["frecuente"], desde, hasta, d.get("patente"),
                  s["consentimiento_version"] if plantillas else None,
                  s["consentimiento_fecha"] if plantillas else None, idcuenta)).lastrowid
            for p in plantillas:
                conn.execute("INSERT INTO plantilla_visita (idautorizacion, embedding, modelo) "
                             "VALUES (?, ?, ?)", (idaut, p["embedding"], p["modelo"]))
            self._cerrar_solicitud(conn, idsolicitud, "aprobada", idcuenta)
            conn.commit()
            return idaut
        except BaseException:
            conn.rollback()
            raise

    # ── visitas autorizadas ───────────────────────────────────────────────

    _VIGENTE = ("a.fecha_desde <= date('now', 'localtime') AND "
                "(a.fecha_hasta IS NULL OR a.fecha_hasta >= date('now', 'localtime'))")

    def list_autorizaciones_visita(self) -> list:
        """Autorizaciones vigentes o futuras (las ocasionales vencidas se purgan)."""
        return self._query("""
            SELECT a.*, v.rut, v.nombres, v.apellidos, u.codigo AS unidad,
                   (SELECT COUNT(*) FROM plantilla_visita p
                    WHERE p.idautorizacion = a.idautorizacion) AS plantillas
            FROM visita_autorizada a
            JOIN visitante v ON v.idvisitante = a.idvisitante
            JOIN unidad u ON u.idunidad = a.idunidad
            WHERE a.fecha_hasta IS NULL OR a.fecha_hasta >= date('now', 'localtime')
            ORDER BY a.frecuente DESC, a.fecha_desde, v.apellidos COLLATE ES
        """)

    def get_autorizacion_visita(self, idautorizacion):
        return self._query("""
            SELECT a.*, v.rut, v.nombres, v.apellidos FROM visita_autorizada a
            JOIN visitante v ON v.idvisitante = a.idvisitante WHERE a.idautorizacion = ?
        """, (idautorizacion,), one=True)

    @_changes_data
    def revocar_autorizacion_visita(self, idautorizacion):
        """Elimina la autorización y sus vectores (revocación o fin de la frecuencia)."""
        self._exec("DELETE FROM visita_autorizada WHERE idautorizacion = ?", (idautorizacion,))

    def get_plantillas_visita_vigentes(self, modelo: str = None) -> list:
        """Vectores de las visitas autorizadas para hoy (ocasionales del día y frecuentes)."""
        rows = self._query(f"""
            SELECT p.embedding, a.idautorizacion, v.nombres, v.apellidos, u.codigo AS unidad
            FROM plantilla_visita p
            JOIN visita_autorizada a ON a.idautorizacion = p.idautorizacion
            JOIN visitante v ON v.idvisitante = a.idvisitante
            JOIN unidad u ON u.idunidad = a.idunidad
            WHERE p.modelo = ? AND {self._VIGENTE}
        """, (modelo or config.FACE_MODEL,))
        for r in rows:
            r["embedding"] = np.frombuffer(r["embedding"], dtype=np.float32)
        return rows

    @_changes_data
    def purgar_autorizaciones_vencidas(self) -> int:
        """Visitas ocasionales: al día siguiente de la visita se borran con sus vectores."""
        cur = self.connection.execute(
            "DELETE FROM visita_autorizada WHERE fecha_hasta < date('now', 'localtime')")
        self.connection.commit()
        return cur.rowcount

    def purgar_registros_moviles(self, dias: int) -> int:
        """Invitaciones vencidas sin usar y solicitudes no resueltas más antiguas que
        `dias` se eliminan con sus datos y vectores (minimización)."""
        conn = self.connection
        try:
            n = conn.execute(f"""
                DELETE FROM invitacion WHERE usada IS NULL AND vence < {_NOW}
            """).rowcount
            n += conn.execute(f"""
                DELETE FROM invitacion WHERE idinvitacion IN (
                    SELECT idinvitacion FROM solicitud_registro
                    WHERE estado IN ('incompleta', 'pendiente')
                      AND COALESCE(fecha_envio, consentimiento_fecha, '0') <
                          datetime('now', 'localtime', '-' || ? || ' days'))
            """, (int(dias),)).rowcount
            conn.commit()
            return n
        except sqlite3.Error:
            conn.rollback()
            raise

    # ── estadísticas ──────────────────────────────────────────────────────

    def get_statistics(self) -> dict:
        return self._query("""
            SELECT
              (SELECT COUNT(*) FROM residente) AS residentes,
              (SELECT COUNT(DISTINCT idresidente) FROM plantilla_facial) AS con_rostro,
              (SELECT COUNT(*) FROM vehiculo) AS vehiculos,
              (SELECT COUNT(*) FROM visita WHERE fecha_salida IS NULL) AS visitas_activas,
              (SELECT COUNT(*) FROM deteccion_rostro
               WHERE date(fecha_hora) = date('now', 'localtime')) AS rostros_hoy,
              (SELECT COUNT(*) FROM deteccion_vehiculo
               WHERE date(fecha_hora) = date('now', 'localtime')) AS vehiculos_hoy,
              (SELECT COUNT(*) FROM solicitud_derecho
               WHERE estado = 'pendiente') AS solicitudes_pendientes
        """, one=True) or {}
