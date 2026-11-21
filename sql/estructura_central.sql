-- =============================================================================
-- Umbral Guardian — BASE CENTRAL (nube, administrada por el proveedor)
-- Plano de control: clientes, suscripciones, pagos, cuentas y nodos.
-- NO contiene datos biométricos ni el historial de accesos (quedan en cada
-- condominio, ver sql/local.sql). Solo la API accede a esta base.
--
-- Solo estructura (tablas vacías). Para instalar con datos base: python setup_central.py
-- =============================================================================

CREATE DATABASE IF NOT EXISTS umbral_central
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
    CONSTRAINT fk_nodo_condominio FOREIGN KEY (idcondominio)
        REFERENCES condominio (idcondominio) ON DELETE CASCADE
) ENGINE=InnoDB;
