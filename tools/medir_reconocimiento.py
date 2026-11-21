# -*- coding: utf-8 -*-
"""
tools/medir_reconocimiento.py - Mide aciertos del reconocimiento facial con una cámara real.

    py tools/medir_reconocimiento.py --camara "Acceso Principal" --participante P1 --residente 1
    py tools/medir_reconocimiento.py --camara "Acceso Principal" --participante P2 --no-registrado

Usa el canal alto y la misma comparación que el motor, un intento por segundo. Guarda solo
hora, código del participante, resultado y distancia: ni imágenes, ni vectores, ni nombres.
"""
import argparse
import csv
import os
import sqlite3
import sys
import time

os.environ.setdefault("OPENCV_LOG_LEVEL", "OFF")
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
from core import face_utils as fu  # noqa: E402
from database import DatabaseManager  # noqa: E402

SALIDA = os.path.join(ROOT, "tests", "evidencias", "rfdetr_sface", "PR-02.csv")
CAMPOS = ["hora", "participante", "esperado", "resultado", "acierto", "distancia"]


def clasificar(res, residente):
    """(resultado, acierto) de un intento válido; residente None = persona no registrada."""
    if res["status"] == "match":
        if residente is None:
            return "aceptado_por_error", 0
        return ("correcto", 1) if res.get("idresidente") == residente else ("otra_persona", 0)
    return ("rechazado_correctamente", 1) if residente is None else ("no_reconocido", 0)


def fuente_camara(nombre):
    c = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    fila = c.execute("SELECT COALESCE(NULLIF(fuente_alta, ''), fuente) FROM camara WHERE nombre = ?",
                     (nombre,)).fetchone()
    c.close()
    if not fila:
        sys.exit(f"No existe la cámara «{nombre}»")
    return fila[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camara", required=True)
    ap.add_argument("--participante", required=True, help="código anónimo, por ejemplo P1")
    quien = ap.add_mutually_exclusive_group(required=True)
    quien.add_argument("--residente", type=int)
    quien.add_argument("--no-registrado", action="store_true")
    ap.add_argument("--segundos", type=float, default=60)
    ap.add_argument("--salida", default=SALIDA)
    a = ap.parse_args()

    db = DatabaseManager()
    if not db.connect():
        sys.exit("No se pudo abrir la base local")
    known = [k for k in fu.load_known_faces(db) if k.get("tipo", "residente") == "residente"]
    db.disconnect()
    if a.residente and not any(k["idresidente"] == a.residente for k in known):
        sys.exit("Ese residente no tiene plantillas activas")

    cap = cv2.VideoCapture(fuente_camara(a.camara), cv2.CAP_FFMPEG)
    if not cap.isOpened():
        sys.exit("No se pudo abrir la cámara")
    existe = os.path.exists(a.salida)
    aciertos = validos = descartes = 0
    fin, proximo = time.time() + a.segundos, 0.0
    with open(a.salida, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, CAMPOS)
        if not existe:
            w.writeheader()
        while time.time() < fin:
            if not cap.grab():
                time.sleep(0.05)
                continue
            if time.time() < proximo:
                continue
            ok, frame = cap.retrieve()
            if not ok:
                continue
            proximo = time.time() + 1.0
            res = fu.recognize_face(frame, known)
            if res["status"] in ("no_face", "low_quality"):
                descartes += 1
                continue
            resultado, acierto = clasificar(res, a.residente)
            validos += 1
            aciertos += acierto
            d = res.get("distance")
            w.writerow({"hora": time.strftime("%Y-%m-%d %H:%M:%S"), "participante": a.participante,
                        "esperado": "residente" if a.residente else "no_registrado",
                        "resultado": resultado, "acierto": acierto,
                        "distancia": "" if d is None else f"{d:.4f}"})
            f.flush()
    cap.release()
    pct = f"{aciertos / validos:.1%}" if validos else "sin intentos válidos"
    print(f"{a.participante}: {aciertos}/{validos} aciertos ({pct}); "
          f"sin rostro útil: {descartes} | umbral {config.FACE_RECOGNITION_THRESHOLD}")


if __name__ == "__main__":
    main()
