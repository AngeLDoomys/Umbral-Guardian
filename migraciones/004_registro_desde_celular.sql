-- =============================================================================
-- Migración 004: registro desde el celular.
--
-- La administración genera una INVITACIÓN (QR o enlace, de un solo uso y con
-- vencimiento). Quien la abre, desde cualquier lugar, completa sus datos en la
-- página de la API central; la nube calcula el vector del rostro, descarta la
-- foto y guarda el resultado CIFRADO para este nodo (core/registro_remoto.py).
-- El nodo lo descarga y lo deja como SOLICITUD pendiente hasta que la
-- administración la aprueba en el programa.
--
-- De las fotos del rostro solo llega el vector (como en la captura en
-- portería); si la solicitud se rechaza o vence, se elimina con sus vectores.
-- =============================================================================

CREATE TABLE invitacion (
    idinvitacion    INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash      TEXT    NOT NULL UNIQUE,            -- SHA-256 del token del enlace
    tipo            TEXT    NOT NULL CHECK (tipo IN ('residente', 'visita')),
    idunidad        INTEGER NOT NULL,
    idresidente     INTEGER NULL,      -- residente ya registrado que solo debe capturar su rostro
    idcuenta_creacion INTEGER NULL,
    fecha_creacion  DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    vence           DATETIME NOT NULL,
    usada           DATETIME NULL,
    CONSTRAINT fk_inv_unidad FOREIGN KEY (idunidad)
        REFERENCES unidad (idunidad) ON DELETE CASCADE,
    CONSTRAINT fk_inv_residente FOREIGN KEY (idresidente)
        REFERENCES residente (idresidente) ON DELETE CASCADE,
    CONSTRAINT fk_inv_cuenta FOREIGN KEY (idcuenta_creacion)
        REFERENCES cuenta_local (idcuenta) ON DELETE SET NULL
);

CREATE TABLE solicitud_registro (
    idsolicitud     INTEGER PRIMARY KEY AUTOINCREMENT,
    idinvitacion    INTEGER NOT NULL UNIQUE,
    tipo            TEXT    NOT NULL CHECK (tipo IN ('residente', 'visita')),
    estado          TEXT    NOT NULL DEFAULT 'incompleta'
                    CHECK (estado IN ('incompleta', 'pendiente', 'aprobada', 'rechazada')),
    datos           TEXT    NOT NULL,          -- JSON con lo ingresado en el formulario
    consentimiento_version TEXT NULL,          -- versión aceptada en el celular (residentes)
    consentimiento_fecha   DATETIME NULL,
    fecha_envio     DATETIME NULL,             -- cuando quedó completa (pendiente)
    fecha_revision  DATETIME NULL,
    idcuenta_revision INTEGER NULL,
    observacion     TEXT    NULL CHECK (length(observacion) <= 300),
    CONSTRAINT fk_solreg_inv FOREIGN KEY (idinvitacion)
        REFERENCES invitacion (idinvitacion) ON DELETE CASCADE,
    CONSTRAINT fk_solreg_cuenta FOREIGN KEY (idcuenta_revision)
        REFERENCES cuenta_local (idcuenta) ON DELETE SET NULL
);
CREATE INDEX ix_solreg_estado ON solicitud_registro (estado);

-- vectores del rostro capturados en el celular, a la espera de aprobación
CREATE TABLE solicitud_plantilla (
    idsolplantilla  INTEGER PRIMARY KEY AUTOINCREMENT,
    idsolicitud     INTEGER NOT NULL,
    embedding       BLOB    NOT NULL,
    modelo          TEXT    NOT NULL,
    CONSTRAINT fk_solpl_sol FOREIGN KEY (idsolicitud)
        REFERENCES solicitud_registro (idsolicitud) ON DELETE CASCADE
);
CREATE INDEX ix_solpl_sol ON solicitud_plantilla (idsolicitud);
