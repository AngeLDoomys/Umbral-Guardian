# -*- coding: utf-8 -*-
"""Topología de comunicación e Infraestructura física (estilo aprobado + registro por QR y SQLite).

    py docs/informe/herramientas/red_infra.py
"""
from lienzo import AZUL, GRIS, LINEA, VERDE, Lienzo


def topologia():
    c = Lienzo(1710, 760)
    c.titulo("Topología de comunicación",
             "Por dónde viaja cada cosa y en qué sentido. Sin especificaciones de equipo: eso va en infraestructura.")
    # red del condominio
    c.grupo(35, 185, 885, 470, "Red del condominio", sub="sin IP pública fija")
    caja = dict(submono=True, subcolor=AZUL, tsize=16, ssize=11.5, ty=None)
    c.caja(78, 270, 257, 72, "Dos cámaras IP", "canales del grabador", ty=297, **{k: v for k, v in caja.items() if k != "ty"})
    c.caja(78, 415, 257, 72, "Grabador", "192.168.1.10", ty=442, submono=True, subcolor=AZUL, tsize=16)
    c.caja(441, 343, 257, 72, "Nodo de borde", "192.168.1.50", ty=370, submono=True, subcolor=AZUL, tsize=16)
    c.caja(441, 538, 257, 72, "Base local · SQLite", "archivo umbral_local.db", ty=565, submono=True,
           subcolor=AZUL, tsize=16, fondo="#edf1f6")
    c.linea([(206, 342), (206, 408)])
    c.etiqueta(285, 368, "RTSP 554", "video continuo", mono=True)
    c.linea([(335, 451), (399, 451), (399, 379), (434, 379)])
    c.etiqueta(388, 318, "RTSP 554", "sólo lectura", mono=True)
    c.linea([(570, 415), (570, 531)])
    c.etiqueta(670, 462, "ARCHIVO LOCAL", "no abre ningún puerto", mono=True)
    # nube
    c.grupo(1018, 185, 657, 470, "Nube del proveedor", color=VERDE, fondo="#f3f7f6", sub="red privada")
    c.caja(1068, 270, 557, 72, "API del plano de control", "escucha en TCP 443", ty=297, submono=True,
           subcolor=AZUL, tsize=16)
    c.grupo(1068, 430, 557, 145, "Red privada · sin salida a internet", color=VERDE, fondo="#e8f2ef", size=13,
            ty=456, rx=8)
    c.caja(1104, 473, 485, 72, "Base central", "sin IP pública", ty=500, submono=True, subcolor=AZUL, tsize=16)
    c.linea([(1346, 342), (1346, 466)])
    c.etiqueta(1446, 398, "TCP 3306", "sólo dentro de la nube", mono=True)
    c.linea([(698, 364), (840, 364), (840, 299), (1061, 299)])
    c.texto(800, 248, "HTTPS 443", size=12.5, peso="bold", anchor="middle", mono=True)
    c.texto(800, 266, "SALE cada 6 h · cuentas y licencia\ncada 60 s · solicitudes del QR",
            size=11.5, anchor="middle", color="#3b4250", interlinea=1.4)
    # celular
    c.caja(1180, 86, 445, 66, "Celular del residente o visita", "datos móviles o Wi-Fi · fuera del condominio",
           ty=112, tsize=16, fondo="#fff8ec", borde="#9a6a12")
    c.linea([(1400, 152), (1400, 263)])
    c.texto(1412, 232, "HTTPS 443", size=12.5, peso="bold", mono=True)
    c.texto(1412, 250, "formulario del QR", size=11.5, color="#3b4250")
    c.nota(35, 672, 1640, 70, "El video nunca sale del condominio.",
           "Se procesa en la caseta y sólo sube el registro del ingreso. La conexión del nodo siempre la abre el nodo: "
           "desde internet no hay forma de entrar. El celular sólo habla con la nube, nunca con el nodo.")
    c.guardar("topologia")


def _caja3d(c, x, y, w, h, titulo, lineas, sello, interior=None):
    d = 12
    c.capas["cajas"].append(
        f'<path d="M{x},{y + d} L{x + d},{y} L{x + w},{y} L{x + w - d},{y + d} Z" fill="#dfe3e9" stroke="{LINEA}" stroke-width="1.6"/>'
        f'<path d="M{x + w - d},{y + d} L{x + w},{y} L{x + w},{y + h - d} L{x + w - d},{y + h} Z" fill="#dfe3e9" stroke="{LINEA}" stroke-width="1.6"/>'
        f'<rect x="{x}" y="{y + d}" width="{w - d}" height="{h - d}" fill="#fff" stroke="{LINEA}" stroke-width="1.6"/>')
    c.texto(x + 14, y + d + 30, titulo, size=17, peso="bold")
    c.texto(x + 14, y + d + 54, lineas, size=12, color=GRIS, interlinea=1.4)
    if interior:
        ix, iy, iw = x + 10, y + d + 108, w - d - 20
        c.capas["cajas"].append(f'<rect x="{ix}" y="{iy}" width="{iw}" height="40" rx="4" fill="#edf0f4" '
                                f'stroke="{LINEA}" stroke-width="1.1"/>')
        c.texto(ix + 8, iy + 15, "«entorno de ejecución»", size=10, color=GRIS, italic=True)
        c.texto(ix + 8, iy + 32, interior, size=12.5, peso="bold")
    colores = {"YA EXISTE": ("#e4f3ea", "#2f8a57"), "SE COMPRA": ("#fdf1dc", "#b07a17"),
               "SE ARRIENDA": ("#e2f2ef", "#1f7a6a"), "NO SE COMPRA": ("#e4f3ea", "#2f8a57")}
    f, b = colores[sello]
    bw = 14 + len(sello) * 8.4
    bx, by = x + w - d - bw - 12, y + h - 34
    c.capas["cajas"].append(f'<rect x="{bx}" y="{by}" width="{bw}" height="24" rx="12" fill="{f}" stroke="{b}" stroke-width="1.5"/>')
    c.texto(bx + bw / 2, by + 16.5, sello, size=11.5, peso="bold", color=b, anchor="middle")


