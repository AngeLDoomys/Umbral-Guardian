# -*- coding: utf-8 -*-
"""Dibuja los BPMN de la sección X con el mismo estilo de los originales aprobados.

    py docs/informe/herramientas/bpmn.py [propuesto|inscripcion]

Cada diagrama se describe con coordenadas fijas (centro de cada elemento) y se
dibuja como SVG; Microsoft Edge sin ventana lo convierte a PNG en docs/informe/diagramas.
"""
import html
import os
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
DIAG = os.path.abspath(os.path.join(AQUI, "..", "diagramas"))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

TW, TH = 118, 40          # tamaño de una tarea
GR, ER = 17, 11           # semidiagonal del rombo y radio de los eventos
AZUL, AZUL_F = "#3a64ad", "#e9f0fb"
LINEA = "#3d4047"
FUENTE = "DejaVu Sans, Verdana, sans-serif"


def _texto(x, y, lineas, size=7.6, peso="normal", anchor="middle", color="#1d2230"):
    lineas = lineas.split("\n")
    y0 = y - (len(lineas) - 1) * size * 0.6
    out = [f'<text x="{x}" y="{y0}" font-size="{size}" font-weight="{peso}" text-anchor="{anchor}" '
           f'fill="{color}" font-family="{FUENTE}" dominant-baseline="middle">']
    for i, l in enumerate(lineas):
        out.append(f'<tspan x="{x}" dy="{0 if i == 0 else size * 1.2}">{html.escape(l)}</tspan>')
    return "".join(out) + "</text>"


