# -*- coding: utf-8 -*-
"""Vista de cámaras tipo grabador: el video llena su espacio sin franjas ni deformación."""

import numpy as np
import pytest

from gui.view_monitor import CameraSlot


@pytest.mark.parametrize("w, h, aspect, esperado", [
    (1280, 1000, 16 / 9, (1280, 720)),   # panel alto: manda el ancho
    (2000, 720, 16 / 9, (1280, 720)),    # panel ancho: manda el alto
    (800, 800, 4 / 3, (800, 600)),       # webcam 4:3
    (640, 360, 16 / 9, (640, 360)),      # justo la proporción
])
def test_mayor_rectangulo_con_la_proporcion_del_video(w, h, aspect, esperado):
    tw, th = CameraSlot._fit(w, h, aspect)
    assert (tw, th) == esperado
    assert tw <= w and th <= h
    assert abs(tw / th - aspect) < 0.01   # sin deformación


def test_el_nombre_de_la_camara_se_dibuja_con_tildes():
    from PIL import Image

    class Falso:
        _osd_text = "1 · Portón"
        _fonts = {}
        _font = classmethod(CameraSlot._font.__func__)

    img = Image.new("RGB", (640, 360), (255, 255, 255))
    out = CameraSlot._draw_osd(Falso(), img)
    esquina = np.asarray(out)[6:30, 6:60]
    assert (esquina < 50).any() and (esquina > 200).any()   # fondo negro y texto blanco
