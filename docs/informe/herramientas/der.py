# -*- coding: utf-8 -*-
"""DER local (SQLite) y DER central (MySQL) con el estilo oscuro de draw.io de los originales.

    py docs/informe/herramientas/der.py

Las columnas se leen del esquema real (sin datos): la base local con PRAGMA y la central desde sql/central.sql.
"""
import os
import re
import sqlite3
import sys

from lienzo import Lienzo, esc

AQUI = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(AQUI, "..", "..", ".."))
sys.path.insert(0, ROOT)
import config  # noqa: E402

FONDO, TRAZO, LETRA = "#161616", "#e8e8e8", "#f2f2f2"
FUENTE = "Helvetica, Arial, sans-serif"
CAB, FILA = 30, 24


# ------------------------------------------------------------------ esquemas
def esquema_local():
    c = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    tablas = {}
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        fks = {r[3]: r[2] for r in c.execute(f"PRAGMA foreign_key_list({t})")}
        uks = set()
        for _, nombre, unico, origen, _p in c.execute(f"PRAGMA index_list({t})"):
            if unico and origen != "pk":
                cols = [r[2] for r in c.execute(f"PRAGMA index_info('{nombre}')")]
                if len(cols) == 1:
                    uks.add(cols[0])
        cols = []
        for _, col, tipo, _n, _d, pk in c.execute(f"PRAGMA table_info({t})"):
            clave = "PK" if pk else "FK" if col in fks else "UK" if col in uks else ""
            cols.append((clave, col, (tipo or "text").lower()))
        tablas[t] = (_ordenar(cols), fks)
    c.close()
    return tablas


def esquema_central():
    sql = open(os.path.join(ROOT, "sql", "central.sql"), encoding="utf-8").read()
    tablas = {}
    for nombre, cuerpo in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\) ENGINE", sql, re.S):
        fks = {col: ref for col, ref in re.findall(r"FOREIGN KEY \((\w+)\)\s*REFERENCES (\w+)", cuerpo)}
        if not fks:
            fks = {}
        for col, ref in re.findall(r"FOREIGN KEY \((\w+)\)\s*\n\s*REFERENCES (\w+)", cuerpo):
            fks[col] = ref
        cols = []
        for col, tipo, resto in re.findall(r"^\s{4}(\w+)\s+([A-Z]+)(.*)$", cuerpo, re.M):
            if col in ("CONSTRAINT", "INDEX", "UNIQUE", "PRIMARY", "KEY"):
                continue
            clave = "PK" if "PRIMARY KEY" in resto else "FK" if col in fks else "UK" if "UNIQUE" in resto else ""
            cols.append((clave, col, tipo.lower()))
        tablas[nombre] = (_ordenar(cols), fks)
    return tablas


def _ordenar(cols):
    orden = {"PK": 0, "FK": 1, "UK": 2, "": 3}
    return sorted(cols, key=lambda c: orden[c[0]])


