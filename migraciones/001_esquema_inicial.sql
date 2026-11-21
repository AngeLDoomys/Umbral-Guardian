-- =============================================================================
-- Umbral Guardian — BASE LOCAL (nodo de borde, PC de la portería), SQLite
-- Migración 001: esquema inicial, traducido de sql/local.sql (MySQL).
--
-- Plano de datos: una base por condominio. Aquí quedan TODOS los datos
-- personales y biométricos; nunca salen del recinto (art. 14 quáter).
--
-- Traducción desde MySQL:
--   AUTO_INCREMENT      -> INTEGER PRIMARY KEY AUTOINCREMENT (no reutiliza ids borrados)
--   ENUM(...)           -> TEXT con CHECK (col IN (...))
--   BOOLEAN             -> INTEGER con CHECK (col IN (0, 1))
--   VARCHAR(n)          -> TEXT con CHECK (length(col) <= n)
--   DECIMAL(5,4)        -> REAL
--   DATETIME / DATE     -> texto 'AAAA-MM-DD HH:MM:SS' / 'AAAA-MM-DD' en hora LOCAL
--                          (igual que NOW() de MySQL; CURRENT_TIMESTAMP de SQLite es UTC)
--   utf8mb4_spanish_ci  -> COLLATE NOCASE en las columnas de texto que se comparan
--                          u ordenan (no iguala tildes: 'Jose' <> 'José')
--   embedding BLOB      -> float32 en bytes (numpy .tobytes()), 2048 bytes para ArcFace
--
-- Las claves foráneas solo se cumplen con PRAGMA foreign_keys = ON, que
-- database.py activa en cada conexión.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. RÉPLICAS DE LA NUBE (se actualizan en cada sincronización)
-- -----------------------------------------------------------------------------

-- Copia de las cuentas del condominio para permitir el inicio de sesión sin
-- internet. idcuenta es el mismo identificador de la base central.
CREATE TABLE cuenta_local (
    idcuenta        INTEGER PRIMARY KEY,
    rol             TEXT    NOT NULL CHECK (rol IN ('administrador', 'conserje')),
    rut             TEXT    NOT NULL COLLATE NOCASE CHECK (length(rut) <= 12),
    nombres         TEXT    NOT NULL COLLATE NOCASE CHECK (length(nombres) <= 60),
    apellidos       TEXT    NOT NULL COLLATE NOCASE CHECK (length(apellidos) <= 60),
    email           TEXT    NOT NULL COLLATE NOCASE UNIQUE CHECK (length(email) <= 120),
    password_hash   TEXT    NOT NULL CHECK (length(password_hash) <= 255),
    activa          INTEGER NOT NULL CHECK (activa IN (0, 1)),
    sincronizada_en DATETIME NOT NULL
);

-- Última licencia emitida por la nube, firmada digitalmente (Ed25519).
-- Permite operar sin conexión durante el período de gracia.
CREATE TABLE licencia (
    idlicencia      INTEGER PRIMARY KEY DEFAULT 1 CHECK (idlicencia = 1),
    contenido       TEXT    NOT NULL,                 -- JSON firmado por la API
    firma           TEXT    NOT NULL CHECK (length(firma) <= 200),
    verificada_en   DATETIME NOT NULL
);

-- -----------------------------------------------------------------------------
-- 2. COMUNIDAD
-- -----------------------------------------------------------------------------

CREATE TABLE unidad (
    idunidad        INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo          TEXT    NOT NULL COLLATE NOCASE UNIQUE CHECK (length(codigo) <= 20)  -- Ej: Torre A-101
);

CREATE TABLE tipo_residente (
    idtipo_residente INTEGER PRIMARY KEY,
    nombre           TEXT   NOT NULL COLLATE NOCASE UNIQUE CHECK (length(nombre) <= 30)
);

