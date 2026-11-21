# -*- coding: utf-8 -*-
"""
tools/generar_licencias.py - Arma la carpeta licencias/ con el texto completo de la
licencia de cada componente que se instala con el nodo (Apache 2.0, MIT, BSD, MPL y
LGPL exigen acompañar el texto de la licencia y los avisos de copyright).

Toma las dependencias reales desde los paquetes instalados, a partir de las que
importa el nodo (RAICES), y agrega los textos que no vienen en ningún paquete de
Python (modelos y DirectML.dll) desde licencias_externas/.

Uso (antes de empaquetar, con el entorno del nodo activo):
    python tools/generar_licencias.py
"""

import os
import re
import shutil
import sys
from importlib import metadata

from packaging.requirements import Requirement

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(ROOT, "licencias")
EXTERNAS = os.path.join(ROOT, "licencias_externas")

# paquetes que importa el código del nodo (main.py, core/, engine/, gui/, reports/)
RAICES = ["opencv-python", "numpy", "pillow", "onnxruntime-directml", "fast-plate-ocr",
          "requests", "cryptography", "reportlab", "qrcode"]
_ARCHIVO_LICENCIA = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS|ThirdPartyNotices)", re.I)


def dependencias():
    vistos, orden = set(), []

    def visitar(nombre):
        clave = nombre.lower().replace("_", "-")
        if clave in vistos:
            return
        vistos.add(clave)
        try:
            dist = metadata.distribution(nombre)
        except metadata.PackageNotFoundError:
            return                       # p. ej. opencv-python-headless: lo cubre opencv-python
        orden.append(dist)
        for r in dist.requires or []:
            req = Requirement(r)
            if req.marker is None or req.marker.evaluate({"extra": ""}):
                visitar(req.name)

    for raiz in RAICES:
        visitar(raiz)
    return orden


def main():
    if os.path.isdir(DESTINO):
        shutil.rmtree(DESTINO)
    os.makedirs(DESTINO)
    indice = []

    for dist in dependencias():
        nombre = f"{dist.metadata['Name']}-{dist.version}"
        carpeta = os.path.join(DESTINO, nombre)
        copiados = 0
        for f in dist.files or []:
            if _ARCHIVO_LICENCIA.search(os.path.basename(str(f))) and str(f).endswith((".txt", ".md", "")) \
                    and not str(f).endswith((".py", ".pyc")):
                origen = dist.locate_file(f)
                if os.path.isfile(origen):
                    os.makedirs(carpeta, exist_ok=True)
                    destino = os.path.join(carpeta, str(f).replace("/", "__").replace("\\", "__"))
                    shutil.copyfile(origen, destino)
                    copiados += 1
        licencia = dist.metadata.get("License-Expression") or \
            (dist.metadata.get("License") or "").split("\n")[0][:60]
        indice.append(f"{nombre:<34} {licencia:<40} {copiados} archivo(s)")
        if copiados == 0:
            print(f"ADVERTENCIA: {nombre} no trae archivo de licencia")

    # Python (incluye los avisos de OpenSSL, SQLite, Tcl/Tk, libffi, zlib, bzip2, xz, expat)
    py = os.path.join(sys.base_prefix, "LICENSE.txt")
    if os.path.exists(py):
        carpeta = os.path.join(DESTINO, f"Python-{sys.version.split()[0]}")
        os.makedirs(carpeta, exist_ok=True)
        shutil.copyfile(py, os.path.join(carpeta, "LICENSE.txt"))
        indice.append(f"Python-{sys.version.split()[0]:<27} PSF-2.0 (y componentes incluidos)")

    for f in sorted(os.listdir(EXTERNAS)):
        shutil.copyfile(os.path.join(EXTERNAS, f), os.path.join(DESTINO, f))
        indice.append(f"{f}")

    with open(os.path.join(DESTINO, "INDICE.txt"), "w", encoding="utf-8") as fh:
        fh.write("Textos de licencia de los componentes del nodo (ver AVISOS.txt)\n\n")
        fh.write("\n".join(indice) + "\n")
    print(f"{len(indice)} componentes en {DESTINO}")


if __name__ == "__main__":
    main()
