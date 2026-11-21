# -*- coding: utf-8 -*-
"""
tools/calibrar_rostros.py - Revisa FACE_RECOGNITION_THRESHOLD y FACE_MATCH_MARGIN
con las cámaras reales y los residentes ya registrados con SFace.

Se corre dos veces, con una persona frente a la cámara cada vez:

  1) un residente registrado (se indica su id):
       python tools/calibrar_rostros.py --residente 3 --segundos 60 rtsp://...
  2) alguien NO registrado:
       python tools/calibrar_rostros.py --no-registrado --segundos 60 rtsp://...

Usa la misma detección, filtro de calidad y comparación que el motor. No guarda
fotos ni vectores: solo imprime, al terminar, las distancias medidas y cuántos
intentos aceptaría cada combinación de umbral y margen.

Qué buscar:
  - con el residente: la mayoría de los intentos deben dar "match" con SU id;
  - con el no registrado: ningún "match" (o casi ninguno: la votación de 2
    confirmaciones descarta coincidencias aisladas).
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
from core import face_utils as fu  # noqa: E402
from database import DatabaseManager  # noqa: E402

UMBRALES = (0.40, 0.45, 0.50, 0.55, 0.60)
MARGENES = (0.05, 0.07, 0.09, 0.11)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fuente", help="URL RTSP, índice USB o archivo de video")
    quien = ap.add_mutually_exclusive_group(required=True)
    quien.add_argument("--residente", type=int, help="id del residente frente a la cámara")
    quien.add_argument("--no-registrado", action="store_true")
    ap.add_argument("--segundos", type=float, default=60)
    ap.add_argument("--cada", type=float, default=0.5, help="segundos entre intentos")
    args = ap.parse_args()

    db = DatabaseManager()
    if not db.connect():
        sys.exit("No se pudo abrir la base local")
    # solo residentes: las visitas no tienen idresidente
    known = [k for k in fu.load_known_faces(db) if k.get("tipo", "residente") == "residente"]
    db.disconnect()
    if not known:
        sys.exit("No hay residentes registrados con " + config.FACE_MODEL)
    if args.residente and not any(k["idresidente"] == args.residente for k in known):
        sys.exit(f"El residente {args.residente} no tiene plantillas {config.FACE_MODEL} activas")

    ids = sorted({k["idresidente"] for k in known})
    templates = {i: [np.asarray(k["embedding"], np.float32) for k in known if k["idresidente"] == i]
                 for i in ids}

    fuente = int(args.fuente) if args.fuente.isdigit() else args.fuente
    cap = cv2.VideoCapture(fuente)
    fin, ultimo = time.time() + args.segundos, 0.0
    medidas, descartes = [], {}
    print(f"Midiendo {args.segundos:.0f} s... (Ctrl+C para terminar antes)")
    try:
        while time.time() < fin:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            if time.time() - ultimo < args.cada:
                continue
            ultimo = time.time()
            info = fu.extract_face(frame)
            if info is None:
                continue
            problema = fu.quality_problem(info)
            if problema:
                clave = problema.split(" (")[0]
                descartes[clave] = descartes.get(clave, 0) + 1
                continue
            e = info["embedding"] / (np.linalg.norm(info["embedding"]) + 1e-9)
            dist = {i: min(1 - float(np.dot(e, t / (np.linalg.norm(t) + 1e-9))) for t in ts)
                    for i, ts in templates.items()}
            orden = sorted(dist.items(), key=lambda kv: kv[1])
            medidas.append((orden[0][0], orden[0][1], orden[1][1] if len(orden) > 1 else 1.0))
    except KeyboardInterrupt:
        pass
    cap.release()

    print(f"\nIntentos válidos: {len(medidas)} | descartados por calidad: {descartes or 0}")
    if not medidas:
        return
    best = np.array([m[1] for m in medidas])
    print(f"Distancia al residente más cercano: mediana {np.median(best):.3f}, "
          f"mín {best.min():.3f}, máx {best.max():.3f}")
    print(f"\nVigente: umbral {config.FACE_RECOGNITION_THRESHOLD:.2f}, margen {config.FACE_MATCH_MARGIN:.2f}")
    titulo = ("% de intentos reconocidos como el residente correcto" if args.residente
              else "% de intentos ACEPTADOS como algún residente (debería ser ~0)")
    print(titulo + ":")
    print("  umbral \\ margen " + "".join(f"{m:>8.2f}" for m in MARGENES))
    for t in UMBRALES:
        fila = []
        for m in MARGENES:
            acepta = [(rid, d1, d2) for rid, d1, d2 in medidas if d1 < t and d2 - d1 >= m]
            if args.residente:
                acepta = [a for a in acepta if a[0] == args.residente]
            fila.append(f"{len(acepta) / len(medidas):8.0%}")
        marca = "  <- vigente" if abs(t - config.FACE_RECOGNITION_THRESHOLD) < 1e-9 else ""
        print(f"  {t:>14.2f}  " + "".join(fila) + marca)


if __name__ == "__main__":
    main()
