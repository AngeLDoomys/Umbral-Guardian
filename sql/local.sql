-- =============================================================================
-- Umbral Guardian — BASE LOCAL (nodo de borde, PC de la portería)
-- Plano de datos: una base por condominio. Aquí quedan TODOS los datos
-- personales y biométricos; nunca salen del recinto (art. 14 quáter).
-- Por ser una base de un solo condominio, las tablas no llevan idcondominio.
--
-- Uso: python setup_nodo.py
-- =============================================================================

DROP DATABASE IF EXISTS umbral_local;
CREATE DATABASE umbral_local
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_spanish_ci;
USE umbral_local;

-- -----------------------------------------------------------------------------
-- 1. RÉPLICAS DE LA NUBE (se actualizan en cada sincronización)
-- -----------------------------------------------------------------------------

-- Copia de las cuentas del condominio para permitir el inicio de sesión sin
-- internet. idcuenta es el mismo identificador de la base central.
CREATE TABLE cuenta_local (
    idcuenta        INT UNSIGNED PRIMARY KEY,
    rol             ENUM('administrador','conserje') NOT NULL,
    rut             VARCHAR(12)  NOT NULL,
    nombres         VARCHAR(60)  NOT NULL,
    apellidos       VARCHAR(60)  NOT NULL,
    email           VARCHAR(120) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    activa          BOOLEAN      NOT NULL,
    sincronizada_en DATETIME     NOT NULL
) ENGINE=InnoDB;

