# -*- coding: utf-8 -*-
"""
engine/security_engine.py - Motor de detección Umbral Guardian
RF-DETR Nano y detector de patentes en ONNX (onnxruntime) + YuNet/SFace (OpenCV) +
fast-plate-ocr + tracker IoU propio
Diseño: clase SecurityEngine con hilos, callbacks hacia la GUI.
"""

import os

# RTSP por TCP y sin buffer de FFmpeg: menos desfase respecto al DVR.
# Debe definirse antes de abrir cualquier VideoCapture.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0",
)

import cv2
import numpy as np
import time
import threading
import queue
from collections import defaultdict, deque
from datetime import datetime
from typing import Callable, Optional

import config
from core import events
from database import DatabaseManager
from core.face_utils import (
    load_known_faces, recognize_face,
    draw_persons, overlay_face_zoom, assign_person_ids, clean_old_persons, _iou,
)
from core.plate_utils import (
    load_registered_plates, read_license_plate, get_car,
    draw_vehicles, cleanup_old_vehicles,
)
from core.security import clean_plate
from core.tracker import IoUTracker
from core.detector import OnnxDetector
from core.gpu import get_device_info
from core.hires_stream import HighResStream
from core.live_stream import LiveStream, is_network_source

RELOAD_EVERY_S = 60  # recarga de residentes, patentes y visitas
MOTO_CLASS = 3       # índice COCO de motocicleta
LATENCY_REPORT_EVERY_S = 10  # resumen de latencias en consola
STOP_JOIN_S = 5      # espera máxima a cada hilo al detener una cámara


def _fuente_segura(fuente) -> str:
    """La URL de la cámara sin usuario ni contraseña, para mostrarla en la consola."""
    texto = str(fuente)
    if "@" not in texto or "://" not in texto:
        return texto
    return texto.split("://", 1)[0] + "://***@" + texto.rsplit("@", 1)[1]


