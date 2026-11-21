# -*- coding: utf-8 -*-
"""
core/detector.py - Detectores de objetos en ONNX, ejecutados con onnxruntime.

Dos formatos, reconocidos por las entradas y salidas del modelo:
  - RF-DETR (Apache 2.0): personas y vehículos (COCO).
      entrada 'input' [1, 3, R, R]; salidas 'dets' [1, Q, 4] (cx, cy, w, h normalizados)
      y 'labels' [1, Q, 91] (logits por id de categoría COCO, 1 = persona).
  - YOLO exportado con NMS: detector de patentes.
      entrada 'images' [1, 3, 640, 640]; salida [1, 300, 6] (x1, y1, x2, y2, score, clase).

detect() retorna filas [x1, y1, x2, y2, score, clase] en píxeles de la imagen de entrada.
Las clases de RF-DETR se traducen a los índices contiguos 0-79 que usaba Ultralytics
(0 = persona, 2 = auto, 3 = moto, 5 = bus, 7 = camión), así config.VEHICLES_CLASS
sigue valiendo igual.
"""

import os
import threading

import cv2
import numpy as np

from core import gpu

# id de categoría COCO (1-90, con huecos) para cada índice contiguo 0-79
_COCO80_TO_91 = [
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25,
    27, 28, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 46, 47, 48, 49, 50, 51,
    52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 67, 70, 72, 73, 74, 75, 76, 77,
    78, 79, 80, 81, 82, 84, 85, 86, 87, 88, 89, 90,
]
_COCO91_TO_80 = {c91: c80 for c80, c91 in enumerate(_COCO80_TO_91)}

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

MIN_SCORE = 0.05   # piso: el umbral real lo aplica el motor (config.*_CONFIDENCE)

# DirectML no admite inferencias simultáneas: con dos cámaras, varios hilos usando la
# GPU a la vez botaban el programa dentro del driver (nvwgf2umx.dll, 0xC0000005).
# Todo uso de la GPU pasa por este candado y cada modelo se carga una sola vez.
_DML = "DmlExecutionProvider"
_gpu_lock = threading.Lock()
_sesiones_dml = {}


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


class OnnxDetector:
    def __init__(self, path: str):
        import onnxruntime as ort
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        providers = gpu.get_device_info()["providers"]
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        if _DML in providers:           # opciones que exige DirectML
            opts.enable_mem_pattern = False
            opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        clave = (os.path.abspath(path), os.path.getmtime(path))
        with _gpu_lock:                 # crear una sesión también usa la GPU
            sesion = _sesiones_dml.get(clave)
            if sesion is None:
                sesion = ort.InferenceSession(path, sess_options=opts, providers=providers)
                gpu.confirm_provider(sesion)
                if sesion.get_providers()[0] == _DML:
                    _sesiones_dml[clave] = sesion
        self._session = sesion
        # en CPU o CUDA, un candado por detector (hilo de video y hilo de OCR)
        self._lock = _gpu_lock if sesion.get_providers()[0] == _DML else threading.Lock()
        self._input = self._session.get_inputs()[0]
        outputs = [o.name for o in self._session.get_outputs()]
        self._kind = "rfdetr" if {"dets", "labels"} <= set(outputs) else "yolo_nms"
        if self._kind == "rfdetr":
            self._h, self._w = (int(d) for d in self._input.shape[2:4])
        else:
            # exportado con entrada dinámica: tamaño base desde los metadatos ('[640, 640]')
            meta = self._session.get_modelmeta().custom_metadata_map
            self._imgsz = int(str(meta.get("imgsz", "640")).strip("[]").split(",")[0])
        self.name = os.path.basename(path)
        self.provider = self._session.get_providers()[0]

    # ── API ───────────────────────────────────────────────────────────────

    def detect(self, img: np.ndarray, classes=None, min_score: float = MIN_SCORE) -> list:
        if img is None or img.size == 0:
            return []
        if self._kind == "rfdetr":
            rows = self._detect_rfdetr(img, min_score)
        else:
            rows = self._detect_yolo(img, min_score)
        if classes is not None:
            keep = set(int(c) for c in classes)
            rows = [r for r in rows if int(r[5]) in keep]
        return rows

    # ── RF-DETR ───────────────────────────────────────────────────────────

    def _detect_rfdetr(self, img, min_score):
        h, w = img.shape[:2]
        rgb = cv2.cvtColor(cv2.resize(img, (self._w, self._h), interpolation=cv2.INTER_LINEAR),
                           cv2.COLOR_BGR2RGB)
        x = ((rgb.astype(np.float32) / 255.0 - _MEAN) / _STD).transpose(2, 0, 1)[None]
        with self._lock:
            boxes, logits = self._session.run(["dets", "labels"], {self._input.name: x})
        prob = _sigmoid(logits[0])                 # [Q, 91]
        # una clase por detección, la más probable (como el NMS de Ultralytics):
        # evita que un mismo vehículo salga dos veces, como "auto" y como "camión"
        cls91 = prob.argmax(1)
        score = prob[np.arange(len(prob)), cls91]
        rows = []
        for q in np.flatnonzero(score >= min_score):
            c80 = _COCO91_TO_80.get(int(cls91[q]))
            if c80 is None:                         # categoría de fondo / sin uso en COCO
                continue
            cx, cy, bw, bh = boxes[0, q]
            rows.append([float((cx - bw / 2) * w), float((cy - bh / 2) * h),
                         float((cx + bw / 2) * w), float((cy + bh / 2) * h),
                         float(score[q]), c80])
        rows.sort(key=lambda r: r[4], reverse=True)
        return rows

    # ── YOLO con NMS incorporado (detector de patentes) ───────────────────

    def _detect_yolo(self, img, min_score):
        # mismo ajuste que Ultralytics al predecir con el .pt (LetterBox auto=True):
        # lado mayor a imgsz y relleno mínimo hasta múltiplo de 32, centrado, gris 114
        h, w = img.shape[:2]
        r = min(self._imgsz / h, self._imgsz / w)
        nw, nh = int(round(w * r)), int(round(h * r))
        dw, dh = ((self._imgsz - nw) % 32) / 2, ((self._imgsz - nh) % 32) / 2
        if (nw, nh) != (w, h):
            img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
        img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT,
                                 value=(114, 114, 114))
        x = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32).transpose(2, 0, 1)[None] / 255.0
        with self._lock:
            out = self._session.run(None, {self._input.name: x})[0][0]   # [300, 6]
        rows = []
        for x1, y1, x2, y2, score, cls in out:
            if score < min_score:
                continue
            rows.append([float(np.clip((x1 - left) / r, 0, w)), float(np.clip((y1 - top) / r, 0, h)),
                         float(np.clip((x2 - left) / r, 0, w)), float(np.clip((y2 - top) / r, 0, h)),
                         float(score), int(cls)])
        return rows
