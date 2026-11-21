-- =============================================================================
-- Migración 005: visitas reconocidas por su rostro.
--
-- Regla del condominio (config.VISITA_ROSTRO_OBLIGATORIO): la visita registra su
-- rostro, con consentimiento, al completar su invitación. Al aprobarla queda una
-- AUTORIZACIÓN para la unidad:
--   ocasional : vigente solo la fecha de la visita; al día siguiente se elimina
--               con sus vectores (minimización).
--   frecuente : sin fecha de término, hasta que la administración la revoque.
-- =============================================================================

ALTER TABLE invitacion ADD COLUMN frecuente INTEGER NOT NULL DEFAULT 0
    CHECK (frecuente IN (0, 1));

CREATE TABLE visita_autorizada (
    idautorizacion  INTEGER PRIMARY KEY AUTOINCREMENT,
    idvisitante     INTEGER NOT NULL,
    idunidad        INTEGER NOT NULL,
    frecuente       INTEGER NOT NULL DEFAULT 0 CHECK (frecuente IN (0, 1)),
    fecha_desde     DATE    NOT NULL,
    fecha_hasta     DATE    NULL,                  -- NULL = frecuente, sin término
    patente         TEXT    NULL COLLATE NOCASE CHECK (length(patente) <= 8),
    consentimiento_version TEXT NULL,
    consentimiento_fecha   DATETIME NULL,
    idcuenta_aprobacion    INTEGER NULL,
    fecha_aprobacion       DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    CONSTRAINT fk_vaut_visitante FOREIGN KEY (idvisitante)
        REFERENCES visitante (idvisitante) ON DELETE CASCADE,
    CONSTRAINT fk_vaut_unidad FOREIGN KEY (idunidad)
        REFERENCES unidad (idunidad) ON DELETE CASCADE,
    CONSTRAINT fk_vaut_cuenta FOREIGN KEY (idcuenta_aprobacion)
        REFERENCES cuenta_local (idcuenta) ON DELETE SET NULL
);
CREATE INDEX ix_vaut_vigencia ON visita_autorizada (fecha_desde, fecha_hasta);
CREATE INDEX ix_vaut_visitante ON visita_autorizada (idvisitante);

CREATE TABLE plantilla_visita (
    idplantilla     INTEGER PRIMARY KEY AUTOINCREMENT,
    idautorizacion  INTEGER NOT NULL,
    embedding       BLOB    NOT NULL,
    modelo          TEXT    NOT NULL,
    CONSTRAINT fk_plvis_aut FOREIGN KEY (idautorizacion)
        REFERENCES visita_autorizada (idautorizacion) ON DELETE CASCADE
);
CREATE INDEX ix_plvis_aut ON plantilla_visita (idautorizacion);

-- deteccion_rostro: nuevo resultado 'visita' y vínculo a la autorización.
-- SQLite no permite cambiar un CHECK: se reconstruye la tabla con sus datos.
CREATE TABLE deteccion_rostro_nueva (
    iddeteccion     INTEGER PRIMARY KEY AUTOINCREMENT,
    idcamara        INTEGER NOT NULL,
    idresidente     INTEGER NULL,
    idautorizacion  INTEGER NULL,
    fecha_hora      DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    resultado       TEXT    NOT NULL CHECK (resultado IN ('reconocido', 'no_reconocido', 'visita')),
    confianza       REAL    NULL,
    CONSTRAINT fk_detr_camara FOREIGN KEY (idcamara)
        REFERENCES camara (idcamara) ON DELETE CASCADE,
    CONSTRAINT fk_detr_residente FOREIGN KEY (idresidente)
        REFERENCES residente (idresidente) ON DELETE SET NULL,
    CONSTRAINT fk_detr_autorizacion FOREIGN KEY (idautorizacion)
        REFERENCES visita_autorizada (idautorizacion) ON DELETE SET NULL
);
INSERT INTO deteccion_rostro_nueva (iddeteccion, idcamara, idresidente, fecha_hora, resultado, confianza)
    SELECT iddeteccion, idcamara, idresidente, fecha_hora, resultado, confianza FROM deteccion_rostro;
DROP TABLE deteccion_rostro;
ALTER TABLE deteccion_rostro_nueva RENAME TO deteccion_rostro;
CREATE INDEX ix_detr_fecha ON deteccion_rostro (fecha_hora);
CREATE INDEX ix_detr_camara ON deteccion_rostro (idcamara);
CREATE INDEX ix_detr_residente ON deteccion_rostro (idresidente);
CREATE INDEX ix_detr_autorizacion ON deteccion_rostro (idautorizacion);