class Bpmn:
    def __init__(self, ancho, alto, pool, carriles):
        self.w, self.h, self.pool, self.carriles = ancho, alto, pool, carriles
        self.nodos, self.svg_n, self.svg_e = {}, [], []

    # ---- elementos
    def tarea(self, k, x, y, texto, w=TW, h=TH):
        self.nodos[k] = (x, y, w / 2, h / 2)
        self.svg_n.append(f'<rect x="{x - w / 2}" y="{y - h / 2}" width="{w}" height="{h}" rx="7" '
                          f'fill="{AZUL_F}" stroke="{AZUL}" stroke-width="1.3"/>' + _texto(x, y, texto))

    @staticmethod
    def _bajo(x, y, texto):
        n = texto.count("\n")
        return _texto(x, y + ER + 9 + n * 0.6 * 7, texto, size=7, color="#333")

    def inicio(self, k, x, y, texto):
        self.nodos[k] = (x, y, ER, ER)
        self.svg_n.append(f'<circle cx="{x}" cy="{y}" r="{ER}" fill="#d6f0c8" stroke="#5f9e47" stroke-width="1.4"/>'
                          + self._bajo(x, y, texto))

    def fin(self, k, x, y, texto):
        self.nodos[k] = (x, y, ER, ER)
        self.svg_n.append(f'<circle cx="{x}" cy="{y}" r="{ER}" fill="#f8d2d2" stroke="#b83232" stroke-width="2.6"/>'
                          + self._bajo(x, y, texto))

    def compuerta(self, k, x, y, texto="", lx=0, ly=-27, anchor="middle", tipo="x"):
        self.nodos[k] = (x, y, GR, GR)
        d = f"M{x},{y - GR} L{x + GR},{y} L{x},{y + GR} L{x - GR},{y} Z"
        s = f'<path d="{d}" fill="#fbf1c4" stroke="#c7a21f" stroke-width="1.3"/>'
        if tipo == "x":
            a = 6.5
            s += (f'<path d="M{x - a},{y - a} L{x + a},{y + a} M{x + a},{y - a} L{x - a},{y + a}" '
                  f'stroke="#c7a21f" stroke-width="1.6"/>')
        else:
            s += f'<circle cx="{x}" cy="{y}" r="7.5" fill="none" stroke="#c7a21f" stroke-width="1.6"/>'
        if texto:
            s += _texto(x + lx, y + ly, texto, size=7.6, peso="bold", anchor=anchor)
        self.svg_n.append(s)

    # ---- conectores ortogonales
    def _puerto(self, k, lado):
        x, y, hw, hh = self.nodos[k]
        return {"r": (x + hw, y), "l": (x - hw, y), "t": (x, y - hh), "b": (x, y + hh)}[lado]

    def flecha(self, a, b, lados="rl", via=(), etiqueta="", lpos=None, anchor="start", dx1=0):
        p0, pn = self._puerto(a, lados[0]), self._puerto(b, lados[1])
        pn = (pn[0] + dx1, pn[1])
        pts = [p0] + list(via) + [pn]
        horiz = lados[0] in "rl"
        camino = [pts[0]]
        for i in range(1, len(pts)):
            (x1, y1), (x2, y2) = camino[-1], pts[i]
            if x1 != x2 and y1 != y2:
                if i == len(pts) - 1:
                    codo = (x2, y1) if lados[1] in "tb" else (x1, y2)
                else:
                    codo = (x2, y1) if horiz else (x1, y2)
                camino.append(codo)
                horiz = not horiz
            else:
                horiz = y1 == y2
            camino.append(pts[i])
        d = "M" + " L".join(f"{x},{y}" for x, y in camino)
        s = f'<path d="{d}" fill="none" stroke="{LINEA}" stroke-width="1.1" marker-end="url(#m)"/>'
        if etiqueta:
            if lpos is None:
                (x1, y1), (x2, y2) = camino[0], camino[1]
                if y1 == y2:
                    lpos = (x1 + 14, y1 - 6)
                else:
                    lpos = (x1 + 6, y1 + (14 if y2 > y1 else -10))
            s += _texto(lpos[0], lpos[1], etiqueta, size=7, peso="bold", anchor=anchor)
        self.svg_e.append(s)

    # ---- salida
    def svg(self):
        x0, x1 = 20, self.w - 20
        y0, y1 = self.carriles[0][1], self.carriles[-1][2]
        s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
             f'viewBox="0 0 {self.w} {self.h}">',
             f'<defs><marker id="m" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
             f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{LINEA}"/></marker></defs>',
             f'<rect width="{self.w}" height="{self.h}" fill="#fff"/>',
             f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="#fff" stroke="#9aa1ac" stroke-width="1.1"/>',
             f'<rect x="{x0}" y="{y0}" width="18" height="{y1 - y0}" fill="#edf2f8" stroke="#9aa1ac" stroke-width="1.1"/>',
             f'<text transform="translate({x0 + 12},{(y0 + y1) / 2}) rotate(-90)" font-size="9" font-weight="bold" '
             f'text-anchor="middle" font-family="{FUENTE}" fill="#1d2230">{html.escape(self.pool)}</text>']
        for nombre, a, b in self.carriles:
            s.append(f'<rect x="{x0 + 18}" y="{a}" width="{x1 - x0 - 18}" height="{b - a}" fill="none" '
                     f'stroke="#9aa1ac" stroke-width="1.1"/>')
            s.append(f'<rect x="{x0 + 18}" y="{a}" width="16" height="{b - a}" fill="#edf2f8" stroke="#9aa1ac" stroke-width="1.1"/>')
            s.append(f'<text transform="translate({x0 + 29.5},{(a + b) / 2}) rotate(-90)" font-size="8.2" '
                     f'font-weight="bold" text-anchor="middle" font-family="{FUENTE}" fill="#1d2230">{html.escape(nombre)}</text>')
        return "\n".join(s + self.svg_e + self.svg_n + ["</svg>"])

    def guardar(self, nombre, escala=3):
        destino = os.path.join(DIAG, nombre + ".png")
        with open(os.path.join(DIAG, nombre + ".svg"), "w", encoding="utf-8") as f:
            f.write(self.svg())
        pagina = os.path.join(tempfile.mkdtemp(prefix="ug_bpmn_"), "p.html")
        with open(pagina, "w", encoding="utf-8") as f:
            f.write("<!doctype html><meta charset=utf-8><style>body{margin:0}</style>" + self.svg())
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        f"--force-device-scale-factor={escala}", f"--window-size={self.w},{self.h}",
                        f"--screenshot={destino}", "file:///" + pagina.replace("\\", "/")],
                       check=True, capture_output=True, timeout=120)
        print(os.path.basename(destino))


