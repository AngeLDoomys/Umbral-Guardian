# -*- coding: utf-8 -*-
"""
core/tracker.py - Seguimiento de vehículos por superposición (IoU), código propio.

Reemplaza a SORT (GPL-3.0) con la misma interfaz y las mismas reglas visibles:

  update(dets) recibe [[x1, y1, x2, y2, score], ...] y retorna [[x1, y1, x2, y2, id], ...]

  - Asociación greedy: se emparejan primero los pares con mayor IoU; un par con
    IoU < iou_threshold (0.3) nunca es match.
  - Cada track se compara en su posición PREDICHA: la última caja desplazada según
    la velocidad medida entre sus dos últimas detecciones (SORT usa un filtro de
    Kalman para lo mismo). Sin esto, un auto rápido muestreado cada 5 frames
    perdería la superposición y cambiaría de id.
  - Un track nuevo se informa recién cuando acumula min_hits (3) detecciones
    seguidas después de la primera, salvo en las min_hits primeras llamadas.
  - Un track no visto en una llamada pierde su racha; con más de max_age (1)
    llamadas sin verse, se elimina.
  - Ids desde 1, únicos en todo el proceso (también entre cámaras), y la salida
    en orden del track más nuevo al más antiguo, como SORT.

Diferencia con SORT: la caja informada es la detectada en ese frame, no la
suavizada por el filtro de Kalman.
"""

import itertools
import threading

import numpy as np


def iou(a, b) -> float:
    """Intersección sobre unión de dos cajas [x1, y1, x2, y2]."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class _Track:
    __slots__ = ("id", "box", "velocity", "time_since_update", "hit_streak")

    def __init__(self, track_id: int, box: np.ndarray):
        self.id = track_id
        self.box = box                     # última caja detectada
        self.velocity = np.zeros(4)        # desplazamiento por llamada (x1, y1, x2, y2)
        self.time_since_update = 0
        self.hit_streak = 0

    def predicted(self) -> np.ndarray:
        return self.box + self.velocity * self.time_since_update

    def update(self, box: np.ndarray):
        # velocidad promedio desde la última detección (puede haber una llamada perdida)
        self.velocity = (box - self.box) / max(1, self.time_since_update)
        self.box = box
        self.time_since_update = 0
        self.hit_streak += 1


class IoUTracker:
    _ids = itertools.count(1)          # compartido por todas las cámaras, como SORT
    _ids_lock = threading.Lock()

    def __init__(self, max_age: int = 1, min_hits: int = 3, iou_threshold: float = 0.3):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.tracks: list[_Track] = []
        self.frame_count = 0

    @classmethod
    def _new_id(cls) -> int:
        with cls._ids_lock:
            return next(cls._ids)

    def update(self, dets=np.empty((0, 5))) -> np.ndarray:
        self.frame_count += 1
        dets = np.asarray(dets, dtype=float).reshape(-1, 5)
        boxes = dets[:, :4]

        # avanzar un paso: quien no se vio en la llamada anterior pierde su racha
        for t in self.tracks:
            if t.time_since_update > 0:
                t.hit_streak = 0
            t.time_since_update += 1

        # asociación greedy por IoU decreciente, uno a uno
        predicted = [t.predicted() for t in self.tracks]
        pairs = sorted(
            ((iou(boxes[d], predicted[k]), d, k)
             for d in range(len(boxes)) for k in range(len(self.tracks))),
            key=lambda p: p[0], reverse=True)
        det_used, trk_used = set(), set()
        for score, d, k in pairs:
            if score < self.iou_threshold:
                break
            if d in det_used or k in trk_used:
                continue
            self.tracks[k].update(boxes[d].copy())
            det_used.add(d)
            trk_used.add(k)

        for d in range(len(boxes)):
            if d not in det_used:
                self.tracks.append(_Track(self._new_id(), boxes[d].copy()))

        out = []
        for t in reversed(self.tracks):
            if t.time_since_update == 0 and (
                    t.hit_streak >= self.min_hits or self.frame_count <= self.min_hits):
                out.append([*t.box, t.id])
        self.tracks = [t for t in self.tracks if t.time_since_update <= self.max_age]
        return np.array(out, dtype=float) if out else np.empty((0, 5))
