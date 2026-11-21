# -*- coding: utf-8 -*-
"""
core/plate_utils.py - Detección y lectura de patentes
OCR: fast-plate-ocr (modelo ONNX entrenado para patentes).
"""

import threading
import cv2
import numpy as np
import config

# un solo lector compartido por todos los motores (uno por cámara)
_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# OCR de patente
# ─────────────────────────────────────────────────────────────────────────────

# Corrección cuando la posición DEBE ser letra pero OCR leyó un dígito
_DIGIT_TO_LETTER = {
    '0': 'O', '1': 'I', '2': 'Z', '4': 'A',
    '5': 'S', '6': 'G', '7': 'T', '8': 'B',
}

# Corrección cuando la posición DEBE ser dígito pero OCR leyó una letra
_LETTER_TO_DIGIT = {
    'O': '0', 'I': '1', 'J': '1', 'L': '1',
    'Z': '2', 'A': '4', 'S': '5', 'G': '6',
    'T': '7', 'B': '8',
}


# El formato nuevo (desde 2007) solo usa consonantes, sin M, N, Ñ ni Q
_NEW_FMT_LETTERS = set("BCDFGHJKLPRSTVWXYZ")

# Formato nuevo: corrección dígito → letra solo en los casos sin ambigüedad.
# 0/O y 5 no se corrigen: con esta tipografía un OCR genérico lee la J como 0 o 5,
# y convertirlos en D o S produce patentes válidas pero equivocadas.
# (fast-plate-ocr no necesita esta corrección; se conserva para lecturas externas.)
_TO_NEW_FMT_LETTER = {'2': 'Z', '6': 'G', '7': 'T', '8': 'B'}


def _clean(text: str) -> str:
    return "".join(c for c in text.upper().strip() if c.isalnum())


def _correct_chilean(text: str) -> str:
    """Corrige caracteres según posición para patentes chilenas.

    Formato nuevo : LLLL-NN  (pos 0-3 letras, 4-5 dígitos)
    Formato antiguo: LL-NNNN (pos 0-1 letras, 2-5 dígitos)
    """
    if len(text) != 6:
        return text

    # Formato nuevo LLLL-NN: al menos 3 de las primeras 4 posiciones son letras
    # Formato antiguo LL-NNNN: solo 2 letras al inicio, resto dígitos
    letters_in_first4 = sum(1 for c in text[:4] if c.isalpha())
    if letters_in_first4 >= 3:
        letters = text[:4].translate(str.maketrans(_TO_NEW_FMT_LETTER))
        digits = text[4:]
    else:
        letters = "".join(_DIGIT_TO_LETTER.get(c, c) for c in text[:2])
        digits = text[2:]
    return letters + "".join(_LETTER_TO_DIGIT.get(c, c) for c in digits)


def _valid_chilean(text: str, moto: bool = False) -> bool:
    """Valida formato estricto de patente chilena tras corrección.

    Autos (6 caracteres): LLLL·NN (2007-, consonantes) y LL·NNNN (1985-2007).
    Motos (5 caracteres), solo si el vehículo se detectó como moto: así una
    lectura incompleta de una patente de auto (AB1234 -> AB123) no pasa como válida.
      LLL·NN  (2014-, consonantes)   ej. SGL·45
      LL·NNN  (antiguo)              ej. AB·123
      LLLL·N  (anunciado para 2027, sin vocales)
    """
    if len(text) == 6:
        # Formato nuevo: 4 consonantes + 2 dígitos
        new_fmt = (all(c in _NEW_FMT_LETTERS for c in text[:4]) and text[4:].isdigit())
        # Formato antiguo: 2 letras + 4 dígitos
        old_fmt = text[:2].isalpha() and text[2:].isdigit()
        return new_fmt or old_fmt
    if len(text) == 5 and moto:
        actual = all(c in _NEW_FMT_LETTERS for c in text[:3]) and text[3:].isdigit()
        antiguo = text[:2].isalpha() and text[2:].isdigit()
        futuro = all(c in _NEW_FMT_LETTERS for c in text[:4]) and text[4].isdigit()
        return actual or antiguo or futuro
    return False