CREATE TABLE residente (
    idresidente           INTEGER PRIMARY KEY AUTOINCREMENT,
    idunidad              INTEGER NOT NULL,
    idtipo_residente      INTEGER NOT NULL,
    rut                   TEXT    NOT NULL COLLATE NOCASE UNIQUE CHECK (length(rut) <= 12),
    nombres               TEXT    NOT NULL COLLATE NOCASE CHECK (length(nombres) <= 60),
    apellidos             TEXT    NOT NULL COLLATE NOCASE CHECK (length(apellidos) <= 60),
    fecha_nacimiento      DATE    NULL,     -- solo para exigir tutor a menores de 16 (art. 16 quáter)
    telefono              TEXT    NULL CHECK (length(telefono) <= 20),
    email                 TEXT    NULL COLLATE NOCASE CHECK (length(email) <= 120),
    fecha_alta            DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    tratamiento_bloqueado INTEGER NOT NULL DEFAULT 0
                          CHECK (tratamiento_bloqueado IN (0, 1)),  -- bloqueo temporal (art. 8 ter)
    CONSTRAINT fk_residente_unidad FOREIGN KEY (idunidad)
        REFERENCES unidad (idunidad) ON DELETE CASCADE,
    CONSTRAINT fk_residente_tipo FOREIGN KEY (idtipo_residente)
        REFERENCES tipo_residente (idtipo_residente)
);

CREATE TABLE consentimiento (
    idconsentimiento   INTEGER PRIMARY KEY AUTOINCREMENT,
    idresidente        INTEGER NOT NULL,
    idrepresentante    INTEGER NULL,      -- tutor si el titular es menor de 16
    idcuenta_registro  INTEGER NULL,
    version_formulario TEXT    NOT NULL CHECK (length(version_formulario) <= 20),
    medio              TEXT    NOT NULL CHECK (medio IN ('escrito', 'digital', 'verbal')),
    fecha_otorgamiento DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    fecha_revocacion   DATETIME NULL,
    CONSTRAINT fk_consent_residente FOREIGN KEY (idresidente)
        REFERENCES residente (idresidente) ON DELETE CASCADE,
    CONSTRAINT fk_consent_representante FOREIGN KEY (idrepresentante)
        REFERENCES residente (idresidente) ON DELETE SET NULL,
    CONSTRAINT fk_consent_cuenta FOREIGN KEY (idcuenta_registro)
        REFERENCES cuenta_local (idcuenta) ON DELETE SET NULL
);

-- Solo el vector del rostro; nunca la fotografía (minimización, art. 3 c)
CREATE TABLE plantilla_facial (
    idplantilla     INTEGER PRIMARY KEY AUTOINCREMENT,
    idresidente     INTEGER NOT NULL,
    embedding       BLOB    NOT NULL,    -- float32 .tobytes()
    modelo          TEXT    NOT NULL CHECK (length(modelo) <= 30),
    fecha_captura   DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    CONSTRAINT fk_plantilla_residente FOREIGN KEY (idresidente)
        REFERENCES residente (idresidente) ON DELETE CASCADE
);

CREATE TABLE vehiculo (
    idvehiculo      INTEGER PRIMARY KEY AUTOINCREMENT,
    idunidad        INTEGER NOT NULL,
    patente         TEXT    NOT NULL COLLATE NOCASE UNIQUE CHECK (length(patente) <= 8),  -- sin guiones
    tipo            TEXT    NOT NULL DEFAULT 'auto'
                    CHECK (tipo IN ('auto', 'moto', 'camioneta', 'otro')),
    marca           TEXT    NULL CHECK (length(marca) <= 40),
    modelo          TEXT    NULL CHECK (length(modelo) <= 40),
    color           TEXT    NULL CHECK (length(color) <= 30),
    fecha_registro  DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    CONSTRAINT fk_vehiculo_unidad FOREIGN KEY (idunidad)
        REFERENCES unidad (idunidad) ON DELETE CASCADE
);

