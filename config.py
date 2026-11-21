"""
config.py - Configuraciones del nodo de Umbral Guardian (PC de la portería).

Arquitectura híbrida: este programa usa su BASE LOCAL (datos personales y
biométricos del condominio) y se comunica con la API CENTRAL de la nube solo
para iniciar sesión, verificar la suscripción y sincronizar cuentas.
Las credenciales de la base central NO están aquí: solo las conoce la API.
"""
import os
import sys
import json

# ==================== BASE DE DATOS LOCAL (nodo) ====================
# SQLite (biblioteca estándar de Python): un archivo, sin servidor que instalar.
# Fuera de la carpeta del programa, para que reinstalar o actualizar no la toque.
DB_PATH = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
                       "UmbralGuardian", "umbral_local.db")
DB_TIMEOUT_S = 10   # espera máxima si otro hilo tiene la base bloqueada para escribir

# ==================== NUBE ====================
API_URL = "http://127.0.0.1:5000"   # se sobrescribe con nodo.json
NODE_KEY = ""                       # clave del nodo, en nodo.json
API_TIMEOUT_S = 8
DIAS_SIN_CONEXION = 7               # operación máxima sin contactar la nube
SINCRONIZAR_CADA_H = 6              # re-sincronización periódica

# ==================== PATHS ====================
# sys.frozen es True cuando corre como ejecutable PyInstaller
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# pesos de los modelos, fuera del ejecutable: actualizar un modelo = reemplazar un archivo
MODELS_DIR = os.path.join(BASE_DIR, "modelos")
REPORTS_OUTPUT_DIR = os.path.join(BASE_DIR, "reports_output")
ROSTROS_REGISTRADOS_DIR = os.path.join(BASE_DIR, "rostros_registrados")
ROSTROS_DESCONOCIDOS_DIR = os.path.join(BASE_DIR, "rostros_desconocidos")
MIGRATIONS_DIR = os.path.join(BASE_DIR, "migraciones")   # NNN_descripcion.sql
CAMERAS_CONFIG_FILE = os.path.join(BASE_DIR, "cameras.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
NODE_FILE = os.path.join(BASE_DIR, "nodo.json")                       # api_url + clave_nodo
LICENSE_PUBLIC_KEY = os.path.join(BASE_DIR, "licencia_publica.pem")   # verifica licencias

# ==================== MODELOS (ONNX, onnxruntime) ====================
# Personas y vehículos: RF-DETR Nano (Apache 2.0, COCO). Medido en la GTX 1650 Ti:
# 30 ms por inferencia, igual que YOLO26s; Small tarda 54 ms y con dos cámaras
# compartiendo la GPU no cabría en los 100 ms del SLA-02.
DETECTOR_MODEL = os.path.join(MODELS_DIR, "rfdetr_nano.onnx")
# Patentes: el mismo YOLOv8n de siempre, solo exportado a ONNX (pesos sin cambios).
# Licencia pendiente: ver AVISOS.txt.
PLATE_DETECTOR_MODEL = os.path.join(MODELS_DIR, "license_plate_detector.onnx")
# Rostros: detector YuNet (MIT) + reconocimiento SFace (Apache 2.0), ambos del
# OpenCV Zoo, con cv2.FaceDetectorYN / cv2.FaceRecognizerSF. SFace entrega 128
# dimensiones (ArcFace entregaba 512). Las plantillas se guardan con el nombre del
# modelo y solo se comparan con las del modelo vigente: al cambiarlo hay que volver
# a enrolar a los residentes.
FACE_MODEL = "SFace"
FACE_DETECTOR_MODEL = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
FACE_RECOGNIZER_MODEL = os.path.join(MODELS_DIR, "face_recognition_sface_2021dec.onnx")

# ==================== CÁMARA DEFAULT ====================
USAR_DROIDCAM = False
DROIDCAM_URL = ""
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30

# ==================== DETECCIÓN ====================
# Calibrados para RF-DETR Nano (no se trasladan desde YOLO26s, que usaba 0.5 en
# ambos): el umbral más bajo que mantiene la precisión que YOLO26s tenía a 0.5,
# medido contra COCO128 anotado. Personas P=0.96 R=0.56 (YOLO26s: P=0.95 R=0.47);
# vehículos P=0.94 R=0.41 (YOLO26s: P=0.92 R=0.33). Confirmar con las cámaras del
# condominio: tools/calibrar_detector.py
PERSON_CONFIDENCE = 0.60
VEHICLE_CONFIDENCE = 0.45
PLATE_CONFIDENCE = 0.5   # detector de patentes sin cambios

# ==================== PROCESAMIENTO ====================
USE_GPU = True  # usa CUDA (NVIDIA) si está disponible; si no, CPU automáticamente
PROCESS_EVERY_N_FRAMES = 5
SCALE_FACTOR = 0.7  # solo con un canal; el substream ya viene en baja resolución

# ==================== DOBLE STREAM RTSP ====================
# Si la cámara tiene `fuente_alta`, se detecta en el substream y los rostros y
# patentes se recortan del canal principal. Margen extra del recorte (fracción
# del bbox) para cubrir el desfase de tiempo entre ambos canales.
HIRES_PAD_PERSON = 0.10
HIRES_PAD_VEHICLE = 0.15
PLATE_RETRY_FRAMES = 5  # frames entre intentos de buscar patente en un mismo vehículo
# ancho mínimo del vehículo (fracción del cuadro) para buscar su patente: más lejos no
# se alcanza a leer y solo ocupa la GPU. En el portón, un auto cercano ocupa 0,16 a 0,35
PLATE_MIN_VEHICLE_WIDTH = 0.12

# ==================== TRACKING ====================
PERSON_TIMEOUT = 30
VEHICLE_TIMEOUT = 40
PERSON_DISTANCE_THRESHOLD = 80  # px entre centros, si no hay superposición suficiente
PERSON_MIN_IOU = 0.3  # superposición mínima para considerar que es la misma persona
# dos personas cuyas cajas se superponen al menos esto se consideran "cruzándose":
# no se reconoce su rostro hasta que se separan, y entonces se verifica de inmediato
PERSON_OVERLAP_IOU = 0.2

# ==================== RECONOCIMIENTO FACIAL ====================
# Distancia coseno máxima para aceptar una coincidencia, y margen por el que el
# mejor residente debe superar al segundo. Calibrados para SFace (los de ArcFace
# eran 0.55 / 0.08 y no se trasladan): simulación sobre LFW con 150 residentes
# inscritos (2 fotos cada uno) y 300 personas no registradas.
#   ArcFace 0.55/0.08: por intento reconoce 85.8 %, acepta desconocidos 3.9 %;
#                      por persona (2 votos, 5 intentos) confirma 96/105, acepta 1/134.
#   SFace   0.60/0.09: por intento reconoce 98.8 %, acepta desconocidos 1.7 %;
#                      por persona confirma 104/105, acepta 0/134. Ninguna confusión
#                      entre residentes en ninguno de los dos.
# Se eligió 0.60/0.09 y no el óptimo nominal 0.62/0.07 porque ahí, con 0.02 menos de
# margen, los desconocidos aceptados suben a 6.3 %. Más bajo = más estricto.
# 08-11-2026: una persona no registrada parecida a un residente quedó a 0.54 de él y
# fue aceptada. Mismo LFW con el umbral más estricto (margen 0.09, 2 votos):
#   150 inscritos  0.60: reconoce 98.8 %, acepta desconocidos 1.72 % por intento
#                  0.55: 98.6 % / 0.47 %     0.50: 97.9 % / 0.00 %     0.45: 94.2 % / 0.00 %
#   3 inscritos    0.60: 98.8 % / 0.12 %     0.50: 98.0 % / 0.00 %
#   por persona, a 0.50: confirma 104/105 residentes (igual que a 0.60), 0 desconocidos.
# Se usa 0.50: casi no cuesta reconocimiento y deja fuera ese caso.
FACE_RECOGNITION_THRESHOLD = 0.50
FACE_MATCH_MARGIN = 0.09
MIN_FACE_SIZE = 60
# confianza mínima del detector de rostros (YuNet). Medido en Conserjería:
# rostros reales 0.91-0.94; falsos positivos (persona de espaldas) <= 0.64
FACE_MIN_DETECTION_CONF = 0.75
# varianza del Laplaciano; menos = rostro borroso. Rostros reales medidos: 160-1100
FACE_MIN_SHARPNESS = 40.0
# enrolamiento: capturas por residente y distancia coseno mínima entre ellas.
# Medido con ArcFace: 5 capturas sin moverse quedan a 0.008-0.039; con cambios de
# pose, sobre 0.06. Revisado para SFace con 240 pares casi idénticos (desplazamiento,
# escala, brillo, ruido): ambos modelos tienen la misma escala aquí (mediana 0.032
# ArcFace / 0.030 SFace; bajo 0.05 queda el 79.6 % / 81.2 %), así que se mantiene.
MAX_CAPTURES = 5
MIN_CAPTURE_DIFF = 0.05
# votación entre intentos de una misma persona antes de decidir
FACE_VOTES_REQUIRED = 2   # coincidencias con el mismo residente para confirmarlo
FACE_MAX_ATTEMPTS = 5     # rostros válidos sin confirmar => NO RECONOCIDO
# una persona NO RECONOCIDA se re-evalúa cada N segundos mientras siga en cuadro:
# pudo entrar de perfil o en movimiento. Pasa a residente con la misma regla de votos.
FACE_RECHECK_S = 2.0
# una persona YA RECONOCIDA también se verifica cada N segundos: el seguimiento es
# por posición, y si otra persona ocupa su lugar (se sienta en la misma silla) el
# recuadro heredaría el nombre. Con FACE_REVERIFY_CONTRA rostros válidos seguidos
# que no son ella, la identidad se descarta y se vuelve a analizar desde cero.
FACE_REVERIFY_S = 3.0
FACE_REVERIFY_CONTRA = 2

# ==================== PATENTES ====================
PLATE_OCR_MODEL = "cct-s-v2-global-model"  # fast-plate-ocr
PLATE_MIN_CHAR_CONF = 0.85  # confianza mínima de CADA carácter leído
PLATE_VOTES_REQUIRED = 2  # lecturas idénticas para confirmar una patente
PLATE_MAX_READS = 6       # lecturas válidas sin consenso => se informa SIN CONFIRMAR

# ==================== CLASES VEHÍCULOS COCO ====================
VEHICLES_CLASS = [2, 3, 5, 7]

# ==================== DISPLAY ====================
# Vista tipo grabador: sobre el video solo van los recuadros de personas y
# vehículos con su nombre o patente. Los datos técnicos (FPS, latencia, BD, GPU)
# se muestran bajo el video; se pueden volver a dibujar encima (p. ej. para
# capturas de pruebas de latencia) activando SHOW_VIDEO_HUD.
SHOW_VIDEO_HUD = False
SHOW_FACE_ZOOM = False   # recuadro ampliado del último rostro, en la esquina
ZOOM_SIZE = 220
DISPLAY_WIDTH = 1280
DISPLAY_HEIGHT = 720

# ==================== VISITAS ====================
# Regla del condominio: las visitas registran su rostro (con consentimiento) para
# que la cámara las reconozca al llegar. Ocasionales: el vector se borra al día
# siguiente de la visita. Frecuentes: hasta que la administración lo revoque.
VISITA_ROSTRO_OBLIGATORIO = True

# ==================== PROTECCIÓN DE DATOS (Ley 21.719) ====================
VERSION_CONSENTIMIENTO = "v1.0"      # versión vigente del formulario de consentimiento
DIAS_RETENCION_DETECCIONES = 90      # historial de accesos (art. 3 c)
DIAS_RETENCION_VISITAS = 30          # datos de visitas

# ==================== LOGS ====================
USE_DATABASE_LOGS = True
USE_CSV_LOGS = False

# ==================== OVERRIDE DESDE settings.json Y nodo.json ====================
def _apply_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                overrides = json.load(f)
            g = globals()
            for key, val in overrides.items():
                if key in g:
                    g[key] = val
        except Exception as e:
            print(f"[CONFIG] Warning: no se pudo leer settings.json: {e}")

    # settings.json puede traer rutas relativas o absolutas de otra instalación:
    # en ese caso se busca el archivo con el mismo nombre en la carpeta del programa
    g = globals()
    for key in ("DETECTOR_MODEL", "PLATE_DETECTOR_MODEL",
                "FACE_DETECTOR_MODEL", "FACE_RECOGNIZER_MODEL"):
        path = g[key]
        # en Windows la misma carpeta puede venir como c:\ o C:\ según cómo se abrió
        en_modelos = os.path.normcase(os.path.dirname(os.path.abspath(path))) \
            == os.path.normcase(MODELS_DIR)
        if en_modelos or not os.path.isabs(path) or not os.path.exists(path):
            local = os.path.join(MODELS_DIR, os.path.basename(path))
            if os.path.exists(local):
                g[key] = local

    global API_URL, NODE_KEY
    if os.path.exists(NODE_FILE):
        try:
            with open(NODE_FILE, 'r', encoding='utf-8') as f:
                nodo = json.load(f)
            API_URL = nodo.get("api_url", API_URL)
            NODE_KEY = nodo.get("clave_nodo", NODE_KEY)
        except Exception as e:
            print(f"[CONFIG] Warning: no se pudo leer nodo.json: {e}")


# valores de este archivo, antes de aplicar settings.json
_DEFAULTS = {k: v for k, v in globals().items() if k.isupper()}


def reload():
    """Vuelve a los valores por defecto y aplica settings.json y nodo.json.
    Los módulos leen `config.X` en cada uso, así que el cambio rige de inmediato."""
    globals().update(_DEFAULTS)
    _apply_settings()


_apply_settings()
