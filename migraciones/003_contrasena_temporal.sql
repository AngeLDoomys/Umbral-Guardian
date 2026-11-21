-- =============================================================================
-- Migración 003: contraseñas temporales.
-- Cuando el proveedor o el administrador restablecen una contraseña (o crean una
-- cuenta), la cuenta queda marcada y debe cambiarla al iniciar sesión. La marca
-- llega a la réplica local en cada sincronización: sin conexión, una cuenta con
-- contraseña temporal no puede ingresar, porque el cambio requiere la nube.
-- =============================================================================

ALTER TABLE cuenta_local ADD COLUMN debe_cambiar_password INTEGER NOT NULL DEFAULT 0
    CHECK (debe_cambiar_password IN (0, 1));
