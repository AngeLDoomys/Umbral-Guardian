# -*- coding: utf-8 -*-
"""Reconocimiento facial con YuNet + SFace (core/face_utils.py) y su votación en el motor.
Usa los rostros reales de las evidencias: PI-04a (residente) y PI-05 (no registrado)."""

import glob
import os

import cv2
import numpy as np
import pytest

import config
from core import face_utils as fu

EVID = os.path.join(config.BASE_DIR, "tests", "evidencias")


def _img(prefijo):
    rutas = glob.glob(os.path.join(EVID, prefijo + "*.png"))
    if not rutas:
        pytest.skip(f"falta la evidencia {prefijo}")
    return cv2.imread(rutas[0])


def _otro_cuadro(img, dx=3, dy=-2, seed=0):
    """El mismo rostro en otro cuadro de video: desplazado, con ruido y recomprimido."""
    rng = np.random.default_rng(seed)
    m = np.float32([[1, 0, dx], [0, 1, dy]])
    out = cv2.warpAffine(img, m, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REFLECT)
    out = np.clip(out + rng.normal(0, 3, out.shape), 0, 255).astype(np.uint8)
    return cv2.imdecode(cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 80])[1], cv2.IMREAD_COLOR)


@pytest.fixture(scope="module")
def residente():
    emb = fu.compute_embedding(_img("PI-04a"))
    return [{"name": "Residente Prueba", "unidad": "Casa 1", "embedding": emb, "idresidente": 1}]


class TestModelo:
    def test_embedding_de_128_dimensiones_float32(self):
        info = fu.extract_face(_img("PI-04a"))
        assert info["embedding"].shape == (128,) and info["embedding"].dtype == np.float32

    def test_sin_rostro_retorna_none(self):
        assert fu.extract_face(np.zeros((480, 640, 3), np.uint8)) is None
        assert fu.recognize_face(np.zeros((480, 640, 3), np.uint8), [])["status"] == "no_face"

    def test_imagen_grande_se_detecta_igual(self):
        img = _img("PI-04a")
        grande = cv2.resize(img, None, fx=2.0, fy=2.0)
        a, b = fu.extract_face(img), fu.extract_face(grande)
        dist = 1 - np.dot(a["embedding"], b["embedding"]) / (
            np.linalg.norm(a["embedding"]) * np.linalg.norm(b["embedding"]))
        assert dist < 0.1


class TestUmbrales:
    def test_el_residente_se_reconoce_en_otro_cuadro(self, residente):
        res = fu.recognize_face(_otro_cuadro(_img("PI-04a")), residente)
        assert res["status"] == "match" and res["idresidente"] == 1
        assert res["distance"] < config.FACE_RECOGNITION_THRESHOLD

    def test_la_persona_no_registrada_no_se_confunde(self, residente):
        res = fu.recognize_face(_img("PI-05"), residente)
        assert res["status"] == "no_match"
        assert res["distance"] >= config.FACE_RECOGNITION_THRESHOLD

    def test_margen_evita_decidir_entre_dos_plantillas_casi_iguales(self, residente):
        gemelo = dict(residente[0], idresidente=2, name="Gemelo")
        res = fu.recognize_face(_otro_cuadro(_img("PI-04a")), residente + [gemelo])
        assert res["status"] == "no_match"     # misma distancia a dos residentes: no decide

    def test_plantillas_de_otro_modelo_se_ignoran(self, residente):
        arcface = [dict(residente[0], embedding=np.random.rand(512).astype(np.float32))]
        res = fu.recognize_face(_img("PI-04a"), arcface)
        assert res["status"] == "no_match" and res["distance"] is None


class TestVotacionConUmbralesNuevos:
    """El motor real con recognize_face real: 2 confirmaciones y corte de 5 intentos."""

    @pytest.fixture
    def motor(self, residente):
        from engine.security_engine import SecurityEngine
        eng = SecurityEngine()
        eng.known_faces = residente
        eng._person_memory[7] = {"name": None, "display_name": "", "attempts": 0, "votes": {},
                                 "candidates": {}, "is_registered": False}
        return eng

    def test_residente_confirmado_con_dos_coincidencias(self, motor):
        img = _img("PI-04a")
        motor._do_recognition(_otro_cuadro(img, seed=1), 7, 1)
        assert not motor._person_memory[7]["is_registered"]          # 1 voto: todavía no
        motor._do_recognition(_otro_cuadro(img, dx=-2, dy=3, seed=2), 7, 2)
        p = motor._person_memory[7]
        assert p["is_registered"] and p["idresidente"] == 1 and p["attempts"] == 2

    def test_no_registrado_tras_cinco_intentos(self, motor):
        img = _img("PI-05")
        for k in range(config.FACE_MAX_ATTEMPTS - 1):
            motor._do_recognition(_otro_cuadro(img, seed=k), 7, k)
            assert motor._person_memory[7]["name"] is None
        motor._do_recognition(_otro_cuadro(img, seed=9), 7, 9)
        p = motor._person_memory[7]
        assert p["display_name"] == "NO RECONOCIDO" and not p["is_registered"]
        assert p["attempts"] == config.FACE_MAX_ATTEMPTS

    def test_otra_persona_en_el_mismo_lugar_no_hereda_el_nombre(self, motor):
        # el seguimiento es por posición: si el residente se va y otra persona ocupa
        # su lugar, la verificación periódica descarta la identidad
        img = _img("PI-04a")
        motor._do_recognition(_otro_cuadro(img, seed=1), 7, 1)
        motor._do_recognition(_otro_cuadro(img, dx=-2, dy=3, seed=2), 7, 2)
        p = motor._person_memory[7]
        assert p["is_registered"] and p["recheck_at"] > 0
        motor._do_recognition(_otro_cuadro(img, seed=3), 7, 3)     # sigue siendo él
        assert p["is_registered"] and p["contra"] == 0
        otro = _img("PI-05")
        motor._do_recognition(_otro_cuadro(otro, seed=4), 7, 4)
        assert p["is_registered"]                                   # 1 rostro distinto: no basta
        motor._do_recognition(_otro_cuadro(otro, seed=5), 7, 5)
        assert not p["is_registered"] and p["name"] is None and p["votes"] == {}
        assert p["display_name"] == "Analizando..."

    def test_tras_cruzarse_basta_un_rostro_distinto(self, motor):
        img = _img("PI-04a")
        motor._do_recognition(_otro_cuadro(img, seed=1), 7, 1)
        motor._do_recognition(_otro_cuadro(img, dx=-2, dy=3, seed=2), 7, 2)
        p = motor._person_memory[7]
        assert p["is_registered"]
        p["post_cruce"] = True          # el motor lo marca al separarse de otra persona
        motor._do_recognition(_otro_cuadro(_img("PI-05"), seed=4), 7, 4)
        assert not p["is_registered"] and p["display_name"] == "Analizando..."
