# -*- coding: utf-8 -*-
"""Diagramas de casos de uso con el estilo aprobado (actor UML, elipses, «include»/«extend»).

    py docs/informe/herramientas/casos_uso.py
"""
import math

from lienzo import GRIS, LINEA, Lienzo

ELIPSE_F, ELIPSE_B = "#e8f0fb", "#2f5b94"


def _borde(cx, cy, rx, ry, px, py):
    dx, dy = px - cx, py - cy
    s = 1 / math.sqrt((dx / rx) ** 2 + (dy / ry) ** 2)
    return cx + dx * s, cy + dy * s


def _entrada(cx, cy, rx, ry, ax, ay):
    """Primer punto del borde de la elipse en la recta desde el actor hacia su lado izquierdo."""
    tx, ty = cx - rx * 0.45, cy
    dx, dy = tx - ax, ty - ay
    ux, uy = ax - cx, ay - cy
    a = (dx / rx) ** 2 + (dy / ry) ** 2
    b = 2 * (ux * dx / rx ** 2 + uy * dy / ry ** 2)
    k = (ux / rx) ** 2 + (uy / ry) ** 2 - 1
    t = (-b - math.sqrt(b * b - 4 * a * k)) / (2 * a)
    return ax + dx * t, ay + dy * t


def _elipse(c, cx, cy, rx, ry, texto, ext=None):
    c.capas["cajas"].append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{ELIPSE_F}" '
                            f'stroke="{ELIPSE_B}" stroke-width="1.5"/>')
    if ext:
        c.texto(cx, cy - 22, texto, size=12, anchor="middle")
        c.capas["cajas"].append(f'<line x1="{cx - rx * 0.72}" y1="{cy - 10}" x2="{cx + rx * 0.72}" y2="{cy - 10}" '
                                f'stroke="{ELIPSE_B}" stroke-width="1" stroke-dasharray="4 3"/>')
        c.texto(cx, cy + 6, "puntos de extensión", size=10, anchor="middle", italic=True, color=GRIS)
        c.texto(cx, cy + 22, ext, size=10.5, anchor="middle")
    else:
        n = texto.count("\n")
        c.texto(cx, cy + 4 - n * 8, texto, size=12, anchor="middle")


def _actor(c, x, y, nombre):
    s = (f'<circle cx="{x}" cy="{y - 44}" r="14" fill="#fff" stroke="#2d3340" stroke-width="2"/>'
         f'<path d="M{x},{y - 30} L{x},{y + 6} M{x - 24},{y - 16} L{x + 24},{y - 16} '
         f'M{x},{y + 6} L{x - 20},{y + 38} M{x},{y + 6} L{x + 20},{y + 38}" stroke="#2d3340" stroke-width="2" fill="none"/>')
    c.capas["cajas"].append(s)
    c.texto(x, y + 62, nombre, size=13, peso="bold", anchor="middle", color="#2d3340")