# ------------------------------------------------------------------ dibujo
class Der:
    def __init__(self, tablas, posiciones, ancho_tabla, filas_y, alto):
        self.t, self.pos, self.w = tablas, posiciones, ancho_tabla
        self.filas_y = filas_y                      # y de inicio de cada fila de tablas
        self.alto = alto
        global IZQ
        IZQ = max(46, 12 + 6.4 * max(len(c[2]) for cols, _ in tablas.values() for c in cols if not c[0]))
        self.puertos, self.bandas, self.callejones = {}, {}, {}
        ancho = max(x for x, _ in posiciones.values()) + ancho_tabla + 50
        self.c = Lienzo(ancho, alto, fondo=FONDO)

    def _fila(self, t):
        y = self.pos[t][1]
        return max(i for i, fy in enumerate(self.filas_y) if y >= fy)

    def _alto(self, t):
        return CAB + FILA * len(self.t[t][0])

    def _puerto(self, t, lado):
        x, y = self.pos[t]
        k = self.puertos.setdefault((t, lado), 0)
        self.puertos[(t, lado)] = k + 1
        px = x + 30 + k * 22 if lado == "b" else x + self.w - 30 - k * 22
        return px, (y + self._alto(t) if lado == "b" else y)

    def _banda(self, fila):
        """Banda horizontal libre debajo de la fila indicada."""
        k = self.bandas.setdefault(fila, 0)
        self.bandas[fila] = k + 1
        fondo = max(self.pos[t][1] + self._alto(t) for t in self.pos if self._fila(t) == fila)
        return fondo + 24 + k * 8

    def _callejon(self, x_tabla):
        k = self.callejones.setdefault(x_tabla, 0)
        self.callejones[x_tabla] = k + 1
        return x_tabla - 12 - k * 7

    def tabla(self, t):
        c, (x, y), w = self.c, self.pos[t], self.w
        cols = self.t[t][0]
        h = self._alto(t)
        s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{FONDO}" stroke="{TRAZO}" stroke-width="1.2"/>',
             f'<line x1="{x}" y1="{y + CAB}" x2="{x + w}" y2="{y + CAB}" stroke="{TRAZO}" stroke-width="1.2"/>',
             f'<line x1="{x + IZQ}" y1="{y + CAB}" x2="{x + IZQ}" y2="{y + h}" stroke="{TRAZO}" stroke-width="1"/>',
             f'<text x="{x + w / 2}" y="{y + 20}" font-size="12.5" font-weight="bold" text-anchor="middle" '
             f'fill="{LETRA}" font-family="{FUENTE}">{esc(t.upper())}</text>']
        for i, (clave, col, tipo) in enumerate(cols):
            ry = y + CAB + i * FILA
            if clave:
                s.append(f'<line x1="{x}" y1="{ry + FILA}" x2="{x + w}" y2="{ry + FILA}" stroke="{TRAZO}" stroke-width="1"/>')
                s.append(f'<text x="{x + IZQ / 2}" y="{ry + 16}" font-size="11.5" font-weight="bold" text-anchor="middle" '
                         f'fill="{LETRA}" font-family="{FUENTE}">{clave}</text>')
                s.append(f'<text x="{x + IZQ + 8}" y="{ry + 16}" font-size="11.5" font-weight="bold" '
                         f'text-decoration="underline" fill="{LETRA}" font-family="{FUENTE}">{esc(col)} ({esc(tipo)})</text>')
            else:
                s.append(f'<text x="{x + IZQ / 2}" y="{ry + 16}" font-size="10.5" text-anchor="middle" '
                         f'fill="{LETRA}" font-family="{FUENTE}">{esc(tipo)}</text>')
                s.append(f'<text x="{x + IZQ + 8}" y="{ry + 16}" font-size="11.5" fill="{LETRA}" '
                         f'font-family="{FUENTE}">{esc(col)}</text>')
        c.capas["cajas"].append("".join(s))

    def _uno(self, x, y, hacia):            # || en el padre
        d = 1 if hacia == "abajo" else -1
        return (f'<path d="M{x - 7},{y + d * 8} L{x + 7},{y + d * 8} M{x - 7},{y + d * 13} L{x + 7},{y + d * 13}" '
                f'stroke="{TRAZO}" stroke-width="1.3"/>')

    def _muchos(self, x, y, desde):         # o< en el hijo
        d = -1 if desde == "arriba" else 1
        return (f'<path d="M{x},{y + d * 13} L{x - 7},{y} M{x},{y + d * 13} L{x},{y} M{x},{y + d * 13} L{x + 7},{y}" '
                f'stroke="{TRAZO}" stroke-width="1.3" fill="none"/>'
                f'<circle cx="{x}" cy="{y + d * 19}" r="5" fill="{FONDO}" stroke="{TRAZO}" stroke-width="1.3"/>')

    def relacion(self, padre, hijo):
        fp, fh = self._fila(padre), self._fila(hijo)
        if fh < fp:                               # el hijo está arriba: sale por arriba del padre
            x0, y0 = self._puerto(padre, "t")
            x1, y1 = self._puerto(hijo, "b")
            yb = self._banda(fh)
            pts = [(x0, y0), (x0, yb), (x1, yb), (x1, y1)]
            marcas = self._uno(x0, y0, "arriba") + self._muchos(x1, y1, "abajo")
        else:
            x0, y0 = self._puerto(padre, "b")
            yb = self._banda(fp)
            if fh == fp:
                x1, y1 = self._puerto(hijo, "b")
                pts = [(x0, y0), (x0, yb), (x1, yb), (x1, y1)]
                marcas = self._uno(x0, y0, "abajo") + self._muchos(x1, y1, "abajo")
            else:
                x1, y1 = self._puerto(hijo, "t")
                pts = [(x0, y0), (x0, yb)]
                if fh > fp + 1:
                    xc = self._callejon(self.pos[hijo][0])
                    yb2 = self._banda(fh - 1)
                    pts += [(xc, yb), (xc, yb2), (x1, yb2)]
                else:
                    pts += [(x1, yb)]
                pts.append((x1, y1))
                marcas = self._uno(x0, y0, "abajo") + self._muchos(x1, y1, "arriba")
        d = "M" + " L".join(f"{x},{y}" for x, y in pts)
        self.c.capas["lineas"].append(f'<path d="{d}" fill="none" stroke="{TRAZO}" stroke-width="1.2"/>' + marcas)

    def dibujar(self, nombre, orden_relaciones):
        for t in self.pos:
            self.tabla(t)
        for padre, hijo in orden_relaciones:
            self.relacion(padre, hijo)
        self.c.guardar(nombre)


