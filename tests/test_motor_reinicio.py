# -*- coding: utf-8 -*-
"""Detener y volver a iniciar una cámara mientras la conexión anterior sigue colgada."""

import threading
import time
from types import SimpleNamespace

import pytest

from engine import security_engine as se


class StreamFalso:
    creados = []

    def __init__(self, source):
        self.primero = not StreamFalso.creados
        self.libre = threading.Event()
        self.abierto = self.liberado = False
        self.size = (64, 48)
        StreamFalso.creados.append(self)

    def start(self):
        if self.primero:             # sin red: abrir la cámara tarda más que detenerla
            self.libre.wait(30)
        self.abierto = True
        return True

    def read(self):
        time.sleep(0.01)
        return False, None

    def release(self):
        self.liberado = True


@pytest.fixture
def motor(monkeypatch):
    StreamFalso.creados = []
    monkeypatch.setattr(se, "LiveStream", StreamFalso)
    monkeypatch.setattr(se, "STOP_JOIN_S", 0.05, raising=False)
    eng = se.SecurityEngine()
    for metodo in ("_connect_db", "_load_models", "_load_data"):
        monkeypatch.setattr(eng, metodo, lambda: None)
    yield eng
    eng.stop()
    for s in StreamFalso.creados:
        s.libre.set()


def test_la_consola_no_muestra_credenciales_de_la_camara():
    assert se._fuente_segura("rtsp://usuario:clave@10.0.0.5:554/canal") == "rtsp://***@10.0.0.5:554/canal"
    assert se._fuente_segura(0) == "0"


def _esperar(condicion, segundos=3):
    fin = time.time() + segundos
    while time.time() < fin and not condicion():
        time.sleep(0.01)
    return condicion()


def test_reiniciar_no_deja_una_conexion_duplicada(motor):
    cam = SimpleNamespace(source="rtsp://camara/baja", source_hi=None, id="1")
    motor.start(cam)
    assert _esperar(lambda: len(StreamFalso.creados) == 1)
    antiguo = StreamFalso.creados[0]

    motor.stop()
    motor.start(cam)
    assert _esperar(lambda: len(StreamFalso.creados) == 2 and StreamFalso.creados[1].abierto)

    antiguo.libre.set()          # vuelve la red: la conexión anterior termina de abrir
    assert _esperar(lambda: antiguo.liberado), "la conexión anterior quedó activa"
    assert motor.is_running and not StreamFalso.creados[1].liberado