-- Visitas: identificadas por carnet, sin dato biométrico
CREATE TABLE visitante (
    idvisitante     INTEGER PRIMARY KEY AUTOINCREMENT,
    rut             TEXT    NOT NULL COLLATE NOCASE UNIQUE CHECK (length(rut) <= 12),
    nombres         TEXT    NOT NULL COLLATE NOCASE CHECK (length(nombres) <= 60),
    apellidos       TEXT    NOT NULL COLLATE NOCASE CHECK (length(apellidos) <= 60)
);

CREATE TABLE visita (
    idvisita          INTEGER PRIMARY KEY AUTOINCREMENT,
    idvisitante       INTEGER NOT NULL,
    idunidad          INTEGER NOT NULL,   -- unidad de destino
    idcuenta_registro INTEGER NULL,
    patente           TEXT    NULL COLLATE NOCASE CHECK (length(patente) <= 8),
    fecha_ingreso     DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    fecha_salida      DATETIME NULL,
    CONSTRAINT fk_visita_visitante FOREIGN KEY (idvisitante)
        REFERENCES visitante (idvisitante) ON DELETE CASCADE,
    CONSTRAINT fk_visita_unidad FOREIGN KEY (idunidad)
        REFERENCES unidad (idunidad) ON DELETE CASCADE,
    CONSTRAINT fk_visita_cuenta FOREIGN KEY (idcuenta_registro)
        REFERENCES cuenta_local (idcuenta) ON DELETE SET NULL
);
CREATE INDEX ix_visita_activa ON visita (fecha_salida, patente);

-- -----------------------------------------------------------------------------
-- 3. OPERACIÓN: zonas, cámaras y detecciones
-- -----------------------------------------------------------------------------

CREATE TABLE zona (
    idzona          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT    NOT NULL COLLATE NOCASE UNIQUE CHECK (length(nombre) <= 60)
);

CREATE TABLE camara (
    idcamara        INTEGER PRIMARY KEY AUTOINCREMENT,
    idzona          INTEGER NOT NULL,
    nombre          TEXT    NOT NULL COLLATE NOCASE CHECK (length(nombre) <= 60),
    tipo_fuente     TEXT    NOT NULL DEFAULT 'rtsp'
                    CHECK (tipo_fuente IN ('usb', 'rtsp', 'droidcam', 'file')),
    fuente          TEXT    NOT NULL CHECK (length(fuente) <= 255),     -- índice USB o URL (substream)
    fuente_alta     TEXT    NULL CHECK (length(fuente_alta) <= 255),    -- canal principal RTSP
    ancho           INTEGER NOT NULL DEFAULT 1280 CHECK (ancho BETWEEN 0 AND 65535),
    alto            INTEGER NOT NULL DEFAULT 720  CHECK (alto BETWEEN 0 AND 65535),
    fps             INTEGER NOT NULL DEFAULT 30   CHECK (fps BETWEEN 0 AND 255),
    activa          INTEGER NOT NULL DEFAULT 1    CHECK (activa IN (0, 1)),
    CONSTRAINT fk_camara_zona FOREIGN KEY (idzona)
        REFERENCES zona (idzona) ON DELETE CASCADE
);

-- Sin dato biométrico de personas no registradas (RNF-09). Al suprimir al
-- residente el evento queda anonimizado (idresidente = NULL).
CREATE TABLE deteccion_rostro (
    iddeteccion     INTEGER PRIMARY KEY AUTOINCREMENT,
    idcamara        INTEGER NOT NULL,
    idresidente     INTEGER NULL,
    fecha_hora      DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    resultado       TEXT    NOT NULL CHECK (resultado IN ('reconocido', 'no_reconocido')),
    confianza       REAL    NULL,
    CONSTRAINT fk_detr_camara FOREIGN KEY (idcamara)
        REFERENCES camara (idcamara) ON DELETE CASCADE,
    CONSTRAINT fk_detr_residente FOREIGN KEY (idresidente)
        REFERENCES residente (idresidente) ON DELETE SET NULL
);
CREATE INDEX ix_detr_fecha ON deteccion_rostro (fecha_hora);