def relaciones(tablas, presentes):
    rel = []
    for hijo, (cols, fks) in tablas.items():
        if hijo not in presentes:
            continue
        for col, padre in fks.items():
            if padre in presentes:
                rel.append((padre, hijo))
    return rel


def der_local():
    t = esquema_local()
    w = 265
    xs = [40 + i * 315 for i in range(7)]
    f0, f1, f2 = 40, 520, 990
    pos = {
        "tipo_residente": (xs[0], 150), "cuenta_local": (xs[1], f0), "zona": (xs[2], 150), "unidad": (xs[3], 150),
        "licencia": (xs[4], 110), "visitante": (xs[5], 110), "invitacion": (xs[6], f0),
        "residente": (xs[1], f1), "camara": (xs[2], f1), "vehiculo": (xs[3], f1), "visita": (xs[4], f1),
        "visita_autorizada": (xs[5], f1), "solicitud_registro": (xs[6], f1),
        "consentimiento": (xs[0], f2), "solicitud_derecho": (xs[1], f2), "plantilla_facial": (xs[2], f2),
        "deteccion_rostro": (xs[3], f2), "deteccion_vehiculo": (xs[4], f2), "plantilla_visita": (xs[5], f2),
        "solicitud_plantilla": (xs[6], f2),
    }
    assert set(pos) == set(t), set(t) ^ set(pos)
    rel = relaciones(t, pos)
    rel.sort(key=lambda r: (pos[r[0]][1], pos[r[0]][0], pos[r[1]][0]))
    Der(t, pos, w, [f0, f1, f2], 1320).dibujar("der_local", rel)


def der_central():
    t = esquema_central()
    w = 330
    xs = [40, 420, 800]
    f0, f1, f2, f3 = 40, 420, 800, 1210
    pos = {"plan": (xs[0], 90), "condominio": (xs[1], f0), "rol": (xs[2], 170),
           "suscripcion": (xs[0], f1), "nodo": (xs[1], f1), "cuenta": (xs[2], f1),
           "pago": (xs[0], f2), "invitacion_registro": (xs[1], f2),
           "envio_registro": (xs[1], f3)}
    assert set(pos) == set(t), set(t) ^ set(pos)
    rel = relaciones(t, pos)
    rel.sort(key=lambda r: (pos[r[0]][1], pos[r[0]][0], pos[r[1]][0]))
    Der(t, pos, w, [f0, f1, f2, f3], 1380).dibujar("der_central", rel)


if __name__ == "__main__":
    der_local()
    der_central()
