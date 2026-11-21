# -*- coding: utf-8 -*-
"""
core/live_stream.py - Lector de baja latencia para streams RTSP/HTTP.

Lee la cámara en su propio hilo y conserva solo el frame más reciente. Si el
loop de detección se demora más que el intervalo entre frames, los frames
viejos se descartan en vez de acumularse en el buffer de FFmpeg, que es lo que
produce el desfase respecto al DVR.
"""

import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

RECONNECT_WAIT_S = 2.0


def is_network_source(source) -> bool:
    return isinstance(source, str) and source.lower().startswith(("rtsp://", "http://", "https://"))


class LiveStream:
    def __init__(self, source: str):
        self._source = source
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cond = threading.Condition()
        self._frame: Optional[np.ndarray] = None
        self._seq = 0
        self._read_seq = 0
        self._cap: Optional[cv2.VideoCapture] = None
        self.size = (0, 0)

    def start(self) -> bool:
        """Abre la fuente de forma síncrona (para conocer la resolución) y lanza el hilo lector."""
        self._cap = self._open()
        if self._cap is None:
            return False
        self.size = (int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                     int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def read(self, timeout_s: float = 2.0) -> Tuple[bool, Optional[np.ndarray]]:
        """Espera un frame más nuevo que el último entregado y lo retorna."""
        with self._cond:
            self._cond.wait_for(lambda: self._seq > self._read_seq or not self._running,
                                timeout=timeout_s)
            if self._seq > self._read_seq:
                self._read_seq = self._seq
                return True, self._frame
            return False, None

    def release(self):
        self._running = False
        with self._cond:
            self._cond.notify_all()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None

    def _open(self) -> Optional[cv2.VideoCapture]:
        cap = cv2.VideoCapture(self._source, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _loop(self):
        cap = self._cap
        while self._running:
            if cap is None:
                cap = self._open()
                if cap is None:
                    print(f"[LiveStream] No se pudo abrir la cámara; reintento en {RECONNECT_WAIT_S:.0f}s")
                    time.sleep(RECONNECT_WAIT_S)
                    continue
                print("[LiveStream] Cámara reconectada")

            ok, frame = cap.read()
            if not ok:
                print("[LiveStream] Se perdió el stream; reconectando")
                cap.release()
                cap = None
                time.sleep(RECONNECT_WAIT_S)
                continue

            with self._cond:
                self._frame = frame
                self._seq += 1
                self._cond.notify_all()

        if cap is not None:
            cap.release()