CREATE TABLE deteccion_vehiculo (
    iddeteccion     INTEGER PRIMARY KEY AUTOINCREMENT,
    idcamara        INTEGER NOT NULL,
    idvehiculo      INTEGER NULL,
    idvisita        INTEGER NULL,
    fecha_hora      DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    patente_leida   TEXT    NOT NULL CHECK (length(patente_leida) <= 8),
    resultado       TEXT    NOT NULL CHECK (resultado IN ('residente', 'visita', 'no_registrado')),
    confianza       REAL    NULL,
    CONSTRAINT fk_detv_camara FOREIGN KEY (idcamara)
        REFERENCES camara (idcamara) ON DELETE CASCADE,
    CONSTRAINT fk_detv_vehiculo FOREIGN KEY (idvehiculo)
        REFERENCES vehiculo (idvehiculo) ON DELETE SET NULL,
    CONSTRAINT fk_detv_visita FOREIGN KEY (idvisita)
        REFERENCES visita (idvisita) ON DELETE SET NULL
);
CREATE INDEX ix_detv_fecha ON deteccion_vehiculo (fecha_hora);

-- -----------------------------------------------------------------------------
-- 4. DERECHOS DEL TITULAR (arts. 4 a 11)
-- -----------------------------------------------------------------------------

-- Al suprimir al residente, idresidente queda en NULL (ON DELETE SET NULL) y
-- rut_titular sobrevive como constancia de que la solicitud se atendió (art. 12).
CREATE TABLE solicitud_derecho (
    idsolicitud       INTEGER PRIMARY KEY AUTOINCREMENT,
    idresidente       INTEGER NULL,
    idcuenta_gestion  INTEGER NULL,
    rut_titular       TEXT    NOT NULL COLLATE NOCASE CHECK (length(rut_titular) <= 12),
    tipo              TEXT    NOT NULL CHECK (tipo IN ('acceso', 'rectificacion', 'supresion',
                                                       'oposicion', 'portabilidad', 'bloqueo')),
    fecha_solicitud   DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    estado            TEXT    NOT NULL DEFAULT 'pendiente'
                      CHECK (estado IN ('pendiente', 'acogida', 'rechazada')),
    fecha_respuesta   DATETIME NULL,
    observacion       TEXT    NULL CHECK (length(observacion) <= 500),
    CONSTRAINT fk_sol_residente FOREIGN KEY (idresidente)
        REFERENCES residente (idresidente) ON DELETE SET NULL,
    CONSTRAINT fk_sol_cuenta FOREIGN KEY (idcuenta_gestion)
        REFERENCES cuenta_local (idcuenta) ON DELETE SET NULL
);

-- MySQL indexa solo las columnas de claves foráneas; SQLite no. Sin estos
-- índices, cada borrado en cascada recorre la tabla hija completa.
CREATE INDEX ix_residente_unidad      ON residente (idunidad);
CREATE INDEX ix_consent_residente     ON consentimiento (idresidente);
CREATE INDEX ix_consent_representante ON consentimiento (idrepresentante);
CREATE INDEX ix_plantilla_residente   ON plantilla_facial (idresidente);
CREATE INDEX ix_vehiculo_unidad       ON vehiculo (idunidad);
CREATE INDEX ix_visita_visitante      ON visita (idvisitante);
CREATE INDEX ix_visita_unidad         ON visita (idunidad);
CREATE INDEX ix_camara_zona           ON camara (idzona);
CREATE INDEX ix_detr_camara           ON deteccion_rostro (idcamara);
CREATE INDEX ix_detr_residente        ON deteccion_rostro (idresidente);
CREATE INDEX ix_detv_camara           ON deteccion_vehiculo (idcamara);
CREATE INDEX ix_detv_vehiculo         ON deteccion_vehiculo (idvehiculo);
CREATE INDEX ix_detv_visita           ON deteccion_vehiculo (idvisita);
CREATE INDEX ix_sol_residente         ON solicitud_derecho (idresidente);

INSERT INTO tipo_residente (idtipo_residente, nombre) VALUES
    (1, 'Propietario'), (2, 'Arrendatario'), (3, 'Familiar / ocupante');
