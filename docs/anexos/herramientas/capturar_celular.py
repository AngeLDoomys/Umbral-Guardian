# -*- coding: utf-8 -*-
"""Capturas del formulario de registro desde el celular, con una invitación ficticia.

    py docs/anexos/herramientas/capturar_celular.py

Genera la página con la misma plantilla que sirve la nube (sin conectarse a ella) y la
fotografía con Microsoft Edge en modo sin ventana, con el ancho de un celular.
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageChops

AQUI = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(AQUI, "..", "..", ".."))
SALIDA = os.path.join(AQUI, "..", "capturas")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
sys.path.insert(0, ROOT)

from flask import Flask  # noqa: E402
from servidor import registro_movil as rm  # noqa: E402

BASE = {"condominio": "Condominio Parque Fray Jorge", "unidad": "Avellano 14", "vigente": True,
        "nodo_activo": True, "frecuente": False, "solo_rostro": False, "rostro": True}
VARIANTES = {
    # nombre: (invitación, CSS que muestra el paso a fotografiar)
    "celular_1_datos_residente": (dict(BASE, tipo="residente"), ""),
    "celular_2_consentimiento": (dict(BASE, tipo="residente"),
                                 "#paso-datos{display:none}#paso-consent{display:block!important}"),
    "celular_3_fotos": (dict(BASE, tipo="residente"),
                        "#paso-datos{display:none}#paso-fotos{display:block!important}"),
    "celular_4_visita": (dict(BASE, tipo="visita"), ""),
    "celular_5_listo": (dict(BASE, tipo="residente"),
                        "#paso-datos{display:none}#paso-fin{display:block!important}"),
}


def recortar(ruta):
    im = Image.open(ruta).convert("RGB")
    fondo = Image.new("RGB", im.size, im.getpixel((2, im.height - 2)))
    caja = ImageChops.difference(im, fondo).getbbox()
    if caja:
        im = im.crop((0, 0, im.width, min(im.height, caja[3] + 24)))
    im.save(ruta)


def main():
    os.makedirs(SALIDA, exist_ok=True)
    app = Flask(__name__)
    app.register_blueprint(rm.bp)
    cliente = app.test_client()
    tmp = tempfile.mkdtemp(prefix="ug_celular_")
    for nombre, (inv, css) in VARIANTES.items():
        rm._invitacion = lambda token, inv=inv: inv
        html = cliente.get("/r/EJEMPLO").get_data(as_text=True)
        html = html.replace("</head>", f"<style>{css}</style></head>")
        if "paso-fotos" in css:      # la lista de poses se dibuja al llegar a ese paso
            html = html.replace("</body>", "<script>dibujar()</script></body>")
        pagina = os.path.join(tmp, nombre + ".html")
        with open(pagina, "w", encoding="utf-8") as f:
            f.write(html)
        destino = os.path.abspath(os.path.join(SALIDA, nombre + ".png"))
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1.5", "--window-size=520,1500",
                        "--virtual-time-budget=3000", f"--screenshot={destino}",
                        "file:///" + pagina.replace("\\", "/")],
                       check=True, capture_output=True, timeout=60)
        recortar(destino)
        print("captura", nombre, Image.open(destino).size)


if __name__ == "__main__":
    main()
