# -*- coding: utf-8 -*-
"""
core/textos.py - Textos legales compartidos por el programa de la portería y el
registro desde el celular (servido por la API central).
"""

TEXTO_CONSENTIMIENTO = (
    "Información al titular (art. 16 ter, Ley 19.628 modificada por Ley 21.719)\n\n"
    "• Sistema biométrico: reconocimiento facial Umbral Guardian "
    "(OpenCV, modelo {modelo}). Se guarda solo un vector numérico del rostro, "
    "no la fotografía.\n"
    "• Finalidad: identificar al residente en los accesos del condominio para "
    "informar al conserje y registrar el ingreso. No se usa para otro fin.\n"
    "• Período: mientras sea residente o hasta que revoque este consentimiento.\n"
    "• Derechos: acceso, rectificación, supresión, oposición, portabilidad y "
    "bloqueo, que se ejercen ante la administración del condominio. Puede "
    "revocar el consentimiento en cualquier momento sin expresar causa.\n"
    "• Otorgarlo es voluntario: quien no lo otorgue ingresa por el "
    "procedimiento habitual de conserjería."
)

# visitas: el rostro permite que la cámara del acceso las reconozca al llegar
TEXTO_CONSENTIMIENTO_VISITA = (
    "Información al titular (art. 16 ter, Ley 19.628 modificada por Ley 21.719)\n\n"
    "• Sistema biométrico: reconocimiento facial Umbral Guardian "
    "(OpenCV, modelo {modelo}). Se guarda solo un vector numérico del rostro, "
    "no la fotografía.\n"
    "• Finalidad: identificarlo como visita autorizada de la unidad en el acceso "
    "del condominio. No se usa para otro fin.\n"
    "• Período: {periodo}\n"
    "• Requisito: el reglamento del condominio exige este registro a las visitas "
    "para ingresar. Si no desea otorgarlo, coordine su ingreso con la unidad que "
    "visita y la administración.\n"
    "• Derechos: acceso, rectificación, supresión, oposición, portabilidad y "
    "bloqueo, que se ejercen ante la administración del condominio. Puede "
    "revocar el consentimiento en cualquier momento."
)
PERIODO_VISITA = ("el vector se elimina automáticamente al día siguiente de la "
                  "fecha de su visita.")
PERIODO_VISITA_FRECUENTE = ("mientras la unidad mantenga su autorización como visita "
                            "frecuente, o hasta que usted revoque este consentimiento.")

# se agrega al texto anterior cuando el registro se hace desde el celular
TEXTO_REGISTRO_REMOTO = (
    "\n• Registro desde el celular: sus fotos viajan cifradas (HTTPS) al servicio "
    "del proveedor de Umbral Guardian, alojado en Amazon Web Services (Estados "
    "Unidos). Allí se calcula el vector del rostro y la fotografía se descarta de "
    "inmediato, sin guardarse. El vector y sus datos se envían cifrados al equipo "
    "del condominio, que es el único que puede leerlos, y se eliminan del servicio "
    "en cuanto el equipo los recibe."
)
