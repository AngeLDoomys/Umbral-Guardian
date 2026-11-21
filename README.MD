# Umbral Guardian

Control de acceso para condominios con visión artificial. El sistema reconoce a residentes y visitas autorizadas por su rostro, y a los vehículos por su patente, y avisa al conserje en vivo. **La decisión de abrir el portón siempre es del conserje.**

Proyecto de título de Matías Tejada · INACAP · 2026.

## Cómo funciona

El sistema tiene dos partes:

| Parte | Dónde corre | Qué hace |
|---|---|---|
| **Nodo de borde** | PC de la portería (Windows, GPU NVIDIA) | Lee las cámaras del grabador por RTSP, reconoce personas y patentes, y guarda todo en una base local SQLite. Incluye la interfaz del conserje y del administrador (Tkinter). |
| **Plano de control** | Nube (AWS: EC2 + RDS MySQL) | API REST en Flask. Maneja condominios, planes, pagos, cuentas, la licencia firmada de cada nodo y el formulario de registro por QR. |

El video y el historial de accesos **nunca salen del condominio**. El nodo solo sale a internet por HTTPS 443 para sincronizar cuentas y licencia, y para recoger las solicitudes del registro por QR. Estas llegan cifradas para el nodo con X25519 + AES-256-GCM.

**Modelos** (ONNX Runtime con DirectML):

| Tarea | Modelo |
|---|---|
| Personas y vehículos | RF-DETR Nano |
| Detección de rostro | YuNet |
| Reconocimiento facial | SFace (distancia coseno 0,50) |
| Localización de la patente | YOLOv8n de una clase |
| Lectura de la patente | fast-plate-ocr |

## Estructura

```
main.py              punto de entrada del nodo
config.py            parámetros (los cambios del usuario quedan en settings.json)
database.py          acceso a la base local SQLite
setup_nodo.py        instala el nodo: crea la base local y la vincula con la nube
setup_central.py     instala la base central de la nube
core/                servicios: detector, rostros, patentes, cámaras, sesión, licencia, cifrado, nube
engine/              motor de visión (un hilo por cámara)
gui/                 interfaz Tkinter (vistas según el rol)
reports/             reportes PDF y CSV
migraciones/         esquema SQLite versionado
modelos/             modelos ONNX (no se suben: ver más abajo)
servidor/            API de la nube y formulario del registro móvil
sql/central.sql      esquema de la base central (MySQL)
despliegue/          instalación en AWS (guía, scripts y requirements del servidor)
tools/               herramientas de calibración, auditoría de red y licencias
tests/               pruebas automáticas (pytest)
docs/                anexos del informe y generadores de diagramas
licencias/, AVISOS.txt   licencias de terceros (deben acompañar al programa)
```

## Instalación del nodo (Windows)

1. Instale Python 3.12.
2. Instale las dependencias:
   ```
   py -m pip install -r requirements.txt
   py -m pip install fast-plate-ocr==1.1.0 --no-deps
   ```
3. Copie `cameras.ejemplo.json` como `cameras.json` y ponga el usuario y la clave de su grabador (o agregue las cámaras desde el programa).
4. Vincule el nodo con la nube usando la clave que entrega el proveedor:
   ```
   py setup_nodo.py --clave ugn_xxxxx --api https://su-servidor
   ```
5. Ejecute el programa:
   ```
   py main.py
   ```

La API de la nube se instala aparte, siguiendo [despliegue/GUIA_AWS.md](despliegue/GUIA_AWS.md).

## Modelos

Los cuatro modelos vienen en `modelos/` y se guardan con **Git LFS**, porque `rfdetr_nano.onnx` supera el límite de 100 MB de GitHub. Para clonar el repositorio con los modelos completos, instale Git LFS antes (`git lfs install`). Si no lo hace, en `modelos/` quedan solo archivos de referencia en lugar de los modelos.

| Archivo | Origen | Licencia |
|---|---|---|
| `rfdetr_nano.onnx` | [roboflow/rf-detr](https://github.com/roboflow/rf-detr), pesos COCO exportados a ONNX | Apache 2.0 |
| `face_detection_yunet_2023mar.onnx` | [OpenCV Zoo · YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | MIT |
| `face_recognition_sface_2021dec.onnx` | [OpenCV Zoo · SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) | Apache 2.0 |
| `license_plate_detector.onnx` | YOLOv8n de una clase, entregado por el autor | AGPL-3.0 (ver AVISOS.txt, sección 5) |

## Pruebas

```
py -m pytest -q
```

Las pruebas que necesitan MySQL o las fotos reales de las evidencias se omiten solas cuando faltan. Esas fotos no se publican porque muestran rostros y patentes reales.

## Lo que no está en el repositorio

Por seguridad y privacidad, `.gitignore` excluye:

- **Secretos:** `nodo.json`, `servidor/secreto.key` y `servidor/licencia_privada.pem`.
- **Cámaras reales:** `cameras.json`, que lleva el usuario y la clave del grabador. En su lugar va `cameras.ejemplo.json`.
- **Evidencias de las pruebas:** `tests/evidencias/`, con rostros, patentes y RUT reales. Las copias difuminadas están en `docs/anexos/capturas/`.

`setup_central.py` y `setup_nodo.py` generan los secretos en cada instalación.

## Licencias

El código es de Matías Tejada. Los modelos y las bibliotecas de terceros conservan sus propias licencias, detalladas en [AVISOS.txt](AVISOS.txt) y en la carpeta `licencias/`.
