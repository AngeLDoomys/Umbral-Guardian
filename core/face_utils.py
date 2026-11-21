# -*- coding: utf-8 -*-
"""
core/face_utils.py - Reconocimiento facial thread-safe con OpenCV
(detector YuNet con alineación por puntos faciales + SFace, filtros de calidad)
"""

import cv2
import numpy as np
import threading
import unicodedata
from typing import Optional

import config

# los objetos de OpenCV DNN no son thread-safe: un solo detector y un solo
# reconocedor compartidos por todos los motores y la interfaz, bajo este candado
_lock = threading.Lock()
_detector = None
_recognizer = None

# YuNet pierde rostros en imágenes grandes: se detecta con el lado mayor a 640 px
# y las coordenadas se llevan a la imagen original (igual que lo hacía DeepFace)
_MAX_DETECT_SIDE = 640.0


def _models():
    global _detector, _recognizer
    if _detector is None:
        _detector = cv2.FaceDetectorYN.create(config.FACE_DETECTOR_MODEL, "", (320, 320))
        _recognizer = cv2.FaceRecognizerSF.create(config.FACE_RECOGNIZER_MODEL, "")
        print(f"[FaceUtils] YuNet + {config.FACE_MODEL} cargados")
    return _detector, _recognizer


# ─────────────────────────────────────────────────────────────────────────────
# Carga de embeddings desde BD
# ─────────────────────────────────────────────────────────────────────────────

def load_known_faces(db) -> list:
    """Plantillas de residentes con consentimiento vigente y sin bloqueo, y de las
    visitas autorizadas para hoy. 'clave' identifica a la persona en la votación:
    ('r', idresidente) o ('v', idautorizacion)."""
    known = [
        {
            "name": f"{r['nombres']} {r['apellidos']}",
            "unidad": r["unidad"],
            "embedding": r["embedding"],
            "idresidente": r["idresidente"],
            "tipo": "residente", "clave": ("r", r["idresidente"]),
        }
        for r in db.get_plantillas_activas(config.FACE_MODEL)
    ]
    visitas = [
        {
            "name": f"{v['nombres']} {v['apellidos']}",
            "unidad": v["unidad"],
            "embedding": v["embedding"],
            "idresidente": None, "idautorizacion": v["idautorizacion"],
            "tipo": "visita", "clave": ("v", v["idautorizacion"]),
        }
        for v in db.get_plantillas_visita_vigentes(config.FACE_MODEL)
    ]
    print(f"[FaceUtils] {len(known)} plantillas de residentes y {len(visitas)} de visitas "
          f"autorizadas hoy")
    return known + visitas


def _clave(known: dict) -> tuple:
    return known.get("clave") or ("r", known["idresidente"])


