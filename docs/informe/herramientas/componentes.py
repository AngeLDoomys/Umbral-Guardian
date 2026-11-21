# -*- coding: utf-8 -*-
"""Componentes de software e interfaces (estilo aprobado + registro por QR y SQLite).

    py docs/informe/herramientas/componentes.py
"""
from lienzo import Lienzo

VERDE_C, AZUL_C, AMAR_C, GRIS_C = "#d9eed3", "#e7eef9", "#faf0c8", "#edf0f4"
L_VERDE, L_AZUL, L_MORADO = "#1d7a3e", "#1f3a68", "#7a3a9a"
ETQ = "#1f4f8f"


def _paquete(c, x, y, w, h, titulo, tab):
    c.capas["fondo"].append(
        f'<path d="M{x},{y + 22} L{x},{y} L{x + tab},{y} L{x + tab},{y + 22} L{x + w},{y + 22} L{x + w},{y + h} '
        f'L{x},{y + h} Z" fill="#fff" stroke="#3a64ad" stroke-width="1.8" stroke-dasharray="9 6"/>')
    c.texto(x + 12, y + 17, titulo, size=13.5, peso="bold", color="#2f5b94")


def _comp(c, x, y, w, h, nombre, sub, fondo, estereo="component"):
    c.capas["cajas"].append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{fondo}" '
                            f'stroke="#2d3340" stroke-width="1.3"/>')
    if estereo == "component":
        ix, iy = x + w - 24, y + 7
        c.capas["cajas"].append(f'<rect x="{ix + 3}" y="{iy}" width="15" height="13" fill="#fff" stroke="#2d3340" stroke-width="1"/>'
                                f'<rect x="{ix}" y="{iy + 2.5}" width="6" height="3" fill="#fff" stroke="#2d3340" stroke-width="1"/>'
                                f'<rect x="{ix}" y="{iy + 7.5}" width="6" height="3" fill="#fff" stroke="#2d3340" stroke-width="1"/>')
    c.texto(x + w / 2, y + 15, f"«{estereo}»", size=9.5, italic=True, color="#59606c", anchor="middle")
    c.texto(x + w / 2, y + 32, nombre, size=13.5, peso="bold", anchor="middle")
    if sub:
        c.texto(x + w / 2, y + 46, sub, size=9.5, color="#59606c", anchor="middle", interlinea=1.25)


def _interfaz(c, cx, cy, hacia_x, nombre, lx=None, ly=None, anchor="end"):
    c.capas["cajas"].append(f'<line x1="{cx + (8 if hacia_x > cx else -8)}" y1="{cy}" x2="{hacia_x}" y2="{cy}" '
                            f'stroke="#2d3340" stroke-width="1.4"/>'
                            f'<circle cx="{cx}" cy="{cy}" r="8" fill="#fff" stroke="#2d3340" stroke-width="1.6"/>')
    c.texto(lx if lx is not None else cx + 8, ly if ly is not None else cy - 13, nombre, size=11.5,
            peso="bold", color=ETQ, anchor=anchor)


def _dep(c, pts, color):
    c.linea(pts, color=color, ancho=1.8, guion="7 5", flecha="abierta")


