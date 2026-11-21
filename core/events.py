# -*- coding: utf-8 -*-
"""
core/events.py - Avisos de cambios para aplicar configuración en caliente.

La GUI (o la base de datos) incrementa un contador cuando algo cambia; cada motor
de detección compara el contador con el último que aplicó en su propio hilo y
recarga lo necesario, sin reiniciar el programa.
"""

import threading

_lock = threading.Lock()
_data_version = 0     # residentes, plantillas, consentimientos, vehículos, visitas
_models_version = 0   # rutas de los modelos YOLO


def data_changed():
    global _data_version
    with _lock:
        _data_version += 1


def data_version() -> int:
    return _data_version


def models_changed():
    global _models_version
    with _lock:
        _models_version += 1


def models_version() -> int:
    return _models_version