def caso_uso(nombre, sistema, actor, izquierda, derecha=(), relaciones=(), notas=(), pie="", ancho=1180):
    """izquierda: [(texto, punto_extension|None)]; derecha: {clave: (texto, y)};
    relaciones: [(indice_izq, clave_der, 'include'|'extend')]; notas: [(clave_der, texto)]."""
    lx, lrx, ry, ryx, gap = 520, 128, 30, 56, 30
    y, pos = 110, []
    for texto, ext in izquierda:
        r = ryx if ext else ry
        y += r
        pos.append((lx, y, lrx, r))
        y += r + gap
    alto_sis = y + 10
    h = alto_sis + (70 if pie else 40)
    c = Lienzo(ancho, h)
    bx, bw = 230, ancho - 270
    c.capas["fondo"].append(f'<rect x="{bx}" y="40" width="{bw}" height="{alto_sis - 40}" fill="#fff" '
                            f'stroke="#8f96a2" stroke-width="1.4"/>'
                            f'<line x1="{bx}" y1="72" x2="{bx + bw}" y2="72" stroke="#8f96a2" stroke-width="1.2"/>')
    c.texto(bx + bw / 2, 61, sistema, size=13.5, peso="bold", anchor="middle", color="#1f3a68")
    ay = (110 + alto_sis) / 2 - 20
    ax = 90
    _actor(c, ax, ay, actor)
    for (cx, cy, rx, r), (texto, ext) in zip(pos, izquierda):
        _elipse(c, cx, cy, rx, r, texto, ext)
        px, py = _entrada(cx, cy, rx, r, ax + 18, ay - 16)
        c.linea([(ax + 18, ay - 16), (px, py)], color=LINEA, ancho=1.4, flecha=None)
    rx2, rcx = 120, ancho - 270 + 230 - 170
    der = {}
    for k, (texto, cy) in dict(derecha).items():
        if isinstance(cy, tuple):
            cy = (pos[cy[0]][1] + pos[cy[1]][1]) / 2
        elif cy < 0:
            cy = pos[-cy - 1][1]
        der[k] = (rcx, cy)
        _elipse(c, rcx, cy, rx2, 36, texto)
    for i, k, tipo in relaciones:
        cx, cy, rx, r = pos[i]
        dx, dy = der[k]
        p1 = _borde(cx, cy, rx, r, dx, dy)
        p2 = _borde(dx, dy, rx2, 36, cx, cy)
        a, b = (p1, p2) if tipo == "include" else (p2, p1)
        c.linea([a, b], color="#3d4450", ancho=1.3, guion="6 4", flecha="abierta")
        c.texto((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 - 9, f"«{tipo}»", size=11, peso="bold",
                anchor="middle", color="#3d4450")
    for k, texto in notas:
        dx, dy = der[k]
        x0, y0, w0, h0 = dx - 132, dy + 48, 264, 58
        c.capas["cajas"].append(f'<rect x="{x0}" y="{y0}" width="{w0}" height="{h0}" fill="#fffbea" stroke="none"/>'
                                f'<path d="M{x0 + 8},{y0} L{x0},{y0} L{x0},{y0 + h0} L{x0 + 8},{y0 + h0}" '
                                f'fill="none" stroke="#8f96a2" stroke-width="1.2"/>')
        c.texto(dx, y0 + 17, texto, size=10.5, anchor="middle", color="#4a4f5a", interlinea=1.3)
    if pie:
        c.texto(bx, alto_sis + 32, pie, size=11.5, italic=True, color="#59606c")
    c.guardar(nombre)


def conserje():
    izq = [("Iniciar sesión", None),
           ("Monitorear el acceso de personas", None),
           ("Monitorear el acceso de vehículos", None),
           ("Registrar una visita", None),
           ("Marcar la salida de una visita", None),
           ("Buscar un residente por fotografía", "consulta del historial"),
           ("Generar una invitación QR", None),
           ("Revisar una solicitud de registro", "aprobación de la solicitud"),
           ("Consultar las visitas autorizadas", None)]
    caso_uso("cu_conserje", "Umbral Guardian", "Conserje", izq,
             derecha={"det": ("Registrar la detección", (1, 2)),"hist": ("Consultar el historial", -6),
                      "crea": ("Crear el residente o la\nvisita autorizada", -8)},
             relaciones=[(1, "det", "include"), (2, "det", "include"), (5, "hist", "extend"),
                         (7, "crea", "extend")],
             notas=[("hist", "Condición: el conserje pide ver el historial\ndel residente encontrado. Punto de extensión:\nconsulta del historial."),
                    ("crea", "Condición: los datos, el consentimiento\ny las fotos son válidos. Punto de extensión:\naprobación de la solicitud.")],
             pie="Nota. La sincronización con la nube es responsabilidad interna de «Iniciar sesión» y se detalla en su "
                 "descripción textual, no en el diagrama.")


def administrador():
    izq = [("Iniciar sesión", None),
           ("Registrar un residente", "captura de la plantilla facial"),
           ("Administrar los vehículos del\nresidente", None),
           ("Dar de baja a un residente", None),
           ("Administrar las cámaras y las zonas", None),
           ("Generar reportes de acceso", None),
           ("Atender solicitudes de derechos del\ntitular", None),
           ("Generar una invitación QR", None),
           ("Revisar una solicitud de registro", "aprobación de la solicitud"),
           ("Administrar las visitas autorizadas", None)]
    caso_uso("cu_administrador", "Umbral Guardian", "Administrador del\ncondominio", izq,
             derecha={"cap": ("Capturar la plantilla facial", -2),
                      "crea": ("Crear el residente o la\nvisita autorizada", -9)},
             relaciones=[(1, "cap", "extend"), (8, "crea", "extend")],
             notas=[("cap", "Condición: el residente otorga el\nconsentimiento informado. Punto de extensión:\ncaptura de la plantilla facial."),
                    ("crea", "Condición: los datos, el consentimiento\ny las fotos son válidos. Punto de extensión:\naprobación de la solicitud.")],
             pie="Nota. La obtención del consentimiento forma parte de «Registrar un residente»: no se dibuja como caso "
                 "incluido porque ningún otro caso de uso lo comparte.")


def residente_visita():
    izq = [("Abrir la invitación QR", None),
           ("Enviar la solicitud de registro", None)]
    caso_uso("cu_residente_visita", "Umbral Guardian · registro móvil", "Residente o visita", izq,
             derecha={"con": ("Otorgar el consentimiento\ninformado", 125), "fot": ("Tomar las fotos del rostro", 245)},
             relaciones=[(1, "con", "include"), (1, "fot", "include")],
             pie="Nota. Usa su propio celular, sin iniciar sesión ni instalar una aplicación: el enlace del QR vence y "
                 "sirve una sola vez.\nLas fotos se descartan en la nube después de calcular el vector facial.")


if __name__ == "__main__":
    conserje()
    administrador()
    residente_visita()