def _format_chilean(text: str) -> str:
    if len(text) == 5:   # moto: letras-números (SGL-45, AB-123, BBBB-0)
        k = len(text) - len(text.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        return f"{text[:k]}-{text[k:]}"
    return f"{text[:2]}-{text[2:4]}-{text[4:6]}"


_plate_ocr = None
_plate_ocr_failed = False


def _get_plate_ocr():
    """Modelo OCR entrenado para patentes (fast-plate-ocr, ONNX en CPU), o None si
    no está disponible: en ese caso no se leen patentes."""
    global _plate_ocr, _plate_ocr_failed
    if _plate_ocr is None and not _plate_ocr_failed:
        try:
            from fast_plate_ocr import LicensePlateRecognizer
            _plate_ocr = LicensePlateRecognizer(config.PLATE_OCR_MODEL, device="cpu")
            print(f"[PlateUtils] OCR de patentes: {config.PLATE_OCR_MODEL}")
        except Exception as e:
            _plate_ocr_failed = True
            print(f"[PlateUtils] ERROR: fast-plate-ocr no disponible ({e}); "
                  f"no se leerán patentes")
    return _plate_ocr


def _read_fast_plate(model, plate_img: np.ndarray, moto: bool = False) -> tuple:
    """El modelo es fiable por sí solo: no se corrigen caracteres, solo se exige
    formato chileno y que ningún carácter quede bajo PLATE_MIN_CHAR_CONF."""
    with _lock:
        pred = model.run(plate_img, return_confidence=True)[0]
    text = _clean(pred.plate)
    if not _valid_chilean(text, moto):
        tipo = "de moto" if moto else "de auto"
        print(f"[PlateUtils] Lectura '{text}' descartada: no es formato chileno {tipo}")
        return None, None
    score = float(np.min(pred.char_probs[:len(pred.plate)]))
    if score < config.PLATE_MIN_CHAR_CONF:
        print(f"[PlateUtils] Lectura '{text}' descartada: confianza {score:.0%} "
              f"< {config.PLATE_MIN_CHAR_CONF:.0%}")
        return None, None
    return _format_chilean(text), score


def read_license_plate(plate_img: np.ndarray, moto: bool = False) -> tuple:
    """Retorna (patente_formateada, score) o (None, None).
    moto=True habilita los formatos de 5 caracteres de las motocicletas."""
    model = _get_plate_ocr()
    if model is None:
        return None, None
    try:
        return _read_fast_plate(model, plate_img, moto)
    except Exception as e:
        print(f"[PlateUtils] OCR error: {e}")
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Asociar placa detectada al vehículo rastreado
# ─────────────────────────────────────────────────────────────────────────────

def get_car(license_plate: tuple, track_ids: np.ndarray) -> tuple:
    """Retorna la tupla (x1,y1,x2,y2,car_id) del vehículo que contiene la placa."""
    x1, y1, x2, y2 = license_plate[:4]
    for row in track_ids:
        cx1, cy1, cx2, cy2, cid = row[:5]
        if x1 > cx1 and y1 > cy1 and x2 < cx2 and y2 < cy2:
            return cx1, cy1, cx2, cy2, cid
    return -1, -1, -1, -1, -1


# ─────────────────────────────────────────────────────────────────────────────
# Carga de patentes registradas desde BD
# ─────────────────────────────────────────────────────────────────────────────

def load_registered_plates(db) -> tuple:
    """Retorna (patentes de residentes, patentes de visitas activas), sin guiones."""
    residents = db.get_patentes_autorizadas()
    visits = db.get_patentes_visitas_activas()
    print(f"[PlateUtils] {len(residents)} patentes de residentes, {len(visits)} de visitas")
    return residents, visits


# ─────────────────────────────────────────────────────────────────────────────
# Drawing helpers
# ─────────────────────────────────────────────────────────────────────────────

def draw_vehicles(frame: np.ndarray, active_vehicles: dict, vehicle_data: dict):
    for cid, data in active_vehicles.items():
        x1, y1, x2, y2 = data["bbox"]
        color = (150, 150, 150)
        label = f"Vehiculo {cid}"  # cv2.putText no dibuja tildes

        if cid in vehicle_data:
            info = vehicle_data[cid]
            color = {"residente": (0, 255, 0), "visita": (255, 200, 0)}.get(
                info.get("status"), (0, 165, 255))
            label = info.get("label", info["plate"])
            if "plate_bbox" in info:
                px1, py1, px2, py2 = info["plate_bbox"]
                cv2.rectangle(frame, (px1, py1), (px2, py2), color, 2)

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
        bg_y1 = max(0, y1 - 35)
        cv2.rectangle(frame, (x1, bg_y1), (x2, y1), color, -1)
        cv2.putText(frame, label, (x1 + 5, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)


def cleanup_old_vehicles(
    current_frame: int, active_vehicles: dict, vehicle_data: dict,
    timeout: int = None,
):
    if timeout is None:
        timeout = config.VEHICLE_TIMEOUT
    stale = [
        vid for vid, d in active_vehicles.items()
        if current_frame - d["last_frame"] > timeout
    ]
    for vid in stale:
        active_vehicles.pop(vid, None)
        vehicle_data.pop(vid, None)