# ======================================================================
def propuesto():
    d = Bpmn(1000, 760, "Condominio Parque Fray Jorge",
             [("Umbral Guardian · nodo de borde", 20, 360), ("Conserjería", 360, 740)])
    # --- sistema
    d.inicio("i", 85, 175, "Se detecta\nmovimiento en\nel acceso")
    d.tarea("cap", 175, 175, "Capturar el fotograma y\ndetectar persona o vehículo")
    d.compuerta("q", 262, 175, "¿Qué se detectó?", tipo="o")
    d.tarea("yun", 345, 95, "Detectar y alinear el\nrostro con YuNet")
    d.tarea("sf", 475, 95, "Calcular el vector facial con\nSFace y compararlo con\nresidentes y visitas", h=46)
    d.compuerta("g1", 560, 95, "¿Coincide con\nalguien inscrito?", lx=-6, ly=34, anchor="end")
    d.tarea("mres", 660, 45, "Marcar como residente")
    d.tarea("mvis", 660, 95, "Marcar como visita\nautorizada")
    d.tarea("mno", 660, 145, "Marcar como no reconocida")
    d.compuerta("j1", 750, 95)
    d.tarea("rr", 840, 95, "Registrar la detección de\nrostro")
    d.tarea("del", 345, 265, "Delimitar la placa en el\nfotograma")
    d.tarea("ocr", 475, 265, "Leer la patente con\nfast-plate-ocr y validar el\nformato chileno", h=46)
    d.compuerta("g2", 560, 265, "¿La patente\nestá inscrita?", lx=-6, ly=36, anchor="end")
    d.tarea("tit", 660, 222, "Mostrar al titular y su\nunidad")
    d.tarea("nor", 660, 310, "Marcar el vehículo como no\nregistrado")
    d.compuerta("j2", 750, 265)
    d.tarea("rp", 840, 265, "Registrar la detección de\npatente")
    d.compuerta("j3", 935, 180, tipo="o")
    d.flecha("i", "cap")
    d.flecha("cap", "q")
    d.flecha("q", "yun", "tl", etiqueta="Persona", lpos=(256, 110), anchor="end")
    d.flecha("q", "del", "bl", etiqueta="Vehículo", lpos=(256, 250), anchor="end")
    d.flecha("yun", "sf")
    d.flecha("sf", "g1")
    d.flecha("g1", "mres", "tl", etiqueta="Residente", lpos=(555, 40), anchor="end")
    d.flecha("g1", "mvis", "rl", etiqueta="Visita", lpos=(579, 89))
    d.flecha("g1", "mno", "bl", etiqueta="No", lpos=(566, 139))
    d.flecha("mres", "j1", "rt")
    d.flecha("mvis", "j1")
    d.flecha("mno", "j1", "rb")
    d.flecha("j1", "rr")
    d.flecha("del", "ocr")
    d.flecha("ocr", "g2")
    d.flecha("g2", "tit", "tl", etiqueta="Sí", lpos=(568, 216))
    d.flecha("g2", "nor", "bl", etiqueta="No", lpos=(568, 304))
    d.flecha("tit", "j2", "rt")
    d.flecha("nor", "j2", "rb")
    d.flecha("j2", "rp")
    d.flecha("rr", "j3", "rt")
    d.flecha("rp", "j3", "rb")
    # --- conserjería
    d.tarea("rev", 130, 455, "Revisar el resultado y aplicar\nel criterio de turno")
    d.flecha("j3", "rev", "rt", via=[(965, 180), (965, 375), (130, 375)])
    d.compuerta("qi", 232, 455, "¿Quién ingresa?", lx=-6, ly=-30, anchor="end")
    d.compuerta("hor", 360, 455, "¿Dentro del horario de apertura\nautomática?", ly=-30)
    d.tarea("abr", 660, 455, "Abrir el portón")
    d.tarea("reg", 800, 455, "Registrar el ingreso: fecha,\nhora y medio de identificación", w=132)
    d.fin("ok", 900, 455, "Ingreso autorizado")
    d.tarea("cit", 290, 545, "Consultar al residente por\ncitófono")
    d.compuerta("cf", 400, 545, "¿El residente confirma\nla visita?", ly=-28)
    d.tarea("rv", 520, 545, "Registrar la visita: RUT, unidad\nde destino y patente", w=134)
    d.tarea("sol", 475, 620, "Solicitar la confirmación del\nresidente titular")
    d.compuerta("ct", 595, 620, "¿El titular\nconfirma?", lx=20, ly=26, anchor="start")
    d.tarea("den", 530, 695, "Denegar el ingreso")
    d.fin("no", 625, 695, "Ingreso denegado")
    d.flecha("rev", "qi")
    d.flecha("qi", "hor", etiqueta="Residente reconocido", lpos=(254, 449))
    d.flecha("qi", "abr", "tt", via=[(232, 400)], etiqueta="Visita autorizada (QR)", lpos=(400, 394))
    d.flecha("qi", "cit", "bl", etiqueta="Persona no reconocida", lpos=(224, 520), anchor="end")
    d.flecha("hor", "abr", etiqueta="Sí", lpos=(500, 449))
    d.flecha("hor", "sol", "bt", via=[(360, 585), (475, 585)], etiqueta="No", lpos=(367, 480))
    d.flecha("cit", "cf")
    d.flecha("cf", "rv", etiqueta="Sí", lpos=(422, 539))
    d.flecha("rv", "abr", "rb", dx1=-25)
    d.flecha("cf", "den", "bl", etiqueta="No", lpos=(406, 685))
    d.flecha("sol", "ct")
    d.flecha("ct", "abr", "rb", dx1=25, etiqueta="Sí", lpos=(632, 614))
    d.flecha("ct", "den", "bt", via=[(595, 662), (530, 662)], etiqueta="No", lpos=(565, 657))
    d.flecha("abr", "reg")
    d.flecha("reg", "ok")
    d.flecha("den", "no")
    d.guardar("bpmn_propuesto")


