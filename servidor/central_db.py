# -*- coding: utf-8 -*-
"""
servidor/central_db.py - Acceso a la base central (umbral_central).
Solo lo usa la API; los condominios nunca se conectan a esta base.
"""

import mysql.connector

from servidor import config_servidor as cfg
from core.security import hash_password


class CentralDB:
    """Una conexión por petición HTTP (se usa con 'with')."""

    def __enter__(self):
        self.conn = mysql.connector.connect(charset="utf8mb4", collation="utf8mb4_spanish_ci",
                                            autocommit=False, **cfg.CENTRAL_DB)
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

    def _q(self, sql, params=(), one=False):
        cur = self.conn.cursor(dictionary=True)
        try:
            cur.execute(sql, params)
            return cur.fetchone() if one else cur.fetchall()
        finally:
            cur.close()

    def _x(self, sql, params=()) -> int:
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params)
            return cur.lastrowid
        finally:
            cur.close()

    # ── esquema ───────────────────────────────────────────────────────────

    # (tabla, columna, definición) agregadas después de la primera versión de central.sql
    _COLUMNAS_NUEVAS = [
        ("cuenta", "debe_cambiar_password",
         "BOOLEAN NOT NULL DEFAULT FALSE "
         "COMMENT 'Contraseña temporal: se exige cambiarla al iniciar sesión' AFTER password_hash"),
        ("pago", "fecha_fin_anterior",
         "DATE NULL COMMENT 'Vigencia antes del pago: se restaura si se anula'"),
        ("pago", "anulado", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("pago", "fecha_anulacion", "DATETIME NULL"),
        ("pago", "motivo_anulacion", "VARCHAR(200) NULL"),
        ("nodo", "clave_registro",
         "TEXT NULL COMMENT 'Clave pública X25519 para cifrar los registros móviles'"),
        ("invitacion_registro", "frecuente", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("invitacion_registro", "rostro", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ]

    # tablas agregadas después (mismo texto que en sql/central.sql)
    _TABLAS_NUEVAS = {
        "invitacion_registro": """
            CREATE TABLE invitacion_registro (
                idinvitacion INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                idnodo INT UNSIGNED NOT NULL,
                token_hash CHAR(64) NOT NULL UNIQUE,
                tipo ENUM('residente','visita') NOT NULL,
                id_local INT UNSIGNED NOT NULL,
                unidad VARCHAR(20) NOT NULL,
                solo_rostro BOOLEAN NOT NULL DEFAULT FALSE,
                frecuente BOOLEAN NOT NULL DEFAULT FALSE,
                rostro BOOLEAN NOT NULL DEFAULT TRUE,
                consentimiento_version VARCHAR(20) NOT NULL,
                creada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                vence DATETIME NOT NULL,
                usada DATETIME NULL,
                CONSTRAINT fk_invreg_nodo FOREIGN KEY (idnodo) REFERENCES nodo (idnodo)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB""",
        "envio_registro": """
            CREATE TABLE envio_registro (
                idenvio INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                idinvitacion INT UNSIGNED NOT NULL UNIQUE,
                paquete MEDIUMTEXT NOT NULL,
                creado DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_envio_inv FOREIGN KEY (idinvitacion)
                    REFERENCES invitacion_registro (idinvitacion) ON DELETE CASCADE
            ) ENGINE=InnoDB""",
    }

    def asegurar_esquema(self):
        """Cambios aditivos para bases creadas con versiones anteriores de
        sql/central.sql (se aplica una vez al iniciar la API)."""
        existentes = {(r["TABLE_NAME"], r["COLUMN_NAME"]) for r in self._q("""
            SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
        """)}
        tablas = {t for t, _ in existentes}
        for tabla, columna, definicion in self._COLUMNAS_NUEVAS:
            # una tabla que aún no existe se crea abajo ya con todas sus columnas
            if tabla in tablas and (tabla, columna) not in existentes:
                self._x(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
                print(f"[CentralDB] Columna {tabla}.{columna} agregada")
        for tabla, ddl in self._TABLAS_NUEVAS.items():   # en orden: la segunda depende de la primera
            if tabla not in tablas:
                self._x(ddl)
                print(f"[CentralDB] Tabla {tabla} creada")

    # ── registro desde el celular ─────────────────────────────────────────

    def guardar_clave_registro(self, idnodo, publica_pem):
        self._x("UPDATE nodo SET clave_registro = %s WHERE idnodo = %s", (publica_pem, idnodo))

    def crear_invitacion_registro(self, idnodo, token_hash, tipo, id_local, unidad, solo_rostro,
                                  consentimiento_version, horas, frecuente=False,
                                  rostro=True) -> int:
        return self._x("""
            INSERT INTO invitacion_registro (idnodo, token_hash, tipo, id_local, unidad, solo_rostro,
                                             frecuente, rostro, consentimiento_version, vence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, DATE_ADD(NOW(), INTERVAL %s HOUR))
        """, (idnodo, token_hash, tipo, id_local, unidad, solo_rostro, frecuente, rostro,
              consentimiento_version, horas))

    def invitacion_registro(self, token_hash):
        """Invitación con la clave pública del nodo y si sigue vigente."""
        return self._q("""
            SELECT i.*, n.clave_registro, n.activo AS nodo_activo, c.nombre AS condominio,
                   (i.usada IS NULL AND i.vence > NOW()) AS vigente
            FROM invitacion_registro i
            JOIN nodo n ON n.idnodo = i.idnodo
            JOIN condominio c ON c.idcondominio = n.idcondominio
            WHERE i.token_hash = %s
        """, (token_hash,), one=True)

    def guardar_envio_registro(self, idinvitacion, paquete):
        """Guarda el registro cifrado y consume la invitación (atómico: misma conexión)."""
        self._x("INSERT INTO envio_registro (idinvitacion, paquete) VALUES (%s, %s)",
                (idinvitacion, paquete))
        self._x("UPDATE invitacion_registro SET usada = NOW() WHERE idinvitacion = %s",
                (idinvitacion,))

    def envios_pendientes(self, idnodo):
        return self._q("""
            SELECT e.idenvio, e.paquete, i.id_local, i.tipo
            FROM envio_registro e JOIN invitacion_registro i ON i.idinvitacion = e.idinvitacion
            WHERE i.idnodo = %s ORDER BY e.idenvio
        """, (idnodo,))

    def borrar_envio(self, idnodo, idenvio) -> bool:
        """El nodo confirmó la recepción: el paquete se elimina de la nube."""
        cur = self.conn.cursor()
        try:
            cur.execute("""
                DELETE e FROM envio_registro e
                JOIN invitacion_registro i ON i.idinvitacion = e.idinvitacion
                WHERE e.idenvio = %s AND i.idnodo = %s
            """, (idenvio, idnodo))
            return cur.rowcount > 0
        finally:
            cur.close()

    def purgar_invitaciones_registro(self):
        """Invitaciones vencidas sin uso (y las usadas de más de 30 días) se eliminan."""
        self._x("""DELETE FROM invitacion_registro
                   WHERE (usada IS NULL AND vence < NOW() - INTERVAL 1 DAY)
                      OR usada < NOW() - INTERVAL 30 DAY""")

    # ── cuentas ───────────────────────────────────────────────────────────

    def cuenta_por_email(self, email):
        return self._q("""
            SELECT c.*, r.nombre AS rol FROM cuenta c JOIN rol r ON r.idrol = c.idrol
            WHERE c.email = %s
        """, (email,), one=True)

    def cuenta_por_id(self, idcuenta):
        return self._q("""
            SELECT c.*, r.nombre AS rol FROM cuenta c JOIN rol r ON r.idrol = c.idrol
            WHERE c.idcuenta = %s
        """, (idcuenta,), one=True)

    def registrar_acceso(self, idcuenta):
        self._x("UPDATE cuenta SET ultimo_acceso = NOW() WHERE idcuenta = %s", (idcuenta,))

    def cuentas_condominio(self, idcondominio):
        return self._q("""
            SELECT c.idcuenta, c.rut, c.nombres, c.apellidos, c.email, c.password_hash,
                   c.debe_cambiar_password, c.activa, c.ultimo_acceso, r.nombre AS rol
            FROM cuenta c JOIN rol r ON r.idrol = c.idrol
            WHERE c.idcondominio = %s ORDER BY r.idrol, c.apellidos
        """, (idcondominio,))

    def crear_cuenta(self, idcondominio, rol, rut, nombres, apellidos, email, password,
                     temporal: bool = False) -> int:
        """temporal=True: quien la creó conoce la contraseña; se cambia al primer ingreso."""
        return self._x("""
            INSERT INTO cuenta (idcondominio, idrol, rut, nombres, apellidos, email, password_hash,
                                debe_cambiar_password)
            VALUES (%s, (SELECT idrol FROM rol WHERE nombre = %s), %s, %s, %s, %s, %s, %s)
        """, (idcondominio, rol, rut, nombres, apellidos, email.lower(), hash_password(password),
              temporal))

    def activar_cuenta(self, idcuenta, activa):
        self._x("UPDATE cuenta SET activa = %s WHERE idcuenta = %s", (activa, idcuenta))

    def cambiar_password(self, idcuenta, password, temporal: bool = False):
        """temporal=True: la cuenta deberá cambiarla al iniciar sesión."""
        self._x("UPDATE cuenta SET password_hash = %s, debe_cambiar_password = %s "
                "WHERE idcuenta = %s", (hash_password(password), temporal, idcuenta))

    # ── nodos ─────────────────────────────────────────────────────────────

    def nodo_por_clave_hash(self, clave_hash):
        return self._q("SELECT * FROM nodo WHERE clave_hash = %s AND activo", (clave_hash,),
                       one=True)

    def registrar_contacto_nodo(self, idnodo):
        self._x("UPDATE nodo SET ultimo_contacto = NOW() WHERE idnodo = %s", (idnodo,))

    def reemplazar_nodo(self, idcondominio, nombre, clave_hash) -> int:
        """Desactiva los nodos anteriores del condominio y registra uno nuevo."""
        self._x("UPDATE nodo SET activo = FALSE WHERE idcondominio = %s", (idcondominio,))
        return self._x("INSERT INTO nodo (idcondominio, nombre, clave_hash) VALUES (%s, %s, %s)",
                       (idcondominio, nombre, clave_hash))

    # ── suscripciones ─────────────────────────────────────────────────────

    def suscripcion_vigente(self, idcondominio):
        return self._q("""
            SELECT s.*, p.nombre AS plan, p.max_camaras, c.nombre AS condominio
            FROM suscripcion s
            JOIN plan p ON p.idplan = s.idplan
            JOIN condominio c ON c.idcondominio = s.idcondominio
            WHERE s.idcondominio = %s ORDER BY s.fecha_fin DESC LIMIT 1
        """, (idcondominio,), one=True)

    # ── planes ────────────────────────────────────────────────────────────

    def planes(self, todos: bool = False):
        """Planes ofrecidos (todos=True incluye los desactivados), con cuántas
        suscripciones no canceladas usan cada uno."""
        return self._q(f"""
            SELECT p.*, (SELECT COUNT(*) FROM suscripcion s
                         WHERE s.idplan = p.idplan AND s.estado <> 'cancelada') AS suscripciones
            FROM plan p {'' if todos else 'WHERE p.activo'}
            ORDER BY p.precio_mensual
        """)

    def plan(self, idplan):
        return self._q("SELECT * FROM plan WHERE idplan = %s", (idplan,), one=True)

    def crear_plan(self, nombre, precio_mensual, max_camaras) -> int:
        return self._x("INSERT INTO plan (nombre, precio_mensual, max_camaras) VALUES (%s, %s, %s)",
                       (nombre, precio_mensual, max_camaras))

    def actualizar_plan(self, idplan, nombre, precio_mensual, max_camaras, activo):
        """Un precio nuevo rige para los pagos que se registren desde ahora; los ya
        registrados conservan el monto que se cobró."""
        self._x("""UPDATE plan SET nombre = %s, precio_mensual = %s, max_camaras = %s, activo = %s
                   WHERE idplan = %s""", (nombre, precio_mensual, max_camaras, activo, idplan))

    def cambiar_plan(self, idsuscripcion, idplan):
        self._x("UPDATE suscripcion SET idplan = %s WHERE idsuscripcion = %s",
                (idplan, idsuscripcion))

    def condominios(self):
        return self._q("""
            SELECT c.idcondominio, c.rut, c.nombre, c.comuna, c.email_contacto,
                   s.idsuscripcion, s.idplan, s.fecha_fin, s.estado, p.nombre AS plan,
                   p.precio_mensual, p.max_camaras,
                   (SELECT MAX(n.ultimo_contacto) FROM nodo n
                    WHERE n.idcondominio = c.idcondominio AND n.activo) AS ultimo_contacto
            FROM condominio c
            LEFT JOIN suscripcion s ON s.idsuscripcion = (
                SELECT s2.idsuscripcion FROM suscripcion s2
                WHERE s2.idcondominio = c.idcondominio ORDER BY s2.fecha_fin DESC LIMIT 1)
            LEFT JOIN plan p ON p.idplan = s.idplan
            ORDER BY c.nombre
        """)

    def crear_condominio(self, rut, nombre, direccion, comuna, email, telefono) -> int:
        return self._x("""
            INSERT INTO condominio (rut, nombre, direccion, comuna, email_contacto, telefono)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (rut, nombre, direccion, comuna, email, telefono))

    def crear_suscripcion(self, idcondominio, idplan, dias) -> int:
        return self._x("""
            INSERT INTO suscripcion (idcondominio, idplan, fecha_inicio, fecha_fin)
            VALUES (%s, %s, CURDATE(), DATE_ADD(CURDATE(), INTERVAL %s DAY))
        """, (idcondominio, idplan, dias))

    def registrar_pago(self, idsuscripcion, meses, referencia, medio="transferencia"):
        susc = self._q("""SELECT p.precio_mensual, s.fecha_fin FROM suscripcion s
                          JOIN plan p ON p.idplan = s.idplan WHERE s.idsuscripcion = %s""",
                       (idsuscripcion,), one=True)
        if not susc:
            return False
        # el monto queda fijo con el precio de hoy, aunque el plan cambie después;
        # la vigencia anterior se guarda para poder restaurarla si se anula el pago
        self._x("""
            INSERT INTO pago (idsuscripcion, fecha_pago, monto, meses, medio, referencia,
                              fecha_fin_anterior)
            VALUES (%s, CURDATE(), %s, %s, %s, %s, %s)
        """, (idsuscripcion, susc["precio_mensual"] * meses, meses, medio, referencia,
              susc["fecha_fin"]))
        self._x("""
            UPDATE suscripcion
            SET fecha_fin = DATE_ADD(GREATEST(fecha_fin, CURDATE()), INTERVAL %s MONTH),
                estado = 'activa'
            WHERE idsuscripcion = %s
        """, (meses, idsuscripcion))
        return True

    def pagos_condominio(self, idcondominio):
        return self._q("""
            SELECT pg.idpago, pg.idsuscripcion, pg.fecha_pago, pg.monto, pg.meses, pg.medio,
                   pg.referencia, pg.anulado, pg.fecha_anulacion, pg.motivo_anulacion,
                   p.nombre AS plan
            FROM pago pg
            JOIN suscripcion s ON s.idsuscripcion = pg.idsuscripcion
            JOIN plan p ON p.idplan = s.idplan
            WHERE s.idcondominio = %s
            ORDER BY pg.idpago DESC
        """, (idcondominio,))

    def anular_pago(self, idpago, motivo):
        """Anula un pago mal registrado y devuelve la suscripción a la vigencia que
        tenía antes. Solo el último pago vigente de la suscripción, para que la
        vigencia restaurada sea exacta. Retorna un mensaje de error o None."""
        pago = self._q("""SELECT pg.*, s.fecha_fin FROM pago pg
                          JOIN suscripcion s ON s.idsuscripcion = pg.idsuscripcion
                          WHERE pg.idpago = %s""", (idpago,), one=True)
        if not pago:
            return "Pago no encontrado"
        if pago["anulado"]:
            return "El pago ya estaba anulado"
        ultimo = self._q("""SELECT MAX(idpago) AS id FROM pago
                            WHERE idsuscripcion = %s AND NOT anulado""",
                         (pago["idsuscripcion"],), one=True)["id"]
        if ultimo != idpago:
            return ("Solo se puede anular el último pago vigente de la suscripción. "
                    "Anule primero los pagos posteriores.")
        if pago["fecha_fin_anterior"] is not None:
            self._x("UPDATE suscripcion SET fecha_fin = %s WHERE idsuscripcion = %s",
                    (pago["fecha_fin_anterior"], pago["idsuscripcion"]))
        else:   # pagos registrados antes de guardar la vigencia anterior
            self._x("""UPDATE suscripcion SET fecha_fin = DATE_SUB(fecha_fin, INTERVAL %s MONTH)
                       WHERE idsuscripcion = %s""", (pago["meses"], pago["idsuscripcion"]))
        self._x("""UPDATE pago SET anulado = TRUE, fecha_anulacion = NOW(), motivo_anulacion = %s
                   WHERE idpago = %s""", (motivo, idpago))
        return None

    def cambiar_estado_suscripcion(self, idsuscripcion, estado):
        self._x("UPDATE suscripcion SET estado = %s WHERE idsuscripcion = %s",
                (estado, idsuscripcion))