def _sharpness(face: np.ndarray) -> float:
    """Varianza del Laplaciano sobre el rostro llevado a 112 px: baja = borroso."""
    gray = cv2.cvtColor(cv2.resize(face, (112, 112)), cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def extract_face(img: np.ndarray) -> Optional[dict]:
    """Detecta (YuNet), alinea y calcula el vector SFace del rostro más grande de la imagen.
    Retorna {'embedding', 'face', 'confidence', 'sharpness'} o None si no hay rostro."""
    if img is None or img.size == 0:
        return None
    h, w = img.shape[:2]
    r = min(1.0, _MAX_DETECT_SIDE / max(h, w))
    small = cv2.resize(img, (int(w * r), int(h * r))) if r < 1.0 else img
    with _lock:
        detector, recognizer = _models()
        detector.setInputSize((small.shape[1], small.shape[0]))
        # los rostros de cámaras de seguridad (vistos desde arriba, comprimidos)
        # quedan en 0.90-0.94: se usa el mismo umbral que el filtro de calidad
        detector.setScoreThreshold(float(config.FACE_MIN_DETECTION_CONF))
        _, faces = detector.detect(small)
        if faces is None or len(faces) == 0:
            return None
        faces = faces.copy()
        faces[:, :14] /= r               # caja y 5 puntos faciales, en la imagen original
        best = max(faces, key=lambda f: f[2] * f[3])
        # alineación por ojos, nariz y boca a 112x112, y vector de 128 dimensiones
        embedding = recognizer.feature(recognizer.alignCrop(img, best)).flatten()
    x, y, fw, fh = (int(v) for v in best[:4])
    x, y = max(0, x), max(0, y)          # YuNet da negativos si el rostro toca el borde
    face = img[y:min(h, y + fh), x:min(w, x + fw)]
    if face.size == 0:
        return None
    return {
        "embedding": np.asarray(embedding, dtype=np.float32),
        "face": face,
        "confidence": float(best[14]),
        "sharpness": _sharpness(face),
    }


def quality_problem(info: dict) -> Optional[str]:
    """Motivo por el que un rostro no sirve para decidir, o None si es usable."""
    if info["face"].shape[0] < config.MIN_FACE_SIZE or info["face"].shape[1] < config.MIN_FACE_SIZE:
        return f"rostro pequeño ({info['face'].shape[1]}x{info['face'].shape[0]} px)"
    if info["confidence"] < config.FACE_MIN_DETECTION_CONF:
        return f"detección dudosa ({info['confidence']:.2f})"
    if info["sharpness"] < config.FACE_MIN_SHARPNESS:
        return f"borroso (nitidez {info['sharpness']:.0f})"
    return None


def compute_embedding(face_img: np.ndarray) -> list:
    """Vector facial para enrolar o buscar por foto. Exige un rostro nítido: una
    plantilla mala provoca confusiones en todos los reconocimientos posteriores."""
    info = extract_face(face_img)
    if info is None:
        raise ValueError("No se detectó un rostro en la imagen")
    problem = quality_problem(info)
    if problem:
        raise ValueError(f"Rostro no apto para plantilla: {problem}")
    return info["embedding"].tolist()


# ─────────────────────────────────────────────────────────────────────────────
# Reconocimiento
# ─────────────────────────────────────────────────────────────────────────────

def recognize_face(img: np.ndarray, known_faces: list) -> dict:
    """Busca un rostro en la imagen (región de la persona) y lo compara con las plantillas.

    Retorna un dict con 'status':
      'no_face' | 'low_quality'  → el intento no cuenta para la decisión
      'match'                    → + name, unidad, confidence, idresidente
      'no_match'                 → rostro válido que no corresponde a ningún residente
    y 'face' (recorte del rostro) cuando se encontró uno.
    """
    info = extract_face(img)
    if info is None:
        return {"status": "no_face"}
    problem = quality_problem(info)
    if problem:
        return {"status": "low_quality", "face": info["face"], "reason": problem}
    if not known_faces:
        return {"status": "no_match", "face": info["face"], "distance": None}

    test = info["embedding"] / (np.linalg.norm(info["embedding"]) + 1e-9)
    # distancia coseno mínima por residente (cada uno puede tener varias plantillas)
    per_resident: dict = {}
    for known in known_faces:
        emb = np.asarray(known["embedding"], dtype=np.float32)
        if emb.shape != test.shape:  # plantilla de otro modelo
            continue
        dist = 1.0 - float(np.dot(test, emb / (np.linalg.norm(emb) + 1e-9)))
        rid = _clave(known)   # cada persona (residente o visita) puede tener varias plantillas
        if rid not in per_resident or dist < per_resident[rid][0]:
            per_resident[rid] = (dist, known)

    if not per_resident:
        return {"status": "no_match", "face": info["face"], "distance": None}

    ranked = sorted(per_resident.values(), key=lambda x: x[0])
    best_dist, best = ranked[0]
    second_dist = ranked[1][0] if len(ranked) > 1 else 1.0
    # además del umbral, el mejor debe destacar sobre el segundo residente:
    # si dos residentes se parecen casi igual, es preferible no decidir
    if best_dist < config.FACE_RECOGNITION_THRESHOLD and \
            second_dist - best_dist >= config.FACE_MATCH_MARGIN:
        return {
            "status": "match", "face": info["face"],
            "name": best["name"], "unidad": best["unidad"],
            "idresidente": best["idresidente"],
            "tipo": best.get("tipo", "residente"), "clave": _clave(best),
            "idautorizacion": best.get("idautorizacion"),
            "confidence": 1.0 - best_dist, "distance": best_dist,
        }
    return {"status": "no_match", "face": info["face"], "distance": best_dist}


# ─────────────────────────────────────────────────────────────────────────────
# Overlay helpers
# ─────────────────────────────────────────────────────────────────────────────

def texto_video(texto: str) -> str:
    """OpenCV solo dibuja ASCII: «pequeño» saldría como «peque??»."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def draw_persons(frame: np.ndarray, person_memory: dict, current_frame: int = None,
                 max_age: int = None):
    """Dibuja a las personas detectadas hace a lo más `max_age` cuadros. Las que
    dejaron de verse siguen en memoria (conservan su identidad si reaparecen),
    pero no se dibujan: así no quedan recuadros fantasma superpuestos."""
    for pid, data in person_memory.items():
        if current_frame is not None and max_age is not None \
                and current_frame - data["last_seen"] > max_age:
            continue
        # la detección corre cada N cuadros: entre una y otra el recuadro avanza con
        # la velocidad medida, en vez de quedarse quieto y saltar
        x1, y1, x2, y2 = predicted_bbox(data, current_frame)
        color = data["color"]
        label = texto_video(data["display_name"])
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
        bg_y1 = max(0, y1 - 35)
        # la etiqueta completa debe caber en la imagen (el canal bajo mide 352 px):
        # se achica si hace falta y se corre a la izquierda si la persona está al borde
        ancho_img = frame.shape[1]
        escala, grosor = 0.6, 2
        ancho = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, escala, grosor)[0][0]
        if ancho + 10 > ancho_img:
            escala *= (ancho_img - 10) / ancho
            grosor = 1
            ancho = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, escala, grosor)[0][0]
        tx = max(0, min(x1, ancho_img - ancho - 10))
        cv2.rectangle(frame, (tx, bg_y1), (max(x2, tx + ancho + 10), y1), color, -1)
        cv2.putText(
            frame, label, (tx + 5, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX, escala, (255, 255, 255), grosor,
        )


def overlay_face_zoom(
    frame: np.ndarray,
    face_crop: np.ndarray,
    label: str = "",
    size: int = None,
) -> np.ndarray:
    if size is None:
        size = config.ZOOM_SIZE
    if face_crop is None or face_crop.size == 0:
        return frame
    h, w = frame.shape[:2]
    try:
        zoom = cv2.resize(face_crop, (size, size))
        xo, yo = w - size - 20, 20
        cv2.rectangle(frame, (xo - 5, yo - 5), (xo + size + 5, yo + size + 5), (0, 255, 255), 3)
        frame[yo: yo + size, xo: xo + size] = zoom
        if label:
            cv2.putText(frame, label, (xo, yo + size + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    except Exception:
        pass
    return frame


# ─────────────────────────────────────────────────────────────────────────────
# Tracking helpers
# ─────────────────────────────────────────────────────────────────────────────

def _iou(a: tuple, b: tuple) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def predicted_bbox(data: dict, current_frame: int = None) -> tuple:
    """Dónde debería estar la persona ahora, según su última caja y su velocidad.
    Al cruzarse dos personas que caminan en sentidos opuestos, comparar con la
    posición predicha (y no con la última vista) evita que intercambien identidad."""
    vel = data.get("vel")
    if not vel or current_frame is None:
        return data["bbox"]
    dt = min(current_frame - data["last_seen"], 2 * config.PROCESS_EVERY_N_FRAMES)
    if dt <= 0:
        return data["bbox"]
    return tuple(int(c + v * dt) for c, v in zip(data["bbox"], vel))


def assign_person_ids(bboxes: list, person_memory: dict, counter: list,
                      min_iou: float = None, threshold: float = None,
                      current_frame: int = None) -> list:
    """Asocia las detecciones de un cuadro con las personas ya seguidas, uno a uno.

    Primero se emparejan los pares con mayor superposición (IoU); las detecciones
    sin superposición suficiente se asocian a la persona libre más cercana, si su
    centro está a menos de `threshold` px. Una persona nunca recibe dos detecciones
    del mismo cuadro, de modo que dos personas juntas no intercambian identidad.
    Las detecciones sin pareja reciben un identificador nuevo.
    """
    if min_iou is None:
        min_iou = config.PERSON_MIN_IOU
    if threshold is None:
        threshold = config.PERSON_DISTANCE_THRESHOLD

    def centro(b):
        return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2

    pids = list(person_memory)
    out = [None] * len(bboxes)
    libres = set(pids)
    pred = {p: predicted_bbox(person_memory[p], current_frame) for p in pids}

    pares = sorted(((_iou(b, pred[p]), i, p)
                    for i, b in enumerate(bboxes) for p in pids), reverse=True)
    for iou, i, p in pares:
        if iou < min_iou:
            break
        if out[i] is None and p in libres:
            out[i] = p
            libres.discard(p)

    pendientes = [i for i in range(len(bboxes)) if out[i] is None]
    cercanos = []
    for i in pendientes:
        cx, cy = centro(bboxes[i])
        for p in libres:
            px, py = centro(pred[p])
            d = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
            if d < threshold:
                cercanos.append((d, i, p))
    for d, i, p in sorted(cercanos):
        if out[i] is None and p in libres:
            out[i] = p
            libres.discard(p)

    for i in range(len(bboxes)):
        if out[i] is None:
            out[i] = f"P{counter[0]}"
            counter[0] += 1
    return out


def clean_old_persons(current_frame: int, person_memory: dict, timeout: int = None):
    if timeout is None:
        timeout = config.PERSON_TIMEOUT
    stale = [
        pid for pid, d in person_memory.items()
        if current_frame - d["last_seen"] > timeout
    ]
    for pid in stale:
        del person_memory[pid]
