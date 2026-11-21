-- =============================================================================
-- Umbral Guardian — BASE CENTRAL (nube, administrada por el proveedor)
-- Plano de control: clientes, suscripciones, pagos, cuentas y nodos.
-- NO contiene datos biométricos ni el historial de accesos (quedan en cada
-- condominio, ver sql/local.sql). Solo la API accede a esta base.
--
-- Uso: python setup_central.py
-- =============================================================================

DROP DATABASE IF EXISTS umbral_central;
CREATE DATABASE umbral_central
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_spanish_ci;
USE umbral_central;

-- Planes comerciales
CREATE TABLE plan (
    idplan          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(40)  NOT NULL UNIQUE,
    precio_mensual  INT UNSIGNED NOT NULL COMMENT 'CLP',
    max_camaras     TINYINT UNSIGNED NOT NULL,
    activo          BOOLEAN      NOT NULL DEFAULT TRUE
) ENGINE=InnoDB;

-- Cliente: la comunidad de copropietarios (responsable de datos, art. 2 n)
CREATE TABLE condominio (
    idcondominio    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    rut             VARCHAR(12)  NOT NULL UNIQUE,
    nombre          VARCHAR(100) NOT NULL,
    direccion       VARCHAR(150) NOT NULL,
    comuna          VARCHAR(60)  NOT NULL,
    email_contacto  VARCHAR(120) NOT NULL,
    telefono        VARCHAR(20)  NULL,
    fecha_registro  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE suscripcion (
    idsuscripcion   INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idcondominio    INT UNSIGNED NOT NULL,
    idplan          INT UNSIGNED NOT NULL,
    fecha_inicio    DATE         NOT NULL,
    fecha_fin       DATE         NOT NULL COMMENT 'Pagado hasta',
    estado          ENUM('activa','suspendida','cancelada') NOT NULL DEFAULT 'activa',
    CONSTRAINT fk_susc_condominio FOREIGN KEY (idcondominio)
        REFERENCES condominio (idcondominio) ON DELETE CASCADE,
    CONSTRAINT fk_susc_plan FOREIGN KEY (idplan) REFERENCES plan (idplan),
    INDEX ix_susc_condominio (idcondominio, fecha_fin)
) ENGINE=InnoDB;

-- Pagos registrados por el proveedor (transferencia)
CREATE TABLE pago (
    idpago          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idsuscripcion   INT UNSIGNED NOT NULL,
    fecha_pago      DATE         NOT NULL,
    monto           INT UNSIGNED NOT NULL COMMENT 'CLP',
    meses           TINYINT UNSIGNED NOT NULL,
    medio           ENUM('transferencia','efectivo','otro') NOT NULL DEFAULT 'transferencia',
    referencia      VARCHAR(60)  NULL,
    fecha_fin_anterior DATE      NULL COMMENT 'Vigencia antes del pago: se restaura si se anula',
    anulado         BOOLEAN      NOT NULL DEFAULT FALSE,
    fecha_anulacion DATETIME     NULL,
    motivo_anulacion VARCHAR(200) NULL,
    CONSTRAINT fk_pago_suscripcion FOREIGN KEY (idsuscripcion)
        REFERENCES suscripcion (idsuscripcion) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE rol (
    idrol           TINYINT UNSIGNED PRIMARY KEY,
    nombre          VARCHAR(20) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- Cuentas de acceso (quien opera el sistema)
CREATE TABLE cuenta (
    idcuenta        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idcondominio    INT UNSIGNED NULL COMMENT 'NULL = cuenta del proveedor (superadmin)',
    idrol           TINYINT UNSIGNED NOT NULL,
    rut             VARCHAR(12)  NOT NULL,
    nombres         VARCHAR(60)  NOT NULL,
    apellidos       VARCHAR(60)  NOT NULL,
    email           VARCHAR(120) NOT NULL UNIQUE COMMENT 'Usuario de inicio de sesión',
    password_hash   VARCHAR(255) NOT NULL COMMENT 'PBKDF2-SHA256 con sal',
    debe_cambiar_password BOOLEAN NOT NULL DEFAULT FALSE
                    COMMENT 'Contraseña temporal: se exige cambiarla al iniciar sesión',
    activa          BOOLEAN      NOT NULL DEFAULT TRUE,
    fecha_creacion  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ultimo_acceso   DATETIME     NULL,
    CONSTRAINT fk_cuenta_condominio FOREIGN KEY (idcondominio)
        REFERENCES condominio (idcondominio) ON DELETE CASCADE,
    CONSTRAINT fk_cuenta_rol FOREIGN KEY (idrol) REFERENCES rol (idrol)
) ENGINE=InnoDB;

-- Equipo instalado en la portería (nodo de borde). Se autentica ante la API
-- con una clave propia; en la base solo se guarda su hash.
CREATE TABLE nodo (
    idnodo          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idcondominio    INT UNSIGNED NOT NULL,
    nombre          VARCHAR(60)  NOT NULL,
    clave_hash      CHAR(64)     NOT NULL UNIQUE COMMENT 'SHA-256 de la clave del nodo',
    fecha_alta      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ultimo_contacto DATETIME     NULL,
    activo          BOOLEAN      NOT NULL DEFAULT TRUE,
    clave_registro  TEXT         NULL COMMENT 'Clave pública X25519 para cifrar los registros móviles',
    CONSTRAINT fk_nodo_condominio FOREIGN KEY (idcondominio)
        REFERENCES condominio (idcondominio) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Registro desde el celular. La nube sirve el formulario, revisa las fotos y
-- calcula el vector del rostro, pero solo guarda el resultado CIFRADO para el
-- nodo (que es el único que puede leerlo) y lo borra cuando el nodo lo recibe.
CREATE TABLE invitacion_registro (
    idinvitacion    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idnodo          INT UNSIGNED NOT NULL,
    token_hash      CHAR(64)     NOT NULL UNIQUE COMMENT 'SHA-256 del token del enlace',
    tipo            ENUM('residente','visita') NOT NULL,
    id_local        INT UNSIGNED NOT NULL COMMENT 'Id de la invitación en la base del nodo',
    unidad          VARCHAR(20)  NOT NULL COMMENT 'Código de la unidad, para mostrarlo',
    solo_rostro     BOOLEAN      NOT NULL DEFAULT FALSE,
    frecuente       BOOLEAN      NOT NULL DEFAULT FALSE COMMENT 'Visita frecuente (sin fecha de término)',
    rostro          BOOLEAN      NOT NULL DEFAULT TRUE COMMENT 'Visita: exige rostro y consentimiento',
    consentimiento_version VARCHAR(20) NOT NULL,
    creada          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    vence           DATETIME     NOT NULL,
    usada           DATETIME     NULL,
    CONSTRAINT fk_invreg_nodo FOREIGN KEY (idnodo) REFERENCES nodo (idnodo) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE envio_registro (
    idenvio         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idinvitacion    INT UNSIGNED NOT NULL UNIQUE,
    paquete         MEDIUMTEXT   NOT NULL COMMENT 'Cifrado para el nodo (X25519 + AES-GCM)',
    creado          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_envio_inv FOREIGN KEY (idinvitacion)
        REFERENCES invitacion_registro (idinvitacion) ON DELETE CASCADE
) ENGINE=InnoDB;

INSERT INTO rol (idrol, nombre) VALUES
    (1, 'superadmin'), (2, 'administrador'), (3, 'conserje');

INSERT INTO plan (nombre, precio_mensual, max_camaras) VALUES
    ('Básico',    79990, 2),
    ('Estándar', 129990, 4),
    ('Avanzado', 189990, 8);
