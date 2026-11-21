# -*- coding: utf-8 -*-
"""
core/hires_stream.py - Canal principal (alta resolución) de una cámara RTSP de doble stream.

La detección corre sobre el substream (baja resolución). Este lector mantiene
abierto el canal principal en su propio hilo haciendo solo grab() continuo, para
que el buffer de red no se atrase, y convierte a imagen (retrieve) únicamente
cuando el motor lo pide porque detectó una persona o un vehículo.
"""

import threading
import time
from typing import Optional

import cv2
import numpy as np

RECONNECT_WAIT_S = 2.0


class HighResStream:
    def __init__(self, source: str):
        self._source = source
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cond = threading.Condition()
        self._want = False
        self._frame: Optional[np.ndarray] = None
        self._frame_t = 0.0
        self.connected = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        with self._cond:
            self._cond.notify_all()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None

    def get_frame(self, max_age_s: float = 0.05, timeout_s: float = 0.5) -> Optional[np.ndarray]:
        """Frame de alta resolución más reciente. Reutiliza uno ya decodificado si tiene
        menos de max_age_s; si no, pide el siguiente y espera como máximo timeout_s.
        Retorna None si el canal no está disponible (el motor usa el frame bajo)."""
        if not self.connected:
            return None
        with self._cond:
            if self._frame is not None and time.perf_counter() - self._frame_t <= max_age_s:
                return self._frame
            self._want = True
            requested_at = time.perf_counter()
            self._cond.wait_for(
                lambda: self._frame_t > requested_at or not self._running or not self.connected,
                timeout=timeout_s,
            )
            if self._frame_t > requested_at:
                return self._frame
            return None

    def _open(self) -> Optional[cv2.VideoCapture]:
        cap = cv2.VideoCapture(self._source)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _loop(self):
        cap = None
        while self._running:
            if cap is None:
                cap = self._open()
                if cap is None:
                    print(f"[HighRes] No se pudo abrir el canal alto; reintento en {RECONNECT_WAIT_S:.0f}s")
                    time.sleep(RECONNECT_WAIT_S)
                    continue
                self.connected = True
                print("[HighRes] Canal de alta resolución conectado")

            # grab() demultiplexa y decodifica, pero no convierte a BGR: es lo mínimo
            # para mantener el stream H.264/H.265 al día
            if not cap.grab():
                print("[HighRes] Se perdió el canal alto; reconectando")
                self.connected = False
                with self._cond:
                    self._cond.notify_all()
                cap.release()
                cap = None
                time.sleep(RECONNECT_WAIT_S)
                continue

            if self._want:
                ok, frame = cap.retrieve()
                if ok:  # si falla, se reintenta con el siguiente grab
                    with self._cond:
                        self._frame = frame
                        self._frame_t = time.perf_counter()
                        self._want = False
                        self._cond.notify_all()

        self.connected = False
        if cap is not None:
            cap.release()