def inscripcion():
    d = Bpmn(1800, 790, "Condominio Parque Fray Jorge",
             [("Conserjería y Administración", 20, 290),
              ("Umbral Guardian · nodo de borde", 290, 480),
              ("Residente o visita · celular", 480, 625),
              ("Nube del proveedor", 625, 770)])
    # --- inscripción presencial (la aprobada)
    d.inicio("i", 92, 120, "Un residente o\nvisita nuevo pide\nsu inscripción")
    d.compuerta("como", 170, 120, "¿Cómo se inscribe?")
    d.tarea("ficha", 290, 120, "Completar la ficha: RUT,\nnombre y unidad")
    d.tarea("cons", 420, 120, "Presentar y explicar el\nformulario de consentimiento")
    d.compuerta("otg", 512, 120, "¿Otorga el consentimiento?")
    d.compuerta("men", 605, 120, "¿Es menor de 16 años?", ly=28)
    d.tarea("tut", 735, 62, "Registrar al tutor que lo\nautoriza (art. 16 quáter)")
    d.tarea("ros", 855, 120, "Capturar el rostro del\nresidente")
    d.tarea("veh", 985, 120, "Registrar los vehículos del\nresidente")
    d.tarea("neg", 625, 205, "Registrar la negativa y su\nfecha")
    d.fin("fneg", 725, 205, "Inscripción no realizada")
    d.flecha("i", "como")
    d.flecha("como", "ficha", etiqueta="Presencial", lpos=(190, 114))
    d.flecha("ficha", "cons")
    d.flecha("cons", "otg")
    d.flecha("otg", "men", etiqueta="Sí", lpos=(540, 114))
    d.flecha("otg", "neg", "bl", etiqueta="No", lpos=(518, 165))
    d.flecha("neg", "fneg")
    d.flecha("men", "tut", "tl", etiqueta="Sí", lpos=(611, 56))
    d.flecha("men", "ros", etiqueta="No", lpos=(715, 114))
    d.flecha("tut", "ros", "rt")
    d.flecha("ros", "veh")
    d.tarea("pla", 985, 385, "Calcular y almacenar la\nplantilla facial")
    d.tarea("alm", 1122, 385, "Almacenar el consentimiento y\nla cuenta que lo obtuvo", w=134)
    d.fin("fok", 1225, 385, "Residente inscrito")
    d.flecha("veh", "pla", "bt")
    d.flecha("pla", "alm")
    d.flecha("alm", "fok")
    # --- inscripción desde el celular (módulo QR)
    d.tarea("qr", 290, 245, "Generar y entregar la invitación\nQR de residente o visita", w=138)
    d.flecha("como", "qr", "bl", etiqueta="Desde su celular (QR)", lpos=(176, 200))
    d.tarea("esc", 290, 545, "Escanear el QR y abrir el\nformulario")
    d.tarea("lee", 420, 545, "Leer y aceptar el\nconsentimiento")
    d.compuerta("acp", 512, 545, "¿Acepta?")
    d.fin("fnoc", 512, 592, "")
    d.tarea("dat", 625, 545, "Ingresar sus datos y tomar\n5 fotos del rostro")
    d.tarea("env", 755, 545, "Enviar la solicitud")
    d.flecha("qr", "esc", "bt")
    d.flecha("esc", "lee")
    d.flecha("lee", "acp")
    d.flecha("acp", "fnoc", "bt", etiqueta="No: registro no realizado", lpos=(530, 592))
    d.flecha("acp", "dat", etiqueta="Sí", lpos=(534, 539))
    d.flecha("dat", "env")
    d.tarea("val", 870, 690, "Validar la invitación\n(vigente y de un solo uso)")
    d.compuerta("fot", 975, 690, "¿Las fotos tienen\nun rostro claro?", ly=-30)
    d.tarea("vec", 1090, 690, "Calcular los vectores SFace\ny descartar las fotos")
    d.tarea("cif", 1220, 690, "Cifrar la solicitud para el\nnodo y guardarla")
    d.flecha("env", "val", "bl")
    d.flecha("val", "fot")
    d.flecha("fot", "dat", "bb", via=[(975, 745), (625, 745)], etiqueta="No: repetir las fotos",
             lpos=(780, 739))
    d.flecha("fot", "vec", etiqueta="Sí", lpos=(995, 684))
    d.flecha("vec", "cif")
    d.tarea("des", 1395, 385, "Descargar y descifrar la\nsolicitud (consulta cada 60 s)", w=134)
    d.flecha("cif", "des", "rb")
    d.tarea("rsol", 1395, 200, "Revisar la solicitud: datos,\nconsentimiento y fotos")
    d.compuerta("apr", 1545, 200, "¿Aprueba la solicitud?")
    d.tarea("rech", 1660, 200, "Rechazar la solicitud")
    d.fin("frech", 1752, 200, "Solicitud rechazada")
    d.tarea("crea", 1545, 385, "Crear el residente o la visita\nautorizada con sus plantillas", w=134)
    d.fin("fqr", 1660, 385, "Residente o visita\ninscrito")
    d.flecha("des", "rsol", "tb")
    d.flecha("rsol", "apr")
    d.flecha("apr", "rech", etiqueta="No", lpos=(1567, 194))
    d.flecha("rech", "frech")
    d.flecha("apr", "crea", "bt", etiqueta="Sí", lpos=(1552, 240))
    d.flecha("crea", "fqr")
    d.guardar("bpmn_inscripcion")


if __name__ == "__main__":
    for p in sys.argv[1:] or ["propuesto", "inscripcion"]:
        globals()[p]()