def _ms_since(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000


def _scale_box(box, sx: float, sy: float, pad: float, w: int, h: int) -> tuple:
    """Lleva un bbox del frame de detección al frame de recorte, con margen y recortado al borde."""
    x1, y1, x2, y2 = box
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    return (
        max(0, int((x1 - px) * sx)), max(0, int((y1 - py) * sy)),
        min(w, int((x2 + px) * sx)), min(h, int((y2 + py) * sy)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Medición de latencia
# ─────────────────────────────────────────────────────────────────────────────

class LatencyMeter:
    """Ventana móvil de tiempos (ms) por etapa: promedio, p95 y máximo.
    Thread-safe: los hilos de OCR y rostros también registran muestras."""

    def __init__(self, window: int = 200):
        self._lock = threading.Lock()
        self._samples = defaultdict(lambda: deque(maxlen=window))

    def add(self, stage: str, ms: float):
        with self._lock:
            self._samples[stage].append(ms)

    def clear(self):
        with self._lock:
            self._samples.clear()

    def summary(self, stage: str) -> Optional[dict]:
        with self._lock:
            s = self._samples.get(stage)
            if not s:
                return None
            arr = np.array(s, dtype=float)
        return {
            "avg": float(arr.mean()),
            "p95": float(np.percentile(arr, 95)),
            "max": float(arr.max()),
            "n": len(arr),
        }

    def report(self) -> str:
        with self._lock:
            stages = list(self._samples)
        parts = []
        for stage in stages:
            s = self.summary(stage)
            if s:
                parts.append(f"  {stage:<14} avg={s['avg']:7.1f}  p95={s['p95']:7.1f}  "
                             f"max={s['max']:7.1f} ms  (n={s['n']})")
        return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Motor principal
# ─────────────────────────────────────────────────────────────────────────────

class SecurityEngine:
    """
    Motor de visión por computador. Se instancia uno por cámara y se reutiliza;
    varios motores pueden correr a la vez (cada uno con sus modelos y su BD).

    Callbacks registrables (todos opcionales):
      on_frame(frame_bgr)             → frame procesado listo para mostrar
      on_face_event(event_dict)       → rostro detectado/reconocido
      on_vehicle_event(event_dict)    → placa detectada
      on_stats(stats_dict)            → métricas en tiempo real
    """

    # dos motores arrancando a la vez no deben cargar modelos en paralelo
    _load_lock = threading.Lock()

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._paused = False
        # una señal por cada inicio: un hilo que siguió colgado abriendo la cámara
        # no debe revivir porque la cámara se volvió a iniciar
        self._stop_evt = threading.Event()

        # callbacks
        self._cb_frame: Optional[Callable] = None
        self._cb_face: Optional[Callable] = None
        self._cb_vehicle: Optional[Callable] = None
        self._cb_stats: Optional[Callable] = None

        # BD y datos en memoria
        self.db: Optional[DatabaseManager] = None
        self._db_lock = threading.Lock()  # una conexión SQLite compartida por 3 hilos
        self.known_faces: list = []
        self.resident_plates: dict = {}   # patente -> {idvehiculo, unidad}
        self.visit_plates: dict = {}      # patente -> {idvisita, unidad}
        self._idcamara: Optional[int] = None
        self._last_reload = 0.0
        self._data_version = -1    # último events.data_version() aplicado
        self._models_version = -1  # último events.models_version() aplicado

        # modelos (lazy init en _load_models)
        self._person_detector: Optional[OnnxDetector] = None
        self._vehicle_detector: Optional[OnnxDetector] = None
        self._plate_detector: Optional[OnnxDetector] = None
        self._models_loaded = False

        # tracking state
        self._person_memory: dict = {}
        self._next_pid = [0]
        self._active_vehicles: dict = {}
        self._vehicle_data: dict = {}
        self._vehicle_class: dict = {}   # cid -> clase COCO (3 = moto)
        self._zoom_face: Optional[np.ndarray] = None
        self._zoom_name: str = ""
        self._frame_count = 0
        self._start_time = 0.0

        # doble stream: canal principal de alta resolución (None = un solo canal)
        self._camera_source_hi: Optional[str] = None
        self._hires: Optional[HighResStream] = None
        self._plate_last_try: dict = {}  # cid -> fc del último intento (doble stream)

        # cola OCR asíncrono: (crop, cid, plate_box, fc, t_enq, vehicle_box, low_frame)
        # crop None => el hilo busca la patente en el canal de alta resolución
        self._ocr_queue: queue.Queue = queue.Queue(maxsize=4)
        self._ocr_thread: Optional[threading.Thread] = None
        self._pending_ocr: set = set()  # cids en proceso
        # lecturas OCR acumuladas por vehículo hasta confirmar (ver _vote_plate)
        self._plate_votes: dict = {}
        self._plate_lock = threading.Lock()

        # cola reconocimiento facial asíncrono: (pid, fc, t_enq, person_box, low_frame)
        # el hilo busca el rostro en la región de la persona (canal alto si existe)
        self._face_queue: queue.Queue = queue.Queue(maxsize=2)
        self._face_thread: Optional[threading.Thread] = None
        self._pending_faces: set = set()  # pids en proceso

        # latencias por etapa (ms)
        self._latency = LatencyMeter()
        self._last_latency_report = 0.0
        self._last_latency_stats = 0.0

        self._stats = {
            "faces_registered": 0,
            "faces_visit": 0,
            "faces_unknown": 0,
            "plates_registered": 0,
            "plates_visit": 0,
            "plates_unregistered": 0,
            "fps": 0.0,
            "db_connected": False,
            "latency_frame_ms": 0.0,      # promedio por frame (lectura excluida)
            "latency_detect_ms": 0.0,     # promedio frames con detección YOLO
            "latency_detect_p95": 0.0,
        }

    # ── callbacks ─────────────────────────────────────────────────────────

    def set_callbacks(
        self,
        on_frame: Callable = None,
        on_face: Callable = None,
        on_vehicle: Callable = None,
        on_stats: Callable = None,
    ):
        self._cb_frame = on_frame
        self._cb_face = on_face
        self._cb_vehicle = on_vehicle
        self._cb_stats = on_stats

    # ── ciclo de vida ─────────────────────────────────────────────────────

    def start(self, cam):
        """cam: CameraConfig de la cámara a monitorear."""
        if self._running:
            return
        self._camera_source = cam.source
        self._camera_source_hi = getattr(cam, "source_hi", None) or None
        self._idcamara = int(cam.id)
        self._running = True
        self._paused = False
        self._stop_evt = threading.Event()
        self._thread = threading.Thread(target=self._loop, args=(self._stop_evt,), daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._stop_evt.set()
        # esperar también a los hilos OCR/rostros para que un start() inmediato
        # no deje dos workers usando el mismo modelo
        for t in (self._thread, self._ocr_thread, self._face_thread):
            if t:
                t.join(timeout=STOP_JOIN_S)
        self._thread = self._ocr_thread = self._face_thread = None

    def toggle_pause(self):
        self._paused = not self._paused

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    # ── inicialización lazy ───────────────────────────────────────────────

    def _connect_db(self) -> bool:
        self.db = DatabaseManager()
        ok = self.db.connect()
        self._stats["db_connected"] = ok
        if not ok:
            print("[Engine] ADVERTENCIA: sin conexión a BD")
        return ok

    def _load_models(self):
        if self._models_loaded and self._models_version == events.models_version():
            return
        with SecurityEngine._load_lock:
            self._models_version = events.models_version()
            print(f"[Engine] Cargando modelos ONNX en {get_device_info()['name']}...")
            # personas y vehículos usan el mismo modelo: se carga una sola vez.
            # Se asignan al final: el hilo OCR sigue usando los anteriores mientras cargan
            person = OnnxDetector(config.DETECTOR_MODEL)
            plate = OnnxDetector(config.PLATE_DETECTOR_MODEL)
            for det in (person, plate):
                print(f"[Engine] Modelo {det.name} en {det.provider}")
            self._person_detector = self._vehicle_detector = person
            self._plate_detector = plate
            self._models_loaded = True
            print("[Engine] Modelos listos")

    def _load_data(self):
        """Plantillas faciales y patentes autorizadas. Se recarga periódicamente
        para incorporar residentes, revocaciones, bloqueos y visitas nuevas."""
        if not self.db:
            return
        self._data_version = events.data_version()
        with self._db_lock:
            try:
                self.known_faces = load_known_faces(self.db)
                self.resident_plates, self.visit_plates = load_registered_plates(self.db)
            except Exception as e:
                print(f"[Engine] Error recargando datos: {e}")
        self._last_reload = time.time()

    # ── loop principal ────────────────────────────────────────────────────

    def _loop(self, stop: threading.Event):
        self._connect_db()
        self._load_models()
        self._load_data()

        mot_tracker = IoUTracker()

        # hilo OCR separado para no bloquear el loop de video
        self._ocr_thread = threading.Thread(target=self._ocr_worker, args=(stop,), daemon=True)
        self._ocr_thread.start()

        # hilo de reconocimiento facial (YuNet + SFace con OpenCV, en CPU)
        self._face_thread = threading.Thread(target=self._face_worker, args=(stop,), daemon=True)
        self._face_thread.start()

        # cámaras IP: lector en hilo propio que descarta frames atrasados
        live = is_network_source(self._camera_source)
        if live:
            cap = LiveStream(self._camera_source)
            opened = cap.start()
        else:
            cap = cv2.VideoCapture(self._camera_source)
            opened = cap.isOpened()
        if stop.is_set():      # se detuvo mientras la cámara tardaba en abrir
            if opened:
                cap.release()
            return
        if not opened:
            print(f"[Engine] Error: no se pudo abrir la fuente {_fuente_segura(self._camera_source)}")
            self._running = False
            stop.set()
            return

        if live:
            width, height = cap.size
        else:
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._frame_count = 0
        self._start_time = time.time()
        self._person_memory.clear()
        self._next_pid = [0]
        self._active_vehicles.clear()
        self._vehicle_data.clear()
        self._vehicle_class.clear()
        self._latency.clear()
        self._last_latency_report = time.time()
        self._plate_last_try.clear()
        self._plate_votes.clear()

        hires = None
        if self._camera_source_hi:
            hires = self._hires = HighResStream(self._camera_source_hi)
            hires.start()
            print(f"[Engine] Doble stream: detección en {width}x{height}, "
                  f"recortes desde el canal de alta resolución")

        print(f"[Engine] Iniciado — fuente={_fuente_segura(self._camera_source)} {width}x{height}")

        while not stop.is_set():
            if self._paused:
                time.sleep(0.05)
                continue

            t_read = time.perf_counter()
            ret, frame = cap.read()
            t_frame = time.perf_counter()
            self._latency.add("lectura_cam", (t_frame - t_read) * 1000)
            if not ret:
                if live:  # LiveStream reconecta por su cuenta
                    continue
                time.sleep(1)
                cap = cv2.VideoCapture(self._camera_source)
                continue

            self._frame_count += 1
            fc = self._frame_count

            # cambios hechos desde la GUI: se aplican al instante, sin reiniciar
            if (time.time() - self._last_reload > RELOAD_EVERY_S
                    or self._data_version != events.data_version()):
                self._load_data()
            if self._models_version != events.models_version():
                try:
                    self._load_models()
                except Exception as e:
                    print(f"[Engine] No se pudieron cargar los modelos nuevos; "
                          f"se siguen usando los anteriores: {e}")

            clean_old_persons(fc, self._person_memory)
            cleanup_old_vehicles(fc, self._active_vehicles, self._vehicle_data)
            if self._plate_votes:
                self._flush_plate_votes()

            if fc % config.PROCESS_EVERY_N_FRAMES == 0:
                t0 = time.perf_counter()
                self._process_frame(frame, width, height, mot_tracker, fc)
                self._latency.add("deteccion", _ms_since(t0))

            # dibujar resultados sobre el frame original
            t0 = time.perf_counter()
            # solo quien se detectó en las dos últimas pasadas de detección
            draw_persons(frame, self._person_memory, fc, 2 * config.PROCESS_EVERY_N_FRAMES)
            draw_vehicles(frame, self._active_vehicles, self._vehicle_data)
            if self._zoom_face is not None and config.SHOW_FACE_ZOOM:
                overlay_face_zoom(frame, self._zoom_face, self._zoom_name,
                                  size=min(config.ZOOM_SIZE, frame.shape[0] // 3))

            if config.SHOW_VIDEO_HUD:
                self._draw_hud(frame, fc)
            elif self._paused:
                self._draw_paused(frame)
            self._latency.add("dibujo", _ms_since(t0))

            if self._cb_frame:
                self._cb_frame(frame.copy())

            # latencia desde que llega el frame hasta que se entrega a la GUI
            self._latency.add("frame_total", _ms_since(t_frame))
            self._update_latency_stats()

            elapsed = time.time() - self._start_time
            self._stats["fps"] = round(fc / elapsed, 1) if elapsed > 0 else 0.0
            # lo que antes solo se veía en el HUD sobre el video
            self._stats["gpu"] = get_device_info()["use_gpu"]
            self._stats["hires_ok"] = None if self._hires is None else self._hires.connected
            if self._cb_stats:
                self._cb_stats(dict(self._stats))

        cap.release()
        if hires:
            hires.stop()
        if self._hires is hires:
            self._hires = None
        if self.db and self._stop_evt is stop:   # si ya hay otro inicio, la base es suya
            self.db.disconnect()
        print(f"[Latencia] Resumen final (últimas muestras):\n{self._latency.report()}")
        print("[Engine] Detenido")

    def _update_latency_stats(self):
        now = time.time()
        if now - self._last_latency_stats >= 1.0:
            self._last_latency_stats = now
            frame = self._latency.summary("frame_total")
            det = self._latency.summary("deteccion")
            if frame:
                self._stats["latency_frame_ms"] = round(frame["avg"], 1)
            if det:
                self._stats["latency_detect_ms"] = round(det["avg"], 1)
                self._stats["latency_detect_p95"] = round(det["p95"], 1)
        if now - self._last_latency_report >= LATENCY_REPORT_EVERY_S:
            self._last_latency_report = now
            print(f"[Latencia] ventana móvil (ms):\n{self._latency.report()}")

    # ── procesamiento por frame ───────────────────────────────────────────

    def _process_frame(self, frame, width, height, mot_tracker, fc):
        dual = self._hires is not None
        # el substream ya viene en baja resolución: no se reescala
        scale = 1.0 if dual else config.SCALE_FACTOR
        small = frame if scale == 1.0 else cv2.resize(
            frame, (int(width * scale), int(height * scale)))

        # copia del frame bajo (antes de dibujar encima) para los hilos de rostro/OCR
        # cuando el canal alto no responde; se hace solo si hay algo que encolar
        low_copy = [None]

        def low():
            if low_copy[0] is None:
                low_copy[0] = frame.copy()
            return low_copy[0]

        if dual:
            # mismo modelo y mismo frame: una sola inferencia para personas y vehículos
            t0 = time.perf_counter()
            classes = [0] + [c for c in config.VEHICLES_CLASS if c != 0]
            rows = self._person_detector.detect(frame, classes=classes)
            self._latency.add("yolo_unificado", _ms_since(t0))
            person_rows = [d for d in rows if int(d[5]) == 0]
            veh_rows = [d for d in rows if int(d[5]) in config.VEHICLES_CLASS]
        else:
            t0 = time.perf_counter()
            person_rows = self._person_detector.detect(small, classes=[0])
            self._latency.add("yolo_personas", _ms_since(t0))

        # ---- personas ----
        bboxes = [
            (int(x1 / scale), int(y1 / scale), int(x2 / scale), int(y2 / scale))
            for x1, y1, x2, y2, score, _ in person_rows if score >= config.PERSON_CONFIDENCE
        ]
        # asignación uno a uno: dos personas juntas no intercambian identidad
        pids = assign_person_ids(bboxes, self._person_memory, self._next_pid,
                                 current_frame=fc)
        # personas superpuestas: el recorte de una contiene la cara de la otra
        superpuestas = {
            pids[i] for i in range(len(bboxes)) for j in range(len(bboxes))
            if i != j and _iou(bboxes[i], bboxes[j]) >= config.PERSON_OVERLAP_IOU
        }
        for bbox, pid in zip(bboxes, pids):
            if pid not in self._person_memory:
                self._person_memory[pid] = {
                    "bbox": bbox, "last_seen": fc, "name": None,
                    "id": None, "idresidente": None, "is_registered": False,
                    "color": (150, 150, 150), "display_name": "Analizando...",
                    # votación entre intentos (ver _do_recognition)
                    "attempts": 0, "votes": {}, "candidates": {},
                }
            else:
                p = self._person_memory[pid]
                # velocidad (px por cuadro) para mover el recuadro entre detecciones
                dt = fc - p["last_seen"]
                if 0 < dt <= 2 * config.PROCESS_EVERY_N_FRAMES:
                    p["vel"] = tuple((n - o) / dt for n, o in zip(bbox, p["bbox"]))
                else:
                    p["vel"] = None
                p["bbox"] = bbox
                p["last_seen"] = fc

            # mientras no haya decisión, se reintenta en cada detección; el hilo de
            # rostros busca la cara dentro de la región de la persona (en el canal
            # alto si existe). Un solo intento en curso por persona. Quien quedó como
            # NO RECONOCIDO se revisa de nuevo cada FACE_RECHECK_S (pudo entrar de
            # perfil), y quien ya fue reconocido se verifica cada FACE_REVERIFY_S
            # (otra persona pudo ocupar su lugar).
            p = self._person_memory[pid]
            if pid in superpuestas:
                # mientras se cruzan no se reconoce (la cara más grande del recorte
                # puede ser la del otro) y la identidad queda en duda: apenas se
                # separan se verifica de inmediato
                p["cruce"] = True
                continue
            if p.pop("cruce", False) and p["is_registered"]:
                p["recheck_at"] = 0
                p["post_cruce"] = True
            pendiente = p["name"] is None or time.time() >= p.get("recheck_at", 0)
            if pendiente and pid not in self._pending_faces:
                try:
                    self._face_queue.put_nowait(
                        (pid, fc, time.perf_counter(), bbox, low()))
                    self._pending_faces.add(pid)
                except queue.Full:
                    pass

        # ---- vehículos + placas ----
        if not dual:
            t0 = time.perf_counter()
            veh_rows = self._vehicle_detector.detect(frame, classes=config.VEHICLES_CLASS)
            self._latency.add("yolo_vehiculos", _ms_since(t0))
        detections_, det_classes = [], []
        for det in veh_rows:
            x1, y1, x2, y2, score, cls = det
            if score >= config.VEHICLE_CONFIDENCE:
                detections_.append([x1, y1, x2, y2, score])
                det_classes.append(int(cls))

        t0 = time.perf_counter()
        if detections_:
            track_ids = mot_tracker.update(np.array(detections_))
        else:
            track_ids = np.empty((0, 5))
        self._latency.add("sort_tracking", _ms_since(t0))
        self._remember_vehicle_class(track_ids, detections_, det_classes)

        if dual:
            self._enqueue_hires_plates(track_ids, fc, low, width)
            self._update_active_vehicles(track_ids, fc)
            return

        t0 = time.perf_counter()
        plate_rows = self._plate_detector.detect(frame)
        self._latency.add("yolo_patentes", _ms_since(t0))
        for lp in plate_rows:
            x1, y1, x2, y2, score, _ = lp
            if score < config.PLATE_CONFIDENCE:
                continue
            cx1, cy1, cx2, cy2, cid = get_car(lp, track_ids)
            cid = int(cid)
            if cid == -1:
                continue
            # saltar si ya tenemos placa para este vehículo o está en proceso
            if cid in self._vehicle_data and self._vehicle_data[cid].get("plate"):
                continue
            if cid in self._pending_ocr:
                continue
            crop = frame[int(y1):int(y2), int(x1):int(x2)]
            if crop.shape[0] < 20:
                continue
            # enviar a hilo OCR sin bloquear
            try:
                self._ocr_queue.put_nowait(
                    (crop.copy(), cid, (x1, y1, x2, y2), fc, time.perf_counter(), None, None))
                self._pending_ocr.add(cid)
            except queue.Full:
                pass

        self._update_active_vehicles(track_ids, fc)

    def _remember_vehicle_class(self, track_ids, detections, classes):
        """Clase COCO de cada vehículo seguido (3 = moto). El tracker informa la caja
        de la detección tal cual, así que se asocian por coincidencia exacta."""
        for row in track_ids:
            for det, cls in zip(detections, classes):
                if np.allclose(det[:4], row[:4], atol=1.0):
                    self._vehicle_class[int(row[4])] = cls
                    break
        if len(self._vehicle_class) > 500:   # vehículos que ya salieron
            self._vehicle_class = {cid: c for cid, c in self._vehicle_class.items()
                                   if cid in self._active_vehicles}

    def _update_active_vehicles(self, track_ids, fc):
        for row in track_ids:
            cx1, cy1, cx2, cy2, cid = row
            cid = int(cid)
            self._active_vehicles[cid] = {
                "bbox": (int(cx1), int(cy1), int(cx2), int(cy2)),
                "last_frame": fc,
            }

    # ── doble stream: recortes desde el canal de alta resolución ──────────

    def _enqueue_hires_plates(self, track_ids, fc, low, frame_width=None):
        """Encola un vehículo sin patente para que el hilo OCR busque la placa en el canal
        alto. La GPU se usa de a una tarea: autos estacionados o lejanos, buscados sin
        parar, retrasaban la detección de las dos cámaras. Por eso hay una búsqueda a la
        vez por cámara, se ignoran los vehículos muy pequeños y se atiende primero al que
        lleva más tiempo sin intentarse (el recién llegado va antes que todos)."""
        for cid in list(self._plate_last_try):
            if cid not in self._active_vehicles:
                del self._plate_last_try[cid]
        if self._pending_ocr:
            return

        ancho_min = (frame_width or 0) * config.PLATE_MIN_VEHICLE_WIDTH
        candidatos = []
        for row in track_ids:
            cx1, cy1, cx2, cy2, cid = row
            cid = int(cid)
            if cid in self._vehicle_data and self._vehicle_data[cid].get("plate"):
                continue
            if cx2 - cx1 < ancho_min:
                continue
            ultimo = self._plate_last_try.get(cid, -10**9)
            if fc - ultimo < config.PLATE_RETRY_FRAMES:
                continue
            candidatos.append((ultimo, -(cx2 - cx1) * (cy2 - cy1), cid, (cx1, cy1, cx2, cy2)))
        if not candidatos:
            return
        _, _, cid, caja = min(candidatos, key=lambda c: c[:2])
        try:
            self._ocr_queue.put_nowait((None, cid, None, fc, time.perf_counter(), caja, low()))
            self._pending_ocr.add(cid)
            self._plate_last_try[cid] = fc
        except queue.Full:
            pass

    def _crop_source(self, low_frame):
        """(imagen, sx, sy): frame de alta resolución y su escala respecto al de
        detección; si el canal alto no está disponible, el propio frame bajo."""
        t0 = time.perf_counter()
        hi = self._hires.get_frame() if self._hires else None
        self._latency.add("alta_res_frame", _ms_since(t0))
        if hi is None:
            return low_frame, 1.0, 1.0
        lh, lw = low_frame.shape[:2]
        return hi, hi.shape[1] / lw, hi.shape[0] / lh

    def _person_region(self, person_box, low_frame) -> Optional[np.ndarray]:
        """Región de la persona donde buscar el rostro (canal alto si está disponible)."""
        src, sx, sy = self._crop_source(low_frame)
        h, w = src.shape[:2]
        x1, y1, x2, y2 = _scale_box(person_box, sx, sy, config.HIRES_PAD_PERSON, w, h)
        region = src[y1:y2, x1:x2]
        return region.copy() if region.size else None

    def _hires_plate(self, vehicle_box, low_frame):
        """Detecta la patente dentro del vehículo en el canal alto.
        Retorna (recorte, bbox de la placa en coordenadas del frame bajo) o None."""
        src, sx, sy = self._crop_source(low_frame)
        h, w = src.shape[:2]
        vx1, vy1, vx2, vy2 = _scale_box(vehicle_box, sx, sy, config.HIRES_PAD_VEHICLE, w, h)
        region = src[vy1:vy2, vx1:vx2]
        if region.size == 0:
            return None

        t0 = time.perf_counter()
        plates = [p for p in self._plate_detector.detect(region) if p[4] >= config.PLATE_CONFIDENCE]
        self._latency.add("yolo_patentes", _ms_since(t0))
        if not plates:
            return None
        px1, py1, px2, py2 = max(plates, key=lambda p: p[4])[:4]
        px1, px2 = int(px1) + vx1, int(px2) + vx1
        py1, py2 = int(py1) + vy1, int(py2) + vy1
        crop = src[py1:py2, px1:px2]
        if crop.shape[0] < 20:
            return None
        return crop.copy(), (px1 / sx, py1 / sy, px2 / sx, py2 / sy)

    def _ocr_worker(self, stop: threading.Event):
        """Hilo dedicado al OCR de patentes — no bloquea el loop de video."""
        while not stop.is_set():
            try:
                crop, cid, plate_box, fc, t_enq, vehicle_box, low_frame = \
                    self._ocr_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if crop is None:  # doble stream: buscar la placa en el canal alto
                    found = self._hires_plate(vehicle_box, low_frame)
                    if found is None:
                        continue
                    crop, plate_box = found
                x1, y1, x2, y2 = plate_box
                t0 = time.perf_counter()
                # los formatos de 5 caracteres solo valen si el vehículo es una moto
                es_moto = self._vehicle_class.get(cid) == MOTO_CLASS
                plate_text, plate_score = read_license_plate(crop, moto=es_moto)
                ms = _ms_since(t0)
                self._latency.add("ocr", ms)
                # espera en cola + OCR: retardo real hasta conocer la patente
                self._latency.add("ocr_total", _ms_since(t_enq))
                if plate_text:
                    print(f"[Engine] PLACA OCR: '{plate_text}' | conf={plate_score:.2%} | tiempo={ms:.1f}ms")
                    self._vote_plate(plate_text, plate_score, cid, (x1, y1, x2, y2), fc)
                else:
                    # placa encontrada pero ilegible o fuera de formato chileno
                    print(f"[Engine] Patente vehículo {cid} ilegible "
                          f"(recorte {crop.shape[1]}x{crop.shape[0]} px) | tiempo={ms:.1f}ms")
            except Exception as e:
                print(f"[Engine] Error OCR de patente: {e}")
            finally:
                self._pending_ocr.discard(cid)
                self._ocr_queue.task_done()

    def _face_worker(self, stop: threading.Event):
        """Hilo dedicado al reconocimiento facial — no bloquea el loop de video."""
        while not stop.is_set():
            try:
                pid, fc, t_enq, person_box, low_frame = self._face_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                region = self._person_region(person_box, low_frame)
                if region is None:
                    continue
                self._do_recognition(region, pid, fc)
                # espera en cola + reconocimiento: retardo real hasta identificar
                self._latency.add("rostro_total", _ms_since(t_enq))
            except Exception as e:
                print(f"[Engine] Error reconocimiento facial: {e}")
            finally:
                self._pending_faces.discard(pid)
                self._face_queue.task_done()

    def _do_recognition(self, region, pid, fc):
        """Un intento de reconocimiento. La decisión se toma por votación: un residente
        se confirma con FACE_VOTES_REQUIRED coincidencias y clara mayoría; tras
        FACE_MAX_ATTEMPTS rostros válidos sin confirmar, la persona es NO RECONOCIDO.
        Los rostros sin calidad suficiente no cuentan como intento."""
        t0 = time.perf_counter()
        res = recognize_face(region, self.known_faces)
        ms = _ms_since(t0)
        self._latency.add("rostro", ms)

        # la persona pudo salir de cuadro mientras se procesaba
        person = self._person_memory.get(pid)
        if person is None:
            return
        if person["is_registered"]:
            self._reverify(person, pid, res)
            return
        revision = person["name"] is not None   # ya decidido NO RECONOCIDO: se re-evalúa
        if revision:
            person["recheck_at"] = time.time() + config.FACE_RECHECK_S
            if res["status"] != "match":
                return   # sigue igual; no se vuelve a registrar el evento
        if res["status"] == "no_face":
            return
        if res["status"] == "low_quality":
            print(f"[Engine] Rostro descartado ({pid}): {res['reason']}")
            # el motivo queda a la vista: sin él la persona parece "atascada"
            person["display_name"] = f"Analizando: {res['reason'].split(' (')[0]}"
            return

        person["attempts"] += 1
        if res["status"] == "match":
            # ('r', idresidente) o ('v', idautorizacion): residentes y visitas no se mezclan
            rid = res.get("clave") or ("r", res["idresidente"])
            person["votes"][rid] = person["votes"].get(rid, 0) + 1
            prev = person["candidates"].get(rid)
            if prev is None or res["confidence"] > prev["confidence"]:
                person["candidates"][rid] = res
        dist = f"{res['distance']:.3f}" if res.get("distance") is not None else "-"
        print(f"[Engine] Intento rostro {pid} #{person['attempts']}: {res['status']} "
              f"(dist={dist}) | {ms:.0f}ms")

        name = unidad = idresidente = best = None
        conf = 0.0
        if person["votes"]:
            rid, n = max(person["votes"].items(), key=lambda kv: kv[1])
            others = sum(person["votes"].values()) - n
            # mayoría clara: el residente gana al resto de coincidencias 2 a 1
            if n >= config.FACE_VOTES_REQUIRED and n >= 2 * others:
                best = person["candidates"][rid]
                name, unidad, conf, idresidente = (
                    best["name"], best["unidad"], best["confidence"], best["idresidente"])
        if name is None and revision:
            return   # coincidencia aislada: no basta para cambiar la decisión
        if name is None and person["attempts"] < config.FACE_MAX_ATTEMPTS:
            person["display_name"] = (
                f"Analizando... {person['attempts']}/{config.FACE_MAX_ATTEMPTS}")
            return

        face_img = res["face"]
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if name and best.get("tipo") == "visita":
            # visita autorizada para hoy (ocasional) o frecuente
            self._stats["faces_visit"] = self._stats.get("faces_visit", 0) + 1
            person.update({
                "name": name, "id": unidad, "idresidente": None,
                "is_registered": True, "color": (255, 200, 0),
                "display_name": f"VISITA: {name} ({unidad})",
                "clave": rid, "contra": 0,
                "recheck_at": time.time() + config.FACE_REVERIFY_S,
            })
            print(f"[Engine] VISITA: {name} -> {unidad} | conf={conf:.2%} | tiempo={ms:.1f}ms")
            self._log_face("visita", conf, None, best.get("idautorizacion"))
            if self._cb_face:
                self._cb_face({
                    "type": "visit", "name": name, "unidad": unidad,
                    "confidence": conf, "timestamp": ts,
                })
        elif name:
            self._stats["faces_registered"] += 1
            person.update({
                "name": name, "id": unidad, "idresidente": idresidente,
                "is_registered": True, "color": (0, 255, 0),
                "display_name": f"{name} ({unidad})",
                "clave": rid, "contra": 0,
                "recheck_at": time.time() + config.FACE_REVERIFY_S,
            })
            print(f"[Engine] RESIDENTE: {name} | conf={conf:.2%} | tiempo={ms:.1f}ms")
            self._log_face("reconocido", conf, idresidente)
            if self._cb_face:
                self._cb_face({
                    "type": "registered", "name": name, "unidad": unidad,
                    "confidence": conf, "timestamp": ts,
                })
        else:
            # no se guarda ningún dato biométrico de personas no registradas (RNF-09)
            self._stats["faces_unknown"] += 1
            print(f"[Engine] NO RECONOCIDO | tiempo={ms:.1f}ms")
            person.update({
                "name": "No reconocido", "id": None, "idresidente": None,
                "is_registered": False, "color": (0, 165, 255),
                "display_name": "NO RECONOCIDO",
                "recheck_at": time.time() + config.FACE_RECHECK_S,
            })
            self._log_face("no_reconocido", None, None)
            if self._cb_face:
                self._cb_face({
                    "type": "unknown", "name": "No reconocido",
                    "confidence": 0.0, "timestamp": ts,
                })

        self._zoom_face = face_img.copy()
        self._zoom_name = person["display_name"]

    def _reverify(self, person, pid, res):
        """Verificación periódica de alguien ya reconocido. Si varios rostros válidos
        seguidos no son esa persona (otra ocupó su lugar en el cuadro), la identidad
        se descarta y el recuadro vuelve a «Analizando...» con votación desde cero."""
        post_cruce = person.get("post_cruce", False)
        if res["status"] not in ("match", "no_match"):
            # sin rostro o de mala calidad: no confirma ni contradice. Tras un cruce
            # se reintenta en la próxima detección en vez de esperar FACE_REVERIFY_S
            person["recheck_at"] = 0 if post_cruce else time.time() + config.FACE_REVERIFY_S
            return
        person["recheck_at"] = time.time() + config.FACE_REVERIFY_S
        person.pop("post_cruce", None)
        if res["status"] == "match" and res.get("clave") == person.get("clave"):
            person["contra"] = 0
            return
        person["contra"] = person.get("contra", 0) + 1
        # justo después de cruzarse con alguien, un solo rostro distinto basta
        limite = 1 if post_cruce else config.FACE_REVERIFY_CONTRA
        print(f"[Engine] Verificación {pid}: el rostro no corresponde a "
              f"{person['name']} ({person['contra']}/{limite})")
        if person["contra"] >= limite:
            print(f"[Engine] {pid}: otra persona en el lugar de {person['name']}; "
                  f"se vuelve a analizar")
            person.update({
                "name": None, "id": None, "idresidente": None, "is_registered": False,
                "color": (150, 150, 150), "display_name": "Analizando...",
                "attempts": 0, "votes": {}, "candidates": {},
                "clave": None, "contra": 0, "recheck_at": 0,
            })

    def _log_face(self, resultado, confianza, idresidente, idautorizacion=None):
        if self.db and config.USE_DATABASE_LOGS:
            with self._db_lock:
                try:
                    self.db.add_deteccion_rostro(self._idcamara, resultado, confianza, idresidente,
                                                 idautorizacion)
                except Exception as e:
                    print(f"[Engine] Error guardando detección de rostro: {e}")

    def _vote_plate(self, plate_text, plate_score, cid, box, fc):
        """Acumula lecturas OCR de un vehículo. Se confirma la patente cuando
        PLATE_VOTES_REQUIRED lecturas coinciden y son mayoría; si se llega a
        PLATE_MAX_READS sin consenso, se informa la más votada SIN CONFIRMAR."""
        with self._plate_lock:
            v = self._plate_votes.setdefault(cid, {"counts": {}, "score": {}, "box": box})
            v["counts"][plate_text] = v["counts"].get(plate_text, 0) + 1
            v["score"][plate_text] = max(v["score"].get(plate_text, 0.0), plate_score)
            v["box"] = box
            top, n = max(v["counts"].items(), key=lambda kv: kv[1])
            total = sum(v["counts"].values())
            confirmed = n >= config.PLATE_VOTES_REQUIRED and n > total - n
            if not confirmed and total < config.PLATE_MAX_READS:
                print(f"[Engine] Lectura patente vehículo {cid}: {plate_text} "
                      f"({n}/{config.PLATE_VOTES_REQUIRED} para confirmar)")
                return
            del self._plate_votes[cid]
        self._handle_plate(top, v["score"][top], cid, *box, fc, confirmed=confirmed)

    def _flush_plate_votes(self):
        """Vehículos que salieron de cuadro con lecturas pero sin consenso: se informa
        la lectura más votada como SIN CONFIRMAR para que quede registro."""
        with self._plate_lock:
            gone = {cid: v for cid, v in self._plate_votes.items()
                    if cid not in self._active_vehicles}
            for cid in gone:
                del self._plate_votes[cid]
        for cid, v in gone.items():
            top = max(v["counts"].items(), key=lambda kv: kv[1])[0]
            self._handle_plate(top, v["score"][top], cid, *v["box"], self._frame_count,
                               confirmed=False)
            self._vehicle_data.pop(cid, None)  # el vehículo ya no está en pantalla

    def _handle_plate(self, plate_text, plate_score, cid, x1, y1, x2, y2, fc, confirmed=True):
        key = clean_plate(plate_text)
        # una lectura sin confirmar nunca se trata como autorizada
        resident = self.resident_plates.get(key) if confirmed else None
        visit = None if resident or not confirmed else self.visit_plates.get(key)
        if not confirmed:
            status, label = "no_registrado", f"{plate_text}? - SIN CONFIRMAR"
            self._stats["plates_unregistered"] += 1
        elif resident:
            status, label = "residente", f"{plate_text} - {resident['unidad']}"
            self._stats["plates_registered"] += 1
        elif visit:
            status, label = "visita", f"{plate_text} - VISITA {visit['unidad']}"
            self._stats["plates_visit"] += 1
        else:
            status, label = "no_registrado", f"{plate_text} - NO REGISTRADO"
            self._stats["plates_unregistered"] += 1
        print(f"[Engine] PATENTE {plate_text}: {status}"
              + ("" if confirmed else " (sin confirmar)"))

        self._vehicle_data[cid] = {
            "plate": plate_text,
            "status": status,
            "label": label,
            "is_registered": status != "no_registrado",
            "plate_bbox": (int(x1), int(y1), int(x2), int(y2)),
        }
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if self.db and config.USE_DATABASE_LOGS:
            with self._db_lock:
                try:
                    self.db.add_deteccion_vehiculo(
                        self._idcamara, plate_text, status, plate_score,
                        resident["idvehiculo"] if resident else None,
                        visit["idvisita"] if visit else None)
                except Exception as e:
                    print(f"[Engine] Error guardando detección de vehículo: {e}")

        if self._cb_vehicle:
            self._cb_vehicle({
                "plate": plate_text, "status": status, "label": label,
                "is_registered": status != "no_registrado",
                "confidence": plate_score, "timestamp": ts,
            })

    def _draw_hud(self, frame, fc):
        elapsed = time.time() - self._start_time
        fps = round(fc / elapsed, 1) if elapsed > 0 else 0.0
        reg_f = sum(1 for p in self._person_memory.values() if p["is_registered"])
        unk_f = len(self._person_memory) - reg_f
        reg_v = sum(1 for v in self._vehicle_data.values() if v["is_registered"])
        int_v = len(self._vehicle_data) - reg_v

        lines = [
            f"Personas: {len(self._person_memory)}  (Residentes:{reg_f} Otros:{unk_f})",
            f"Vehiculos: {len(self._active_vehicles)}  (Autorizados:{reg_v} No reg.:{int_v})",
            "BD: OK" if self._stats["db_connected"] else "BD: DESCONECTADA",
            f"FPS: {fps}  |  {get_device_info()['name']}",
            f"Latencia: frame {self._stats['latency_frame_ms']} ms  |  "
            f"deteccion {self._stats['latency_detect_ms']} ms (p95 {self._stats['latency_detect_p95']})",
        ]
        colors = [(0, 255, 255)] * 2 + [
            (0, 255, 0) if self._stats["db_connected"] else (0, 0, 255),
            (0, 255, 0) if get_device_info()["use_gpu"] else (0, 165, 255),
            (0, 255, 255),
        ]
        if self._hires is not None:
            ok = self._hires.connected
            lines.append("Canal alta res.: OK" if ok else "Canal alta res.: SIN SENAL (usando baja)")
            colors.append((0, 255, 0) if ok else (0, 0, 255))

        # el substream puede ser de 640x360: el HUD se escala con la altura del frame
        h, w = frame.shape[:2]
        s = min(1.0, h / 720)
        for i, (line, col) in enumerate(zip(lines, colors)):
            cv2.putText(frame, line, (int(20 * s), int((30 + i * 28) * s)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65 * s, col, max(1, round(2 * s)))
        if self._paused:
            self._draw_paused(frame)

    @staticmethod
    def _draw_paused(frame):
        h, w = frame.shape[:2]
        s = min(1.0, h / 720)
        cv2.putText(frame, "PAUSADO", (w - int(220 * s), int(40 * s)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0 * s, (0, 165, 255), max(1, round(3 * s)))