-- Última licencia emitida por la nube, firmada digitalmente (Ed25519).
-- Permite operar sin conexión durante el período de gracia.
CREATE TABLE licencia (
    idlicencia      TINYINT UNSIGNED PRIMARY KEY DEFAULT 1,
    contenido       TEXT         NOT NULL COMMENT 'JSON firmado por la API',
    firma           VARCHAR(200) NOT NULL,
    verificada_en   DATETIME     NOT NULL,
    CONSTRAINT ck_licencia_unica CHECK (idlicencia = 1)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 2. COMUNIDAD
-- -----------------------------------------------------------------------------

CREATE TABLE unidad (
    idunidad        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    codigo          VARCHAR(20)  NOT NULL UNIQUE COMMENT 'Ej: Torre A-101, Casa 12'
) ENGINE=InnoDB;

CREATE TABLE tipo_residente (
    idtipo_residente TINYINT UNSIGNED PRIMARY KEY,
    nombre           VARCHAR(30) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE residente (
    idresidente           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idunidad              INT UNSIGNED NOT NULL,
    idtipo_residente      TINYINT UNSIGNED NOT NULL,
    rut                   VARCHAR(12)  NOT NULL UNIQUE,
    nombres               VARCHAR(60)  NOT NULL,
    apellidos             VARCHAR(60)  NOT NULL,
    fecha_nacimiento      DATE         NULL COMMENT 'Solo para exigir tutor a menores de 16 (art. 16 quáter)',
    telefono              VARCHAR(20)  NULL,
    email                 VARCHAR(120) NULL,
    fecha_alta            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tratamiento_bloqueado BOOLEAN      NOT NULL DEFAULT FALSE COMMENT 'Bloqueo temporal (art. 8 ter)',
    CONSTRAINT fk_residente_unidad FOREIGN KEY (idunidad)
        REFERENCES unidad (idunidad) ON DELETE CASCADE,
    CONSTRAINT fk_residente_tipo FOREIGN KEY (idtipo_residente)
        REFERENCES tipo_residente (idtipo_residente)
) ENGINE=InnoDB;

CREATE TABLE consentimiento (
    idconsentimiento   INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idresidente        INT UNSIGNED NOT NULL,
    idrepresentante    INT UNSIGNED NULL COMMENT 'Tutor si el titular es menor de 16',
    idcuenta_registro  INT UNSIGNED NULL,
    version_formulario VARCHAR(20)  NOT NULL,
    medio              ENUM('escrito','digital','verbal') NOT NULL,
    fecha_otorgamiento DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_revocacion   DATETIME     NULL,
    CONSTRAINT fk_consent_residente FOREIGN KEY (idresidente)
        REFERENCES residente (idresidente) ON DELETE CASCADE,
    CONSTRAINT fk_consent_representante FOREIGN KEY (idrepresentante)
        REFERENCES residente (idresidente) ON DELETE SET NULL,
    CONSTRAINT fk_consent_cuenta FOREIGN KEY (idcuenta_registro)
        REFERENCES cuenta_local (idcuenta) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Solo el vector del rostro; nunca la fotografía (minimización, art. 3 c)
CREATE TABLE plantilla_facial (
    idplantilla     INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idresidente     INT UNSIGNED NOT NULL,
    embedding       BLOB         NOT NULL,
    modelo          VARCHAR(30)  NOT NULL,
    fecha_captura   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_plantilla_residente FOREIGN KEY (idresidente)
        REFERENCES residente (idresidente) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE vehiculo (
    idvehiculo      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idunidad        INT UNSIGNED NOT NULL,
    patente         VARCHAR(8)   NOT NULL UNIQUE COMMENT 'Sin guiones, en mayúsculas',
    tipo            ENUM('auto','moto','camioneta','otro') NOT NULL DEFAULT 'auto',
    marca           VARCHAR(40)  NULL,
    modelo          VARCHAR(40)  NULL,
    color           VARCHAR(30)  NULL,
    fecha_registro  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_vehiculo_unidad FOREIGN KEY (idunidad)
        REFERENCES unidad (idunidad) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Visitas: identificadas por carnet, sin dato biométrico
CREATE TABLE visitante (
    idvisitante     INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    rut             VARCHAR(12)  NOT NULL UNIQUE,
    nombres         VARCHAR(60)  NOT NULL,
    apellidos       VARCHAR(60)  NOT NULL
) ENGINE=InnoDB;

CREATE TABLE visita (
    idvisita          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idvisitante       INT UNSIGNED NOT NULL,
    idunidad          INT UNSIGNED NOT NULL COMMENT 'Unidad de destino',
    idcuenta_registro INT UNSIGNED NULL,
    patente           VARCHAR(8)   NULL,
    fecha_ingreso     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_salida      DATETIME     NULL,
    CONSTRAINT fk_visita_visitante FOREIGN KEY (idvisitante)
        REFERENCES visitante (idvisitante) ON DELETE CASCADE,
    CONSTRAINT fk_visita_unidad FOREIGN KEY (idunidad)
        REFERENCES unidad (idunidad) ON DELETE CASCADE,
    CONSTRAINT fk_visita_cuenta FOREIGN KEY (idcuenta_registro)
        REFERENCES cuenta_local (idcuenta) ON DELETE SET NULL,
    INDEX ix_visita_activa (fecha_salida, patente)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 3. OPERACIÓN: zonas, cámaras y detecciones
-- -----------------------------------------------------------------------------

CREATE TABLE zona (
    idzona          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(60)  NOT NULL UNIQUE COMMENT 'Ej: Acceso peatonal'
) ENGINE=InnoDB;

CREATE TABLE camara (
    idcamara        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idzona          INT UNSIGNED NOT NULL,
    nombre          VARCHAR(60)  NOT NULL,
    tipo_fuente     ENUM('usb','rtsp','droidcam','file') NOT NULL DEFAULT 'rtsp',
    fuente          VARCHAR(255) NOT NULL COMMENT 'Índice USB o URL del stream (substream de baja resolución si hay fuente_alta)',
    fuente_alta     VARCHAR(255) NULL     COMMENT 'URL RTSP del canal principal (alta resolución) para recortes de rostros y patentes',
    ancho           SMALLINT UNSIGNED NOT NULL DEFAULT 1280,
    alto            SMALLINT UNSIGNED NOT NULL DEFAULT 720,
    fps             TINYINT UNSIGNED  NOT NULL DEFAULT 30,
    activa          BOOLEAN      NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_camara_zona FOREIGN KEY (idzona)
        REFERENCES zona (idzona) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Sin dato biométrico de personas no registradas (RNF-09). Al suprimir al
-- residente el evento queda anonimizado (idresidente = NULL).
CREATE TABLE deteccion_rostro (
    iddeteccion     BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idcamara        INT UNSIGNED NOT NULL,
    idresidente     INT UNSIGNED NULL,
    fecha_hora      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resultado       ENUM('reconocido','no_reconocido') NOT NULL,
    confianza       DECIMAL(5,4) NULL,
    CONSTRAINT fk_detr_camara FOREIGN KEY (idcamara)
        REFERENCES camara (idcamara) ON DELETE CASCADE,
    CONSTRAINT fk_detr_residente FOREIGN KEY (idresidente)
        REFERENCES residente (idresidente) ON DELETE SET NULL,
    INDEX ix_detr_fecha (fecha_hora)
) ENGINE=InnoDB;

CREATE TABLE deteccion_vehiculo (
    iddeteccion     BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idcamara        INT UNSIGNED NOT NULL,
    idvehiculo      INT UNSIGNED NULL,
    idvisita        INT UNSIGNED NULL,
    fecha_hora      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    patente_leida   VARCHAR(8)   NOT NULL,
    resultado       ENUM('residente','visita','no_registrado') NOT NULL,
    confianza       DECIMAL(5,4) NULL,
    CONSTRAINT fk_detv_camara FOREIGN KEY (idcamara)
        REFERENCES camara (idcamara) ON DELETE CASCADE,
    CONSTRAINT fk_detv_vehiculo FOREIGN KEY (idvehiculo)
        REFERENCES vehiculo (idvehiculo) ON DELETE SET NULL,
    CONSTRAINT fk_detv_visita FOREIGN KEY (idvisita)
        REFERENCES visita (idvisita) ON DELETE SET NULL,
    INDEX ix_detv_fecha (fecha_hora)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 4. DERECHOS DEL TITULAR (arts. 4 a 11)
-- -----------------------------------------------------------------------------

CREATE TABLE solicitud_derecho (
    idsolicitud       INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idresidente       INT UNSIGNED NULL,
    idcuenta_gestion  INT UNSIGNED NULL,
    rut_titular       VARCHAR(12)  NOT NULL COMMENT 'Constancia que sobrevive a la supresión',
    tipo              ENUM('acceso','rectificacion','supresion','oposicion',
                           'portabilidad','bloqueo') NOT NULL,
    fecha_solicitud   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado            ENUM('pendiente','acogida','rechazada') NOT NULL DEFAULT 'pendiente',
    fecha_respuesta   DATETIME     NULL,
    observacion       VARCHAR(500) NULL,
    CONSTRAINT fk_sol_residente FOREIGN KEY (idresidente)
        REFERENCES residente (idresidente) ON DELETE SET NULL,
    CONSTRAINT fk_sol_cuenta FOREIGN KEY (idcuenta_gestion)
        REFERENCES cuenta_local (idcuenta) ON DELETE SET NULL
) ENGINE=InnoDB;

INSERT INTO tipo_residente (idtipo_residente, nombre) VALUES
    (1, 'Propietario'), (2, 'Arrendatario'), (3, 'Familiar / ocupante');
