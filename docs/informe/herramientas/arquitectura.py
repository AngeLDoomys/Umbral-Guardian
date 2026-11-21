# -*- coding: utf-8 -*-
"""Arquitectura en dos planos (estilo aprobado + registro por QR, SFace 0,50 y SQLite).

    py docs/informe/herramientas/arquitectura.py
"""
from lienzo import AZUL, OCRE, VERDE, Lienzo

GRIS_G = "#6b6f76"


def arquitectura():
    c = Lienzo(1580, 2200)
    c.titulo("Arquitectura en dos planos", y=40)

    # ---------------- celular
    c.caja(990, 72, 485, 66, "Celular del residente o visita", "abre el QR · datos, consentimiento y cinco fotos",
           fondo="#fff8ec", borde=OCRE, ty=98)
    # ---------------- plano de control
    c.grupo(58, 170, 1467, 330, "PLANO DE CONTROL · nube del proveedor (AWS)", fondo="#eaf2fb", ty=200)
    c.caja(108, 228, 582, 100, "API REST Flask", "login · sincronización del nodo · invitaciones QR", ty=254)
    c.cilindro(790, 219, 460, 118, "umbral_central · 9 tablas",
               "condominios, planes, suscripciones, pagos, cuentas,\nroles, nodos, invitaciones y registros cifrados")
    c.linea([(690, 278), (783, 278)])
    c.caja(790, 385, 460, 90, "Formulario de registro móvil",
           "valida la invitación · calcula el vector SFace\ny descarta la foto · cifra la solicitud para el nodo", ty=410)
    c.linea([(1020, 385), (1020, 344)])
    c.texto(1030, 368, "guarda", size=12, peso="bold")
    c.linea([(1400, 138), (1400, 430), (1257, 430)])
    c.etiqueta(1410, 162, "HTTPS 443", anchor="start")
    # ---------------- flechas entre planos
    c.linea([(166, 815), (166, 507)])
    c.etiqueta(193, 560, "correo, contraseña y clave del nodo · invitaciones QR", anchor="start")
    c.linea([(1350, 500), (1350, 858)])
    c.etiqueta(1335, 552, "licencia firmada Ed25519 · réplica de las cuentas", anchor="end")
    c.etiqueta(1335, 572, "solicitudes del QR cifradas · cada 60 s", anchor="end")

    # ---------------- fuente de video
    c.grupo(267, 613, 1049, 142, "FUENTE DE VIDEO · no es parte del nodo", color=GRIS_G, fondo="#f3f3f1", ty=640)
    c.caja(308, 648, 450, 83, "Dos cámaras IP del ingreso", "una vehicular y una peatonal", ty=675)
    c.caja(808, 648, 466, 83, "Grabador Hikvision", "canal principal y canal de baja resolución", ty=675)
    c.linea([(758, 690), (801, 690)])
    c.linea([(1041, 731), (1041, 856)])
    c.etiqueta(1060, 788, "RTSP 554 · sólo lectura", anchor="start")

    # ---------------- plano de datos
    c.grupo(58, 805, 1467, 1158, "PLANO DE DATOS · nodo de borde en la portería", ty=834)
    c.caja(108, 863, 1092, 83, "Un motor de visión por cámara",
           "detecta sobre el canal de baja resolución y recorta desde el principal · la GPU atiende una tarea a la vez",
           ty=890)
    c.caja(1240, 863, 235, 83, "Registro móvil", "descifra las solicitudes\nque llegan de la nube", ty=887, ssize=11)
    c.linea([(437, 946), (437, 1012)])
    c.etiqueta(468, 975, "persona", anchor="start")
    c.linea([(1145, 946), (1145, 1012)])
    c.etiqueta(1176, 975, "vehículo", anchor="start")

    c.grupo(108, 984, 658, 508, "Rama peatonal", color=VERDE, fondo="#eef6f3", ty=1015)
    c.grupo(816, 984, 658, 508, "Rama vehicular", color=OCRE, fondo="#fdf5e6", ty=1015)
    peat = [("RF-DETR Nano", "detección de persona"),
            ("YuNet", "detección del rostro y alineación por los ojos"),
            ("Filtros de calidad", "confianza 0,75 · nitidez por varianza del laplaciano"),
            ("SFace", "representación vectorial de 128 dimensiones"),
            ("Distancia coseno 0,50", "margen 0,09 · residentes y visitas autorizadas"),
            ("Votación entre intentos", "dos coincidencias confirman · cinco sin confirmar, no reconocido")]
    veh = [("RF-DETR Nano", "detección de vehículo"),
           ("Seguidor propio IoU", "seguimiento del vehículo entre fotogramas"),
           ("Detector de patentes", "localización de la placa"),
           ("fast-plate-ocr", "lectura de la patente · lector único"),
           ("Validación", "formato chileno y confianza mínima por carácter"),
           ("Votación entre lecturas", "la patente se confirma con dos lecturas idénticas")]
    for i, ((t1, s1), (t2, s2)) in enumerate(zip(peat, veh)):
        y = 1019 + i * 78.5
        c.caja(137, y, 600, 53, t1, s1, tsize=14, ssize=11, ty=y + 20)
        c.caja(845, y, 600, 53, t2, s2, tsize=14, ssize=11, ty=y + 20)
        if i:
            c.linea([(437, y - 25.5), (437, y - 2)])
            c.linea([(1145, y - 25.5), (1145, y - 2)])
    c.linea([(437, 1464), (437, 1524), (632, 1524), (632, 1552)])
    c.etiqueta(441, 1512, "residente / visita / no reconocido", anchor="start")
    c.linea([(1145, 1464), (1145, 1524), (950, 1524), (950, 1552)])
    c.etiqueta(1050, 1512, "residente / visita / no registrado")
    c.caja(533, 1559, 516, 74, "Resultado confirmado", "con su cámara, su zona y su hora", ty=1586)
    c.linea([(666, 1633), (666, 1655), (425, 1655), (425, 1683)])
    c.etiqueta(516, 1645, "registra")
    c.linea([(916, 1633), (916, 1655), (1158, 1655), (1158, 1677)])
    c.etiqueta(1070, 1645, "avisa en vivo")
    c.cilindro(108, 1686, 633, 118, "umbral_local · 20 tablas",
               "SQLite · residentes, consentimientos, plantillas, vehículos,\n"
               "visitas autorizadas, detecciones y solicitudes del QR")
    c.caja(842, 1684, 633, 91, "Interfaz del conserje",
           "gui/app.py · Tkinter · resultado y evidencia en vivo\naprueba o rechaza las solicitudes del QR", ty=1712)
    c.linea([(1475, 904), (1500, 904), (1500, 1729), (1482, 1729)])
    c.texto(1490, 1610, "solicitudes", size=12, peso="bold", anchor="end")
    c.texto(1490, 1628, "por aprobar", size=12, peso="bold", anchor="end")
    c.linea([(1000, 1775), (1000, 1822), (375, 1822), (375, 1843)])
    c.etiqueta(700, 1812, "lo que el conserje ingresa o aprueba")
    c.caja(108, 1850, 350, 78, "Registro de visitas", "por carnet, sin biometría", ty=1876)
    c.linea([(208, 1850), (208, 1811)])
    c.etiqueta(227, 1836, "registra", anchor="start")
    c.pildora(125, 1949, 590, 28, "el video y el historial de accesos nunca salen de este recuadro")

    # ---------------- fuera del sistema
    c.linea([(1158, 1775), (1158, 1995), (725, 1995), (725, 2043)])
    c.etiqueta(941, 1985, "lo que el conserje ve")
    c.grupo(58, 2013, 1467, 158, "FUERA DEL SISTEMA · la decisión es humana", color=GRIS_G, fondo="#f3f3f1", ty=2041)
    c.caja(467, 2050, 516, 78, "El conserje decide", "autoriza o deniega · RN-01", ty=2076)
    c.caja(1033, 2050, 400, 78, "Abrir el portón", "acción física", ty=2076)
    c.linea([(983, 2089), (1026, 2089)])
    c.guardar("3-7_arquitectura")


if __name__ == "__main__":
    arquitectura()
