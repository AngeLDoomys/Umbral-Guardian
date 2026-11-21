# -*- coding: utf-8 -*-
"""Genera los diagramas de base de datos desde el esquema real y dibuja todos los .mmd.

    py docs/anexos/herramientas/renderizar_diagramas.py

Los modelos entidad-relación se leen del esquema (SQLite local y sql/central.sql), sin datos.
El dibujo usa Mermaid 10.9.1 en Microsoft Edge sin ventana (requiere internet la primera vez).
"""
import glob
import os
import re
import sqlite3
import subprocess
import sys
import tempfile

from PIL import Image, ImageChops

AQUI = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(AQUI, "..", "..", ".."))
DIAG = os.path.join(AQUI, "..", "diagramas")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
sys.path.insert(0, ROOT)
import config  # noqa: E402

HTML = """<!doctype html><html><head><meta charset=utf-8>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<style>body{margin:0;padding:24px;background:#fff;font-family:Calibri,Segoe UI,sans-serif}</style>
</head><body><pre class=mermaid>%s</pre>
<script>mermaid.initialize({startOnLoad:true, theme:'neutral', securityLevel:'loose',
 fontFamily:'Calibri, Segoe UI, sans-serif', flowchart:{useMaxWidth:false, htmlLabels:true},
 sequence:{useMaxWidth:false}, er:{useMaxWidth:false}, class:{useMaxWidth:false}});</script>
</body></html>"""


def _tipo(t):
    t = re.sub(r"\(.*?\)", "", (t or "TEXT")).upper().split()[0]
    return re.sub(r"[^A-Z]", "", t) or "TEXT"


# la base local en tres diagramas por tema, para que se lean en una página
GRUPOS_LOCAL = {
    "10a_er_local_residentes_accesos": [
        "unidad", "tipo_residente", "residente", "consentimiento", "plantilla_facial",
        "vehiculo", "zona", "camara", "deteccion_rostro", "deteccion_vehiculo"],
    "10b_er_local_visitas_registro_movil": [
        "unidad", "visitante", "visita", "visita_autorizada", "plantilla_visita",
        "invitacion", "solicitud_registro", "solicitud_plantilla"],
    "10c_er_local_cuentas_privacidad": [
        "cuenta_local", "licencia", "residente", "solicitud_derecho"],
}


def er_local(grupo):
    c = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    lineas, relaciones = ["erDiagram"], []
    for t in grupo:
        fks = {r[3]: r[2] for r in c.execute(f"PRAGMA foreign_key_list({t})")}
        lineas.append(f"  {t} {{")
        for _, col, tipo, _nn, _d, pk in c.execute(f"PRAGMA table_info({t})"):
            marca = " PK" if pk else (" FK" if col in fks else "")
            lineas.append(f"    {_tipo(tipo)} {col}{marca}")
        lineas.append("  }")
        relaciones += [f"  {destino} ||--o{{ {t} : \"{col}\"" for col, destino in fks.items()
                       if destino in grupo]
    c.close()
    return "\n".join(lineas + relaciones)


def er_central():
    sql = open(os.path.join(ROOT, "sql", "central.sql"), encoding="utf-8").read()
    lineas, relaciones = ["erDiagram"], []
    for nombre, cuerpo in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\) ENGINE", sql, re.S):
        fks = dict(re.findall(r"FOREIGN KEY \((\w+)\)\s*REFERENCES (\w+)", cuerpo))
        lineas.append(f"  {nombre} {{")
        for col, tipo, resto in re.findall(r"^\s{4}(\w+)\s+([A-Z]+(?:\([^)]*\))?)(.*)$", cuerpo, re.M):
            if col in ("CONSTRAINT", "INDEX", "UNIQUE", "PRIMARY"):
                continue
            marca = " PK" if "PRIMARY KEY" in resto else (" FK" if col in fks else "")
            lineas.append(f"    {_tipo(tipo)} {col}{marca}")
        lineas.append("  }")
        relaciones += [f"  {destino} ||--o{{ {nombre} : \"{col}\"" for col, destino in fks.items()]
    return "\n".join(lineas + relaciones)


def dibujar(mmd):
    destino = os.path.abspath(mmd[:-4] + ".png")
    pagina = os.path.join(tempfile.mkdtemp(prefix="ug_mmd_"), "d.html")
    texto = open(mmd, encoding="utf-8").read()
    with open(pagina, "w", encoding="utf-8") as f:
        f.write(HTML % texto.replace("&", "&amp;").replace("<br/>", "#br#")
                .replace("<", "&lt;").replace(">", "&gt;").replace("#br#", "<br/>"))
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=2", "--window-size=2600,3200",
                    "--virtual-time-budget=15000", f"--screenshot={destino}",
                    "file:///" + pagina.replace("\\", "/")], check=True, capture_output=True,
                   timeout=120)
    im = Image.open(destino).convert("RGB")
    caja = ImageChops.difference(im, Image.new("RGB", im.size, "white")).getbbox()
    if caja:
        im = im.crop((max(0, caja[0] - 20), max(0, caja[1] - 20),
                      min(im.width, caja[2] + 20), min(im.height, caja[3] + 20)))
    im.save(destino)
    print(os.path.basename(destino), im.size)


def main():
    viejo = os.path.join(DIAG, "10_er_local.mmd")
    for ruta in (viejo, viejo[:-4] + ".png"):
        if os.path.exists(ruta):
            os.remove(ruta)
    for nombre, grupo in GRUPOS_LOCAL.items():
        with open(os.path.join(DIAG, nombre + ".mmd"), "w", encoding="utf-8") as f:
            f.write(er_local(grupo))
    with open(os.path.join(DIAG, "11_er_central.mmd"), "w", encoding="utf-8") as f:
        f.write(er_central())
    solo = sys.argv[1:]
    for mmd in sorted(glob.glob(os.path.join(DIAG, "*.mmd"))):
        if not solo or any(s in mmd for s in solo):
            dibujar(mmd)


if __name__ == "__main__":
    main()
