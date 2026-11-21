# -*- coding: utf-8 -*-
"""
core/camera_manager.py - Cámaras del condominio almacenadas en la base local (zona y camara).
Soporta: USB, RTSP (Hikvision/Dahua), DroidCam, archivo de video.
"""

import cv2
from dataclasses import dataclass, field
from typing import Optional, Union

from database import DatabaseManager

TIPOS_FUENTE = ["usb", "rtsp", "droidcam", "file"]


def _parse_source(raw: str, tipo: str) -> Union[int, str]:
    """Las cámaras USB se abren por índice entero."""
    if tipo == "usb":
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    return raw


@dataclass
class CameraConfig:
    id: str                       # idcamara como texto
    name: str
    source: Union[int, str]
    type: str = "rtsp"
    enabled: bool = True
    idzona: Optional[int] = None
    zona: str = ""
    resolution: list = field(default_factory=lambda: [1280, 720])
    fps: int = 30
    # canal principal (alta resolución); `source` pasa a ser el substream de detección
    source_hi: Optional[str] = None

    @staticmethod
    def from_row(r: dict) -> "CameraConfig":
        return CameraConfig(
            id=str(r["idcamara"]), name=r["nombre"],
            source=_parse_source(r["fuente"], r["tipo_fuente"]),
            type=r["tipo_fuente"], enabled=bool(r["activa"]),
            idzona=r["idzona"], zona=r["zona"],
            resolution=[r["ancho"], r["alto"]], fps=r["fps"],
            source_hi=r.get("fuente_alta") or None,
        )


class CameraManager:
    """Carga y guarda las cámaras del condominio de la sesión activa."""

    def __init__(self):
        self.db = DatabaseManager()
        self.cameras: list[CameraConfig] = []
        self.load()

    def _ensure_db(self) -> bool:
        return self.db.is_connected() or self.db.connect()

    # ── persistencia ──────────────────────────────────────────────────────

    def load(self):
        if not self._ensure_db():
            self.cameras = []
            return
        try:
            self.cameras = [CameraConfig.from_row(r) for r in self.db.list_camaras()]
        except Exception as e:
            print(f"[CameraManager] Error al leer cámaras: {e}")
            self.cameras = []

    def zonas(self) -> list:
        if not self._ensure_db():
            return []
        return self.db.list_zonas()

    def add(self, cam: CameraConfig, zona_nombre: str):
        self._ensure_db()
        idzona = self.db.get_or_create_zona(zona_nombre)
        self.db.create_camara(idzona, cam.name, cam.type, cam.source,
                              cam.resolution[0], cam.resolution[1], cam.fps, cam.enabled,
                              cam.source_hi)
        self.load()

    def update(self, cam: CameraConfig, zona_nombre: str):
        self._ensure_db()
        idzona = self.db.get_or_create_zona(zona_nombre)
        self.db.update_camara(int(cam.id), idzona, cam.name, cam.type, cam.source,
                              cam.resolution[0], cam.resolution[1], cam.fps, cam.enabled,
                              cam.source_hi)
        self.load()

    def remove(self, cam_id: str):
        self._ensure_db()
        self.db.delete_camara(int(cam_id))
        self.load()

    # ── consultas ─────────────────────────────────────────────────────────

    def get_enabled(self) -> list[CameraConfig]:
        return [c for c in self.cameras if c.enabled]

    def get_by_id(self, cam_id: str) -> Optional[CameraConfig]:
        return next((c for c in self.cameras if c.id == cam_id), None)

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def open_capture(cam: CameraConfig) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(cam.source)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam.resolution[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam.resolution[1])
            cap.set(cv2.CAP_PROP_FPS, cam.fps)
        return cap

    @staticmethod
    def test_source(source: Union[int, str]) -> bool:
        cap = cv2.VideoCapture(source)
        ok = cap.isOpened()
        cap.release()
        return ok
