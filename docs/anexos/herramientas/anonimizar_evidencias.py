# -*- coding: utf-8 -*-
"""Copia evidencias del condominio a docs/anexos/capturas con rostros y patentes difuminados.

    py docs/anexos/herramientas/anonimizar_evidencias.py

Rostros: detector YuNet con umbral bajo (mejor difuminar de más). Patentes: detector de
patentes del sistema. Además, zonas fijas por imagen (texto de patentes en las etiquetas).
"""
import os
import sys

import cv2
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(AQUI, "..", "..", ".."))
sys.path.insert(0, ROOT)
import config  # noqa: E402
from core.detector import OnnxDetector  # noqa: E402

EVID = os.path.join(ROOT, "tests", "evidencias", "rfdetr_sface")
SALIDA = os.path.join(AQUI, "..", "capturas")

# origen -> (destino, zonas extra (x1, y1, x2, y2) en fracciones del ancho/alto)
IMAGENES = {
    "PI-04a.png": ("real_residente_reconocido", []),
    "PI-05.png": ("real_no_reconocido", []),
    "PI-06b.png": ("real_patente_no_registrada", [(0.535, 0.405, 0.665, 0.475),
                                                  (0.610, 0.665, 0.640, 0.712)]),
    "PI-03b.png": ("real_misma_camara", []),
    "PI-13.png": ("real_reconexion", []),
    "PI-11a_pdf.png": ("real_reporte_pdf", []),
    "PI-09.png": ("real_sin_conexion", []),
    "PS-01a.png": ("real_menu_conserje", []),
    "PI-07c.png": ("real_configuracion_aplicada", []),
    # prueba de vehículos en entorno controlado: patente del autor, igual se difumina
    "PI-07a_antes.png": ("casa_patente_no_registrada", [(0.570, 0.365, 0.625, 0.405),
                                                        (0.625, 0.660, 0.675, 0.710)]),
    "PI-07a.png": ("casa_registro_vehiculo", [(0.400, 0.262, 0.440, 0.285)]),
    "PI-07b.png": ("casa_patente_reconocida", [(0.582, 0.410, 0.640, 0.448),
                                               (0.625, 0.615, 0.668, 0.655)]),
}


def difuminar(img, x1, y1, x2, y2):
    h, w = img.shape[:2]
    x1, y1, x2, y2 = max(0, int(x1)), max(0, int(y1)), min(w, int(x2)), min(h, int(y2))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    zona = img[y1:y2, x1:x2]
    k = max(15, (min(zona.shape[:2]) // 3) | 1)
    img[y1:y2, x1:x2] = cv2.GaussianBlur(cv2.resize(cv2.resize(zona, (8, 8)), zona.shape[1::-1],
                                                    interpolation=cv2.INTER_NEAREST), (k, k), 0)


def main():
    os.makedirs(SALIDA, exist_ok=True)
    det = cv2.FaceDetectorYN.create(config.FACE_DETECTOR_MODEL, "", (320, 320), score_threshold=0.45)
    patentes = OnnxDetector(config.PLATE_DETECTOR_MODEL)
    for origen, (destino, extra) in IMAGENES.items():
        ruta = os.path.join(EVID, origen)
        if not os.path.exists(ruta):
            print("falta", origen)
            continue
        img = cv2.imread(ruta)
        h, w = img.shape[:2]
        caras = 0
        for escala in (1.0, 2.0):
            g = cv2.resize(img, None, fx=escala, fy=escala)
            det.setInputSize((g.shape[1], g.shape[0]))
            _, f = det.detect(g)
            for c in (f if f is not None else []):
                x, y, fw, fh = c[:4] / escala
                # un rostro en el video mide entre ~15 y ~180 px: lo más grande es un error
                if not 12 <= fw <= 0.1 * w:
                    continue
                difuminar(img, x - fw * 0.35, y - fh * 0.45, x + fw * 1.35, y + fh * 1.3)
                caras += 1
        placas = 0
        for x1, y1, x2, y2, s, _ in patentes.detect(img):
            if s >= 0.4 and x2 - x1 <= 0.08 * w:
                difuminar(img, x1 - 6, y1 - 6, x2 + 6, y2 + 6)
                placas += 1
        for fx1, fy1, fx2, fy2 in extra:
            difuminar(img, fx1 * w, fy1 * h, fx2 * w, fy2 * h)
        cv2.imwrite(os.path.join(SALIDA, destino + ".png"), img)
        print(f"{destino}: {caras} rostros, {placas} patentes, {len(extra)} zonas fijas")


if __name__ == "__main__":
    main()
