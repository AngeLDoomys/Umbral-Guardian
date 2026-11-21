-- =============================================================================
-- Migración 002: el reconocimiento facial pasa de ArcFace (512 dimensiones) a
-- SFace (128 dimensiones). Los vectores de ArcFace no son comparables con los
-- de SFace y el motor ya no los usa: se eliminan, porque conservar un dato
-- biométrico sin finalidad contradice el principio de minimización (Ley 21.719,
-- art. 3 c). Los residentes afectados deben volver a capturar su rostro; su
-- consentimiento y sus demás datos no se tocan.
-- =============================================================================

DELETE FROM plantilla_facial WHERE modelo = 'ArcFace';
