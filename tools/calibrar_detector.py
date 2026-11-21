# -*- coding: utf-8 -*-
"""
tools/calibrar_detector.py - Calibra PERSON_CONFIDENCE y VEHICLE_CONFIDENCE de
RF-DETR con las cámaras reales, usando como referencia lo que detectaba YOLO26s
con umbral 0.5 (el comportamiento anterior del nodo).

HERRAMIENTA DE DESARROLLO: necesita ultralytics y yolo26s.pt, que NO van en el
instalador del nodo. Se ejecuta en el equipo de desarrollo conectado a la red
del condominio.

Uso:
    python tools/calibrar_detector.py --minutos 10 --cada 2 rtsp://usuario:clave@ip/Streaming/Channels/102 ...
    python tools/calibrar_detector.py --carpeta capturas/      (imágenes ya guardadas)

Para cada umbral muestra, por grupo (personas / vehículos):
  coincide = fracción de detecciones de YOLO26s@0.5 que RF-DETR también encuentra
  extra    = detecciones de RF-DETR que YOLO26s no tenía, por cuadro

Las 'extra' NO son necesariamente errores: RF-DETR encuentra objetos que YOLO26s
no veía (en COCO128 anotado, a 0.60 casi todas eran personas reales). Por eso no
se recomienda un umbral automático: con --guardar, el recorte de cada 'extra' al
umbral vigente queda en <guardar>/extra_<grupo>/ y se revisa a ojo. Si la mayoría
son reales, el umbral está bien; si hay muchos falsos positivos, subirlo 0.05.
"""

import argparse
import glob
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
from core.detector import OnnxDetector  # noqa: E402
from core.tracker import iou  # noqa: E402

GRUPOS = {"personas": {0}, "vehiculos": set(config.VEHICLES_CLASS)}
UMBRALES = [round(t, 2) for t in np.arange(0.30, 0.81, 0.05)]
VIGENTE = {"personas": config.PERSON_CONFIDENCE, "vehiculos": config.VEHICLE_CONFIDENCE}


def capturar(fuentes, minutos, cada, guardar):
    caps = [cv2.VideoCapture(f) for f in fuentes]
    fin = time.time() + minutos * 60
    n = 0
    while time.time() < fin:
        for i, cap in enumerate(caps):
            ok, frame = cap.read()
            if ok:
                n += 1
                if guardar:
                    cv2.imwrite(os.path.join(guardar, f"cam{i}_{n:05d}.jpg"), frame)
                yield frame
        t0 = time.time()
        while time.time() - t0 < cada:     # descartar cuadros intermedios
            for cap in caps:
                cap.grab()
    for cap in caps:
        cap.release()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fuentes", nargs="*")
    ap.add_argument("--carpeta")
    ap.add_argument("--minutos", type=float, default=10)
    ap.add_argument("--cada", type=float, default=2.0, help="segundos entre cuadros")
    ap.add_argument("--guardar", help="carpeta donde guardar los cuadros usados")
    ap.add_argument("--referencia", default=os.path.join(ROOT, "yolo26s.pt"))
    args = ap.parse_args()
    if args.guardar:
        os.makedirs(args.guardar, exist_ok=True)

    from ultralytics import YOLO
    ref = YOLO(args.referencia)
    det = OnnxDetector(config.DETECTOR_MODEL)
    clases = [0] + list(config.VEHICLES_CLASS)

    if args.carpeta:
        frames = (cv2.imread(p) for p in sorted(glob.glob(os.path.join(args.carpeta, "*.jpg"))))
    else:
        frames = capturar(args.fuentes, args.minutos, args.cada, args.guardar)

    stats = {g: {t: [0, 0, 0] for t in UMBRALES} for g in GRUPOS}   # [ref_total, coinciden, extra]
    n_frames = 0
    for frame in frames:
        if frame is None:
            continue
        n_frames += 1
        r_rows = [r for r in ref(frame, classes=clases, verbose=False)[0].boxes.data.tolist()
                  if r[4] >= 0.5]
        d_rows = det.detect(frame, classes=clases)
        for g, cls in GRUPOS.items():
            rr = [r for r in r_rows if int(r[5]) in cls]
            for t in UMBRALES:
                dd = [d for d in d_rows if int(d[5]) in cls and d[4] >= t]
                usados = set()
                for r in rr:
                    j = max(range(len(dd)), key=lambda k: iou(r, dd[k]), default=None)
                    if j is not None and j not in usados and iou(r, dd[j]) >= 0.5:
                        usados.add(j)
                s = stats[g][t]
                s[0] += len(rr)
                s[1] += len(usados)
                s[2] += len(dd) - len(usados)
                if args.guardar and t == round(VIGENTE[g], 2):
                    carpeta = os.path.join(args.guardar, f"extra_{g}")
                    os.makedirs(carpeta, exist_ok=True)
                    for k, d in enumerate(dd):
                        if k in usados:
                            continue
                        x1, y1, x2, y2 = (max(0, int(v)) for v in d[:4])
                        crop = frame[y1:y2, x1:x2]
                        if crop.size:
                            cv2.imwrite(os.path.join(
                                carpeta, f"{n_frames:05d}_{k}_score{d[4]:.2f}.jpg"), crop)
        if n_frames % 20 == 0:
            print(f"  {n_frames} cuadros...", flush=True)

    print(f"\n{n_frames} cuadros analizados. Referencia: YOLO26s @0.50\n")
    for g in GRUPOS:
        print(f"[{g}]  (umbral vigente {VIGENTE[g]:.2f})")
        for t in UMBRALES:
            total, coinciden, extra = stats[g][t]
            marca = "  <- vigente" if t == round(VIGENTE[g], 2) else ""
            print(f"  umbral {t:.2f}: coincide {coinciden / max(total, 1):6.1%} "
                  f"de {total:4d} | extra {extra / max(n_frames, 1):5.2f} por cuadro{marca}")
        if args.guardar:
            print(f"  recortes de las 'extra' al umbral vigente: "
                  f"{os.path.join(args.guardar, 'extra_' + g)}")
        print()


if __name__ == "__main__":
    main()