def infraestructura():
    c = Lienzo(1930, 700)
    c.titulo("Infraestructura física",
             "Qué equipo hay, dónde está y cuál se compra. Sin protocolos ni puertos: eso va en topología.",
             y=36)
    c.grupo(33, 100, 419, 430, "En el pórtico")
    c.grupo(492, 100, 675, 430, "En la caseta de conserjería")
    c.grupo(1207, 100, 378, 430, "En la nube")
    c.grupo(1625, 100, 272, 430, "En manos de cada persona", color="#9a6a12", fondo="#fdf8ef", size=15.5)
    _caja3d(c, 67, 163, 362, 125, "Dos cámaras IP", "una vehicular y una peatonal\nconectadas al grabador", "YA EXISTE")
    _caja3d(c, 67, 322, 362, 125, "Portón y citófono", "ya instalados en el condominio\nel proyecto no los interviene",
            "YA EXISTE")
    _caja3d(c, 520, 163, 267, 133, "Grabador de video", "Hikvision · ocho canales\nno se configura\nni se reemplaza",
            "YA EXISTE")
    _caja3d(c, 520, 330, 267, 117, "Cámara USB", "sólo para enrolar\nresidentes en la caseta", "SE COMPRA")
    _caja3d(c, 884, 163, 247, 200, "Nodo de borde", "PC dedicado · Windows\nGPU NVIDIA GTX 1650 Ti\nsostiene el SLA-02",
            "SE COMPRA", interior="SQLite · umbral_local.db")
    _caja3d(c, 884, 390, 247, 101, "Router del condominio", "fibra · reparte la red", "YA EXISTE")
    _caja3d(c, 1235, 178, 335, 141, "Servidor de aplicación",
            "Amazon EC2\naloja la API y el formulario\ndel registro por QR", "SE ARRIENDA")
    _caja3d(c, 1235, 352, 335, 134, "Base de datos central", "Amazon RDS\nsólo administración", "SE ARRIENDA")
    _caja3d(c, 1645, 178, 232, 168, "Celular", "del residente o la visita\nabre el QR y envía\nsus datos y fotos",
            "NO SE COMPRA")
    # conexiones
    c.linea([(418, 228), (472, 228), (472, 235), (520, 235)], flecha=None)
    c.punto(418, 228); c.punto(520, 235)
    c.etiqueta(472, 199, "cable de red")
    c.linea([(776, 204), (829, 204), (829, 442), (884, 442)], flecha=None)
    c.punto(776, 204); c.punto(884, 442)
    c.etiqueta(851, 262, "cable de red")
    c.linea([(776, 394), (802, 394), (802, 235), (884, 235)], flecha=None)
    c.punto(776, 394); c.punto(884, 235)
    c.etiqueta(803, 364, "USB")
    c.linea([(1002, 363), (1002, 400)], flecha=None)
    c.punto(1002, 363); c.punto(1002, 400)
    c.etiqueta(1002, 386, "cable o WiFi")
    c.linea([(1121, 442), (1173, 442), (1173, 281), (1235, 281)], flecha=None)
    c.punto(1121, 442); c.punto(1235, 281)
    c.etiqueta(1173, 251, "internet")
    c.linea([(1645, 262), (1572, 262)], flecha=None)
    c.punto(1645, 262); c.punto(1572, 262)
    c.etiqueta(1608, 251, "internet")
    c.nota(33, 556, 1864, 118, "Todo cuelga del router: una sola red.",
           "El grabador y el PC cuelgan los dos del router, así que el PC le pide el video al grabador por la misma red "
           "por la que después sale a internet. No hay cable directo entre ellos.\n"
           "Y no se compra ninguna cámara: las dos del ingreso ya existen. Del proyecto sale sólo el PC dedicado y la cámara "
           "de enrolar.\n"
           "El registro por QR no agrega equipo: cada residente o visita usa su propio celular, que se conecta sólo a la nube.")
    c.guardar("infraestructura")


if __name__ == "__main__":
    topologia()
    infraestructura()
