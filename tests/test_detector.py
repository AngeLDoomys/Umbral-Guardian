# -*- coding: utf-8 -*-
"""Detectores ONNX (core/detector.py): RF-DETR Nano y detector de patentes."""

import glob
import os
import subprocess
import sys

import cv2
import numpy as np
import pytest

import config
from core.detector import OnnxDetector, _COCO91_TO_80

ROOT = config.BASE_DIR
EVID = os.path.join(ROOT, "tests", "evidencias")


def _modelo(ruta):
    if not os.path.exists(ruta):
        pytest.skip(f"falta {ruta}")
    return OnnxDetector(ruta)


class TestClases:
    def test_ids_coco_se_traducen_a_los_indices_de_ultralytics(self):
        # persona, bicicleta, auto, moto, bus, camión
        assert [_COCO91_TO_80[c] for c in (1, 2, 3, 4, 6, 8)] == [0, 1, 2, 3, 5, 7]
        assert set(config.VEHICLES_CLASS) == {2, 3, 5, 7}

    def test_categorias_sin_uso_en_coco_no_tienen_indice(self):
        assert 12 not in _COCO91_TO_80 and 0 not in _COCO91_TO_80


@pytest.fixture(scope="module")
def rfdetr():
    return _modelo(config.DETECTOR_MODEL)


@pytest.fixture(scope="module")
def patentes():
    return _modelo(config.PLATE_DETECTOR_MODEL)


class TestGPUCompartida:
    def test_directml_usa_una_sesion_por_modelo_y_un_solo_candado(self, rfdetr, patentes):
        # dos cámaras usando DirectML a la vez botaban el programa dentro del driver
        if rfdetr.provider != "DmlExecutionProvider":
            pytest.skip("solo aplica a DirectML")
        otra_camara = _modelo(config.DETECTOR_MODEL)
        assert otra_camara._session is rfdetr._session
        assert otra_camara._lock is rfdetr._lock is patentes._lock


class TestRFDETR:
    @pytest.fixture
    def det(self, rfdetr):
        return rfdetr

    def test_formato_de_filas_y_filtro_de_clases(self, det):
        img = cv2.imread(glob.glob(os.path.join(EVID, "PI-04a*.png"))[0])
        rows = det.detect(img, classes=[0])
        assert rows and all(len(r) == 6 and r[5] == 0 for r in rows)
        h, w = img.shape[:2]
        assert all(0 <= r[0] < r[2] <= w + 1 and 0 <= r[1] < r[3] <= h + 1 for r in rows)

    def test_detecta_a_la_persona_con_el_umbral_calibrado(self, det):
        img = cv2.imread(glob.glob(os.path.join(EVID, "PI-04a*.png"))[0])
        assert any(r[4] >= config.PERSON_CONFIDENCE for r in det.detect(img, classes=[0]))

    def test_imagen_vacia_no_falla(self, det):
        assert det.detect(np.zeros((0, 0, 3), np.uint8)) == []

    def test_imagen_negra_no_tiene_personas_sobre_el_umbral(self, det):
        rows = det.detect(np.zeros((360, 640, 3), np.uint8), classes=[0])
        assert not [r for r in rows if r[4] >= config.PERSON_CONFIDENCE]


class TestDetectorPatentes:
    @pytest.fixture
    def det(self, patentes):
        return patentes

    def test_encuentra_la_patente_de_la_evidencia(self, det):
        img = cv2.imread(os.path.join(EVID, "PI-06b_patente_no_registrada_2.png"))
        plates = [r for r in det.detect(img) if r[4] >= config.PLATE_CONFIDENCE]
        assert plates and all(r[5] == 0 for r in plates)

    def test_recorte_no_cuadrado_conserva_coordenadas(self, det):
        img = cv2.imread(os.path.join(EVID, "PI-06b_patente_no_registrada_2.png"))
        a = max(det.detect(img), key=lambda r: r[4])
        x1, y1, x2, y2 = (int(v) for v in a[:4])
        # recorte alrededor de la patente (lo que hace el canal de alta resolución)
        pad = 80
        sub = img[max(0, y1 - pad):y2 + pad, max(0, x1 - 2 * pad):x2 + 2 * pad]
        b = max(det.detect(sub), key=lambda r: r[4])
        assert abs((b[0] + max(0, x1 - 2 * pad)) - a[0]) < 8
        assert abs((b[1] + max(0, y1 - pad)) - a[1]) < 8


def test_el_motor_no_carga_torch_ultralytics_easyocr_deepface_ni_tensorflow():
    codigo = ("import sys; sys.path.insert(0, r'%s'); import engine.security_engine, core.plate_utils; "
              "import gui.view_residents, gui.view_history; "
              "print(sorted(m for m in ('torch', 'ultralytics', 'easyocr', 'deepface', 'tensorflow') "
              "if m in sys.modules))" % ROOT)
    out = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                         timeout=300, cwd=ROOT)
    assert out.stdout.strip().splitlines()[-1] == "[]", out.stdout + out.stderr