def componentes():
    c = Lienzo(2050, 900)
    c.titulo("Componentes de software e interfaces", y=34)
    _paquete(c, 32, 64, 1483, 820, "Nodo de borde «subsystem»", 236)
    _paquete(c, 1530, 64, 470, 820, "Plano de control en la nube «subsystem»", 296)

    # ---- componentes del nodo
    _comp(c, 71, 129, 220, 64, "InterfazConserjeria", "gui/app.py · Tkinter\nvistas según el rol · incluye Registros", VERDE_C)
    _comp(c, 440, 129, 220, 78, "MotorVision", "engine/security_engine.py\norquesta el lazo · un hilo por cámara\nreverifica la identidad cada 3 s", VERDE_C)
    _comp(c, 440, 278, 220, 65, "ServicioSesion", "core/session.py · PBKDF2\nvalida local si no hay enlace", AZUL_C)
    _comp(c, 440, 401, 220, 65, "ServicioLicencia", "core/licencia.py\nverifica la firma con clave pública", AZUL_C)
    _comp(c, 440, 530, 220, 56, "GeneradorReportes", "reports/report_generator.py", AZUL_C)
    _comp(c, 440, 650, 220, 80, "ClienteRegistroMovil", "core/registro_remoto.py\nconsulta la nube cada 60 s\nguarda las solicitudes por aprobar", AZUL_C)
    _comp(c, 808, 129, 220, 63, "AdaptadorCaptura", "core/camera_manager.py\nRTSP doble canal y USB sobre OpenCV", AMAR_C)
    _comp(c, 808, 220, 220, 62, "DetectorObjetos", "RF-DETR Nano · personas y vehículos\nseguidor propio por IoU entre fotogramas", AMAR_C)
    _comp(c, 808, 311, 220, 62, "ReconocimientoFacial", "core/face_utils.py · vía OpenCV\nYuNet detecta · SFace representa en 128-d", AMAR_C)
    _comp(c, 808, 401, 220, 71, "LectorPatentes", "core/plate_utils.py\nsegundo detector delimita la placa\nfast-plate-ocr lee · lector único", AMAR_C)
    _comp(c, 808, 511, 220, 62, "ClienteNube", "core/cloud.py\nHTTPS · cada seis horas", AZUL_C)
    _comp(c, 808, 650, 220, 62, "Cifrado", "core/cifrado.py\nX25519 + HKDF + AES-256-GCM", AMAR_C)
    _comp(c, 1177, 323, 220, 65, "AccesoDatos", "database.py\núnica puerta a la persistencia", AZUL_C)
    _comp(c, 1177, 479, 220, 55, "umbral_local", "SQLite · veinte tablas", GRIS_C, estereo="database")
    # ---- componentes de la nube
    _comp(c, 1600, 149, 336, 64, "ApiCentral", "servidor/api.py · Flask\n/api/login · /api/nodo/sincronizar · /api/registro", AZUL_C)
    _comp(c, 1600, 291, 336, 64, "FirmadorLicencia", "Ed25519 · clave privada\nfirma la licencia del condominio", AZUL_C)
    _comp(c, 1600, 433, 336, 62, "AccesoDatosCentral", "servidor/central_db.py", AZUL_C)
    _comp(c, 1600, 582, 336, 55, "umbral_central", "MySQL en RDS · nueve tablas", GRIS_C, estereo="database")
    _comp(c, 1600, 700, 320, 72, "RegistroMovil", "servidor/registro_movil.py · formulario del QR\ncalcula el vector SFace y descarta la foto\ncifra la solicitud para el nodo", AZUL_C)

    # ---- interfaces
    _interfaz(c, 414, 145, 440, "IMonitoreo")
    _interfaz(c, 414, 310, 440, "IAutenticacion")
    _interfaz(c, 414, 433, 440, "IVerificacionLicencia")
    _interfaz(c, 414, 558, 440, "IReportes")
    _interfaz(c, 414, 685, 440, "IRegistroMovil")
    _interfaz(c, 782, 160, 808, "ICaptura")
    _interfaz(c, 782, 251, 808, "IDeteccionObjetos")
    _interfaz(c, 782, 342, 808, "IReconocimiento")
    _interfaz(c, 782, 436, 808, "ILecturaPatente")
    _interfaz(c, 782, 542, 808, "ISincronizacion")
    _interfaz(c, 782, 681, 808, "ICifrado")
    _interfaz(c, 1151, 355, 1177, "IPersistencia")
    _interfaz(c, 1574, 181, 1600, "IApiCentral")
    _interfaz(c, 1574, 323, 1600, "IFirmaDigital", lx=1566, ly=300)
    _interfaz(c, 1574, 464, 1600, "IPersistenciaCentral", lx=1582, ly=451)
    _interfaz(c, 1960, 736, 1920, "IFormularioQR", lx=1960, ly=714, anchor="middle")
    c.texto(1960, 760, "celular\nHTTPS 443", size=10, color="#59606c", anchor="middle")

    # ---- dependencias de la interfaz (verde)
    _dep(c, [(291, 145), (405, 145)], L_VERDE)
    _dep(c, [(291, 160), (362, 160), (362, 310), (405, 310)], L_VERDE)
    _dep(c, [(291, 172), (336, 172), (336, 433), (405, 433)], L_VERDE)
    _dep(c, [(291, 184), (317, 184), (317, 558), (405, 558)], L_VERDE)
    _dep(c, [(180, 193), (180, 685), (405, 685)], L_VERDE)
    # ---- dependencias del motor (azul oscuro)
    _dep(c, [(660, 160), (773, 160)], L_AZUL)
    _dep(c, [(660, 175), (763, 175), (763, 251), (773, 251)], L_AZUL)
    _dep(c, [(660, 186), (743, 186), (743, 342), (773, 342)], L_AZUL)
    _dep(c, [(660, 196), (723, 196), (723, 436), (773, 436)], L_AZUL)
    _dep(c, [(550, 129), (550, 106), (1131, 106), (1131, 347), (1142, 352)], L_AZUL)
    # ---- dependencias de los servicios (morado)
    _dep(c, [(660, 298), (1118, 298), (1118, 355), (1142, 355)], L_MORADO)
    _dep(c, [(660, 323), (692, 323), (692, 542), (773, 542)], L_MORADO)
    _dep(c, [(660, 453), (679, 453), (679, 630), (1105, 630), (1105, 359), (1142, 357)], L_MORADO)
    _dep(c, [(660, 575), (1092, 575), (1092, 362), (1142, 358)], L_MORADO)
    _dep(c, [(660, 681), (773, 681)], L_MORADO)
    _dep(c, [(550, 730), (550, 790), (1080, 790), (1080, 366), (1142, 360)], L_MORADO)
    _dep(c, [(1028, 562), (1045, 562), (1045, 760), (1460, 760), (1460, 181), (1565, 181)], L_MORADO)
    _dep(c, [(620, 730), (620, 840), (1475, 840), (1475, 192), (1566, 186)], L_MORADO)
    c.texto(1450, 650, "HTTPS 443", size=12, peso="bold", color="#1d6b55", anchor="end")
    c.texto(1450, 667, "TLS 1.3 · saliente", size=10, color="#59606c", anchor="end")
    # ---- nube
    _dep(c, [(1760, 213), (1760, 250), (1574, 250), (1574, 314)], "#3d4450")
    _dep(c, [(1600, 200), (1548, 200), (1548, 464), (1565, 464)], "#3d4450")
    _dep(c, [(1600, 745), (1538, 745), (1538, 470), (1566, 467)], "#3d4450")
    _dep(c, [(1287, 388), (1287, 479)], "#3d4450")
    c.texto(1297, 438, "«use» · sqlite3 embebido", size=10.5, italic=True, color="#4a4f5a")
    _dep(c, [(1760, 495), (1760, 582)], "#3d4450")
    c.texto(1772, 542, "«use»", size=10.5, italic=True, color="#4a4f5a")
    c.guardar("3-8_componentes")


if __name__ == "__main__":
    componentes()
