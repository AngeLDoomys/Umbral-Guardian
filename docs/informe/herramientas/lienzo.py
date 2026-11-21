# -*- coding: utf-8 -*-
"""Primitivas SVG con el estilo de los diagramas aprobados del informe (sección X)."""
import html
import os
import subprocess
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
DIAG = os.path.abspath(os.path.join(AQUI, "..", "diagramas"))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
FUENTE = "DejaVu Sans, Verdana, sans-serif"
MONO = "DejaVu Sans Mono, Consolas, monospace"
TINTA, GRIS, LINEA = "#16203a", "#5b6270", "#3d4047"
AZUL, VERDE, OCRE = "#2f5b94", "#1d6b55", "#9a6a12"


def esc(t):
    return html.escape(str(t))


class Lienzo:
    def __init__(self, w, h, fondo="#ffffff"):
        self.w, self.h, self.fondo = w, h, fondo
        self.defs, self.capas = {}, {"fondo": [], "lineas": [], "cajas": [], "texto": []}

    # ---------------------------------------------------------------- texto
    def texto(self, x, y, t, size=12, peso="normal", color=TINTA, anchor="start", mono=False,
              italic=False, capa="texto", interlinea=1.35, subrayado=False):
        lineas = str(t).split("\n")
        fam = MONO if mono else FUENTE
        s = [f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{peso}" fill="{color}" '
             f'text-anchor="{anchor}" font-family="{fam}"'
             + (' font-style="italic"' if italic else "")
             + (' text-decoration="underline"' if subrayado else "") + ">"]
        for i, l in enumerate(lineas):
            s.append(f'<tspan x="{x}" dy="{0 if i == 0 else size * interlinea}">{esc(l)}</tspan>')
        self.capas[capa].append("".join(s) + "</text>")

    def titulo(self, t, sub=None, y=36):
        self.texto(self.w / 2, y, t, size=26, peso="bold", anchor="middle")
        if sub:
            self.texto(self.w / 2, y + 28, sub, size=13.5, color=GRIS, anchor="middle")

    # ---------------------------------------------------------------- marcadores
    def _marca(self, color, tipo):
        k = f"m_{tipo}_{color.strip('#')}"
        if k not in self.defs:
            if tipo == "llena":
                p = f'<path d="M0,0 L12,6 L0,12 z" fill="{color}"/>'
                self.defs[k] = (f'<marker id="{k}" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" '
                                f'markerHeight="12" markerUnits="userSpaceOnUse" orient="auto-start-reverse">{p}</marker>')
                self.defs[k] = self.defs[k].replace('markerWidth="12" markerHeight="12"',
                                                    'markerWidth="20" markerHeight="20"')
            elif tipo == "chica":
                p = f'<path d="M0,0 L10,5 L0,10 z" fill="{color}"/>'
                self.defs[k] = (f'<marker id="{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="11" '
                                f'markerHeight="11" markerUnits="userSpaceOnUse" orient="auto-start-reverse">{p}</marker>')
            else:  # abierta
                p = f'<path d="M1,1 L10,6 L1,11" fill="none" stroke="{color}" stroke-width="1.5"/>'
                self.defs[k] = (f'<marker id="{k}" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="12" '
                                f'markerHeight="12" markerUnits="userSpaceOnUse" orient="auto-start-reverse">{p}</marker>')
        return k

    def linea(self, pts, color=LINEA, ancho=2, guion=None, flecha="llena", inicio=None, capa="lineas"):
        d = "M" + " L".join(f"{x},{y}" for x, y in pts)
        s = f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{ancho}" stroke-linejoin="round"'
        if guion:
            s += f' stroke-dasharray="{guion}"'
        if flecha:
            s += f' marker-end="url(#{self._marca(color, flecha)})"'
        if inicio:
            s += f' marker-start="url(#{self._marca(color, inicio)})"'
        self.capas[capa].append(s + "/>")

    def punto(self, x, y, r=4.5, color=LINEA):
        self.capas["texto"].append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>')

    # ---------------------------------------------------------------- formas
    def grupo(self, x, y, w, h, titulo="", color=AZUL, fondo="#f4f6f9", sub=None, size=17, rx=12,
              ancho=2, tcolor=None, ty=None):
        self.capas["fondo"].append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fondo}" stroke="{color}" '
            f'stroke-width="{ancho}" stroke-dasharray="9 6"/>')
        if titulo:
            ty = ty if ty is not None else y + 30
            self.texto(x + 20, ty, titulo, size=size, peso="bold", color=tcolor or color)
            if sub:
                self.texto(x + 20, ty + 19, sub, size=11, color=GRIS, mono=True)

    def caja(self, x, y, w, h, titulo, sub="", fondo="#ffffff", borde=LINEA, tsize=15.5, ssize=11.5,
             subcolor=GRIS, submono=False, rx=7, ty=None, ancho=1.6, centrado=True):
        self.capas["cajas"].append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fondo}" stroke="{borde}" '
            f'stroke-width="{ancho}"/>')
        cx = x + w / 2 if centrado else x + 16
        an = "middle" if centrado else "start"
        ty = ty if ty is not None else y + 26
        self.texto(cx, ty, titulo, size=tsize, peso="bold", anchor=an)
        if sub:
            self.texto(cx, ty + ssize + 9, sub, size=ssize, color=subcolor, anchor=an, mono=submono)

    def cilindro(self, x, y, w, h, titulo, sub="", fondo="#edf1f6"):
        e = 14
        self.capas["cajas"].append(
            f'<path d="M{x},{y + e} L{x},{y + h - e} A{w / 2},{e} 0 0 0 {x + w},{y + h - e} L{x + w},{y + e}" '
            f'fill="{fondo}" stroke="{LINEA}" stroke-width="1.6"/>'
            f'<ellipse cx="{x + w / 2}" cy="{y + e}" rx="{w / 2}" ry="{e}" fill="#f7f8fa" stroke="{LINEA}" stroke-width="1.6"/>')
        n = sub.count("\n")
        ty = y + h / 2 + 8 - n * 8
        self.texto(x + w / 2, ty, titulo, size=15.5, peso="bold", anchor="middle")
        if sub:
            self.texto(x + w / 2, ty + 22, sub, size=11.5, color=GRIS, anchor="middle")

    def pildora(self, x, y, w, h, t, color="#a33a3a", fondo="#fff"):
        self.capas["cajas"].append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="{fondo}" '
                                   f'stroke="{color}" stroke-width="1.3"/>')
        self.texto(x + w / 2, y + h / 2 + 4.5, t, size=12.5, peso="bold", color=color, anchor="middle")

    def nota(self, x, y, w, h, titulo, cuerpo, borde="#b0841f", fondo="#f9f1df", color="#6b4a08"):
        self.capas["cajas"].append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fondo}" '
                                   f'stroke="{borde}" stroke-width="1.6"/>')
        self.texto(x + 22, y + 29, titulo, size=15, peso="bold", color=color)
        self.texto(x + 22, y + 53, cuerpo, size=12, color=color, interlinea=1.55)

    def etiqueta(self, x, y, t, sub=None, anchor="middle", mono=False, size=12.5):
        self.texto(x, y, t, size=size, peso="bold", anchor=anchor, mono=mono, color="#1f2633")
        if sub:
            self.texto(x, y + 18, sub, size=11.5, anchor=anchor, color="#3b4250")

    # ---------------------------------------------------------------- salida
    def svg(self):
        cuerpo = (self.capas["fondo"] + self.capas["lineas"] + self.capas["cajas"] + self.capas["texto"])
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}"><defs>{"".join(self.defs.values())}</defs>'
                f'<rect width="{self.w}" height="{self.h}" fill="{self.fondo}"/>' + "\n".join(cuerpo) + "</svg>")

    def guardar(self, nombre, escala=2):
        destino = os.path.join(DIAG, nombre + ".png")
        svg = self.svg()
        with open(os.path.join(DIAG, nombre + ".svg"), "w", encoding="utf-8") as f:
            f.write(svg)
        pagina = os.path.join(tempfile.mkdtemp(prefix="ug_dx_"), "p.html")
        with open(pagina, "w", encoding="utf-8") as f:
            f.write("<!doctype html><meta charset=utf-8><style>body{margin:0}</style>" + svg)
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        f"--force-device-scale-factor={escala}", f"--window-size={self.w},{self.h}",
                        f"--screenshot={destino}", "file:///" + pagina.replace("\\", "/")],
                       check=True, capture_output=True, timeout=120)
        print(os.path.basename(destino), self.w * escala, "x", self.h * escala)
