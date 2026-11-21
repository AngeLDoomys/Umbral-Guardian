titulo: Anexo 6 · Documentación técnica
subtitulo: Manual técnico, instalación y mantenimiento de Umbral Guardian
encabezado: Umbral Guardian · Anexo 6 · Documentación técnica
archivo: Anexo_6_Documentacion_tecnica.docx

## 1. Propósito y destinatarios

Este documento explica cómo está construido Umbral Guardian, cómo se instala y cómo se mantiene en funcionamiento. Está dirigido al **técnico** que instala el sistema en un condominio, al **proveedor** que lo administra y a quien deba darle **mantenimiento**. El uso diario del programa se describe en el Anexo 9 (Manual de usuario), y la arquitectura con sus diagramas, en el Anexo 5.

## 2. Descripción técnica general

El sistema tiene dos partes:

- **Nodo de la portería (borde):** un PC con Windows y tarjeta gráfica NVIDIA, que recibe el video de las cámaras por la red local, detecta personas y vehículos, reconoce rostros y lee patentes. Todo el procesamiento de video ocurre en este equipo, y sus datos se guardan en una base SQLite local.
- **Servicio en la nube:** una API web en AWS que administra los condominios clientes, las cuentas, las licencias y el registro desde el celular. Usa una base MySQL privada.

![Vista física del sistema: qué corre en el condominio y qué corre en la nube](diagramas/08_despliegue.png)

### 2.1 Modelos de inteligencia artificial

| Función | Modelo | Archivo | Licencia |
|---|---|---|---|
| Personas y vehículos | RF-DETR Nano | `modelos/rfdetr_nano.onnx` | Apache 2.0 |
| Región de la patente | YOLOv8n entrenado para patentes | `modelos/license_plate_detector.onnx` | AGPL-3.0 (pendiente, ver `AVISOS.txt`) |
| Detección de rostros | YuNet 2023mar | `modelos/face_detection_yunet_2023mar.onnx` | MIT |
| Reconocimiento facial | SFace 2021dec (vector de 128 valores) | `modelos/face_recognition_sface_2021dec.onnx` | Apache 2.0 |
| Lectura de caracteres | fast-plate-ocr `cct-s-v2-global-model` | Se descarga la primera vez | MIT |

Los detectores corren en la GPU con **ONNX Runtime y DirectML**. Si no hay GPU, el programa usa el procesador automáticamente, con menor velocidad. El reconocimiento facial corre en el procesador con OpenCV.

### 2.2 Cómo decide el reconocimiento facial

Un rostro se acepta cuando su **distancia** a las plantillas de una persona es menor que **0,50** y supera en al menos **0,09** a la segunda persona más parecida. La decisión requiere **2 coincidencias** con mayoría de 2 a 1 en un máximo de **5 intentos válidos**. Una persona no reconocida se revisa de nuevo cada 2 segundos, y una reconocida se verifica cada 3 segundos para que otra persona no herede su nombre. El detalle del flujo se encuentra en el Anexo 5.

## 3. Requisitos

### 3.1 Equipo de la portería

| Componente | Mínimo probado |
|---|---|
| Sistema operativo | Windows 11 de 64 bits |
| Procesador y memoria | 4 núcleos y 16 GB de RAM |
| Tarjeta gráfica | NVIDIA GTX 1650 Ti con 4 GB, con un controlador actualizado. Sin GPU funciona, pero más lento |
| Disco | 2 GB libres para el programa y los modelos, más el crecimiento de la base |
| Red | En la misma red que las cámaras; salida a internet por HTTPS (puerto 443) |
| Reloj | **Sincronizado automáticamente con internet.** Las fechas de los registros y los plazos legales dependen de él |

### 3.2 Cámaras

- Cámaras IP o grabador con **RTSP**. Se recomienda configurar dos canales por cámara: uno de baja resolución para detectar (por ejemplo, 352x288) y el principal para leer rostros y patentes (por ejemplo, 1280x720).
- También se pueden usar cámaras USB.
- La cámara de rostros debe captar las caras de frente, a la altura de la persona y con buena luz.

### 3.3 Software del nodo

| Paquete | Versión verificada | Uso |
|---|---|---|
| Python | 3.12.7 | Lenguaje del programa |
| opencv-python | 4.13.0.92 | Video, rostros y dibujo |
| numpy | 2.5.0 | Cálculo numérico |
| pillow | 12.2.0 | Imágenes en la interfaz |
| onnxruntime-directml | 1.24.4 | Modelos en la GPU |
| fast-plate-ocr | 1.1.0 | Lectura de patentes |
| qrcode | 8.2 | Códigos QR de invitación |
| requests | 2.34.2 | Comunicación con la nube |
| reportlab | 4.2.5 | Reportes PDF |
| cryptography | 50.0.1 | Licencias firmadas y cifrado del registro móvil |
| pytest | 9.1.1 | Pruebas automáticas (solo desarrollo) |

## 4. Estructura del proyecto

| Carpeta o archivo | Contenido |
|---|---|
| `main.py` | Punto de entrada: verifica dependencias, abre el inicio de sesión y luego el programa |
| `config.py` | Parámetros por defecto; se complementan con `settings.json` y `nodo.json` |
| `database.py` | Acceso a la base local SQLite |
| `gui/` | Pantallas del programa (Tkinter) |
| `engine/` | Motor de visión: video, detección, seguimiento, rostros y patentes |
| `core/` | Servicios: modelos, cámaras, sesión, nube, licencias, cifrado y seguridad |
| `reports/` | Generación de reportes PDF y CSV |
| `migraciones/` | Scripts que crean y actualizan la base local (se aplican solos al iniciar) |
| `modelos/` | Los cuatro modelos ONNX |
| `servidor/` | API de la nube (Flask) y formulario de registro móvil |
| `sql/central.sql` | Esquema de la base central |
| `despliegue/` | Guía e instaladores de la nube en AWS |
| `tools/` | Herramientas de calibración, medición y auditoría de red |
| `tests/` | Pruebas automáticas y evidencias |
| `settings.json` | Configuración modificada desde el programa |
| `nodo.json` | Dirección de la API y clave del nodo (**secreto**) |
| `licencia_publica.pem` | Clave para verificar la licencia firmada por el proveedor |

La base local se guarda en `C:\ProgramData\UmbralGuardian\umbral_local.db`.

===

## 5. Instalación del nodo en la portería

### 5.1 Antes de empezar

El **proveedor** crea el condominio en su panel (**Condominios → nuevo cliente**) con su plan y su primera cuenta de administrador. El panel entrega la **clave del nodo**, con formato `ugn_…`. Esa clave se muestra una sola vez y no debe compartirse.

### 5.2 Pasos

1. **Instalar Python 3.12** de 64 bits desde python.org y marcar «Add python.exe to PATH».
2. **Copiar la carpeta del programa** al equipo, por ejemplo en `C:\UmbralGuardian`. Debe incluir `modelos/` y `licencia_publica.pem`.
3. **Instalar las dependencias** desde PowerShell, dentro de esa carpeta:

```
py -m pip install opencv-python==4.13.0.92 numpy==2.5.0 pillow==12.2.0 onnxruntime-directml==1.24.4 qrcode==8.2 requests==2.34.2 reportlab==4.2.5 cryptography==50.0.1
py -m pip install fast-plate-ocr==1.1.0 --no-deps
```

   fast-plate-ocr se instala con `--no-deps` porque, de lo contrario, reemplaza OpenCV por otra variante que entra en conflicto.

4. **Configurar el nodo** con la clave entregada por el proveedor:

```
py setup_nodo.py --clave ugn_XXXXXXXX --api https://umbralguardian-mt.duckdns.org
```

   El script crea la base local, guarda `nodo.json` y descarga la licencia y las cuentas del condominio. **Si ya existía una base local, la borra:** úselo solo en una instalación nueva.

5. **Abrir el programa:**

```
py main.py
```

   La primera vez que se lee una patente, fast-plate-ocr descarga su modelo (unos 5 MB), por lo que se necesita internet.

6. **Configurar las cámaras:** entre como administrador, vaya a **Cámaras → Añadir** y complete el nombre, la zona, la fuente de baja resolución y la fuente alta. Pulse **Probar**. Formato habitual de un grabador:

```
rtsp://USUARIO:CLAVE@192.168.1.X:554/cam/realmonitor?channel=1&subtype=1   (canal bajo)
rtsp://USUARIO:CLAVE@192.168.1.X:554/cam/realmonitor?channel=1&subtype=0   (canal alto)
```

7. **Registrar a los residentes** con su consentimiento y su rostro, por la portería o con el registro desde el celular (Anexo 9).
8. **Sincronizar la hora** del equipo: Configuración de Windows → Hora e idioma → **Establecer la hora automáticamente**.

![Cámaras configuradas en el programa](capturas/admin_06_cameras.png)

### 5.3 Verificación después de instalar

| Revisión | Resultado esperado |
|---|---|
| Inicio de sesión | Arriba aparece **EN LÍNEA** |
| Monitor con las dos cámaras | Video en ambos paneles, 15 FPS y sin aviso del canal alto |
| Un residente frente a la cámara | Recuadro verde con su nombre y unidad |
| Historial | El evento aparece en las primeras filas |
| Pruebas automáticas (opcional) | `py -m pytest -q` termina sin fallas |

===

## 6. Instalación del servicio en la nube

El procedimiento completo está en `despliegue/GUIA_AWS.md`. En resumen:

1. En **AWS Academy Learner Lab**, iniciar el laboratorio (**Start Lab**) y entrar a la consola, región **us-east-1**.
2. Crear un subdominio gratuito en **DuckDNS** (por ejemplo, `umbralguardian-mt.duckdns.org`) y guardar su token.
3. Crear dos **grupos de seguridad**: `ug-api` (entrada 443 y 80 desde internet; 22 solo desde la IP del administrador) y `ug-rds` (entrada 3306 solo desde `ug-api`).
4. Crear la base **RDS MySQL 8.4** `umbral-central`, sin acceso público y con Enhanced Monitoring desactivado.
5. Crear el servidor **EC2** `umbral-api` con Ubuntu 24.04, tipo t3.small y el grupo `ug-api`.
6. En el PC, ejecutar `despliegue\preparar_paquete.ps1`, subir la carpeta `despliegue\paquete` por `scp` y, en el servidor, ejecutar:

```
sudo bash instalar_servidor.sh umbralguardian-mt TOKEN_DUCKDNS
```

7. Editar `/etc/umbral/api.env` con el endpoint y la contraseña de RDS, importar la base y volver a ejecutar el instalador.
8. Comprobar `https://umbralguardian-mt.duckdns.org/api/salud`, que debe responder `{"ok": true}`, y borrar la carpeta `paquete` del servidor y del PC.

El instalador deja funcionando: la API con **gunicorn** en `127.0.0.1:5000`, **Caddy** con certificado HTTPS automático de Let's Encrypt, y un **temporizador** que actualiza la IP en DuckDNS en cada arranque. También fija la zona horaria `America/Santiago`.

> El paquete de despliegue contiene secretos (clave de sesión y clave privada de licencias). No se debe compartir ni subir a repositorios.

===

## 7. Configuración

### 7.1 Archivos de configuración

| Archivo | Quién lo modifica | Contenido |
|---|---|---|
| `config.py` | Desarrollador | Valores por defecto y su justificación |
| `settings.json` | Administrador, desde **Configuración** | Valores que reemplazan a los de `config.py` |
| `nodo.json` | Técnico, con `setup_nodo.py` | Dirección de la API y clave del nodo |
| `/etc/umbral/api.env` (servidor) | Técnico | Conexión a la base central |

![Pantalla de Configuración del programa](capturas/admin_11_settings.png)

### 7.2 Parámetros principales

| Parámetro | Valor | Efecto |
|---|---|---|
| `PERSON_CONFIDENCE` | 0,60 | Confianza mínima para aceptar una persona detectada |
| `VEHICLE_CONFIDENCE` | 0,45 | Confianza mínima para un vehículo |
| `PLATE_CONFIDENCE` | 0,50 | Confianza mínima para la región de una patente |
| `PLATE_MIN_CHAR_CONF` | 0,85 | Confianza mínima de cada carácter leído |
| `FACE_RECOGNITION_THRESHOLD` | 0,50 | Distancia máxima para aceptar un rostro. Subirlo acepta a más desconocidos |
| `FACE_MATCH_MARGIN` | 0,09 | Diferencia mínima con la segunda persona más parecida |
| `FACE_VOTES_REQUIRED` | 2 | Coincidencias necesarias para confirmar |
| `FACE_MAX_ATTEMPTS` | 5 | Intentos válidos antes de declarar NO RECONOCIDO |
| `PROCESS_EVERY_N_FRAMES` | 5 | Cada cuántos cuadros se ejecuta la detección |
| `SCALE_FACTOR` | 0,70 | Reducción del video cuando la cámara tiene un solo canal |
| `PLATE_MIN_VEHICLE_WIDTH` | 0,12 | Ancho mínimo del vehículo, como fracción del cuadro, para buscar su patente |
| `DIAS_RETENCION_DETECCIONES` | 90 | Días que se guarda el historial de accesos |
| `DIAS_RETENCION_VISITAS` | 30 | Días que se guardan los datos de visitas |
| `VISITA_ROSTRO_OBLIGATORIO` | Sí | Las visitas invitadas por QR deben registrar su rostro |
| `DIAS_SIN_CONEXION` | 7 | Días máximos de operación sin contactar la nube |
| `SINCRONIZAR_CADA_H` | 6 | Cada cuántas horas se renuevan la licencia y las cuentas |

Los umbrales faciales se calibraron con la base de rostros pública LFW: con 0,50, se reconoció el 97,9 % de los intentos de residentes y no se aceptó a ninguna persona desconocida. Cualquier cambio debe medirse antes con `tools/calibrar_rostros.py`.

===

## 8. Operación técnica

### 8.1 Encender el servicio en la nube

El laboratorio de AWS Academy se apaga solo al terminar cada sesión de 4 horas. Antes de usar el sistema:

1. AWS Academy → Learner Lab → **Start Lab**.
2. Revisar que el servidor **EC2 `umbral-api`** esté *Running* y la base **RDS `umbral-central`** esté *Available*. Si alguno está detenido, iniciarlo.
3. Esperar 2 a 3 minutos y abrir `https://umbralguardian-mt.duckdns.org/api/salud`.

Si la nube no está disponible, el nodo sigue operando con la copia local hasta por 7 días. Solo dejan de funcionar las cuentas, el panel del proveedor y el registro desde el celular.

### 8.2 Tareas del proveedor

Con su cuenta, el proveedor ve las pantallas **Condominios** y **Planes**:

- **Condominios:** crear clientes (**+ Nuevo condominio**), **Registrar pago**, revisar o anular pagos en **Historial de pagos**, **Cambiar plan**, **Suspender / reactivar** el servicio, restablecer contraseñas en **Cuentas y contraseñas** y generar una **Nueva clave de nodo**.
- **Planes:** crear y desactivar planes. Planes actuales: Básico (2 cámaras), Estándar (4) y Avanzado (8).

La licencia que recibe el nodo está **firmada digitalmente** por el proveedor e indica el plan y la fecha de pago. Si el pago vence, el sistema sigue operando durante un período de gracia y muestra un aviso.

## 9. Mantenimiento

### 9.1 Tareas periódicas

| Frecuencia | Tarea | Cómo |
|---|---|---|
| Diaria | Comprobar que ambas cámaras muestren video | Monitor; avisos en Eventos recientes |
| Semanal | Revisar que la hora del equipo sea correcta | Reloj de Windows sincronizado |
| Semanal | Respaldar la base local | Ver 9.2 |
| Mensual | Revisar solicitudes de privacidad pendientes | Privacidad (las vencidas aparecen en rojo) |
| Mensual | Actualizar Windows y el controlador NVIDIA | Windows Update y GeForce Experience |
| Al cambiar una cámara | Editar su fuente y pulsar **Probar** | Cámaras |
| Al cambiar de personal | Crear o desactivar cuentas | Cuentas |
| Al actualizar el programa | Ejecutar las pruebas automáticas | `py -m pytest -q` |

La **retención** se aplica sola cada vez que alguien inicia sesión: borra los eventos de rostros y vehículos con más de 90 días, las visitas registradas con más de 30 días, los datos de visitantes que ya no tienen visitas ni autorizaciones, las visitas ocasionales vencidas con su rostro y las invitaciones vencidas sin usar.

### 9.2 Respaldo y restauración

1. **Cierre el programa.**
2. Copie `C:\ProgramData\UmbralGuardian\umbral_local.db`, junto con los archivos `-wal` y `-shm` si existen, a un medio externo.
3. Guarde también `nodo.json` y `settings.json`.

Para restaurar, cierre el programa y reemplace esos archivos.

> La base local **no está cifrada**: contiene datos personales y vectores faciales. Guarde los respaldos en un medio protegido y active BitLocker en el disco del equipo.

### 9.3 Actualizar el programa

1. Respaldar la base (9.2).
2. Reemplazar los archivos del programa, conservando `nodo.json`, `settings.json` y `licencia_publica.pem`.
3. Abrir el programa: las migraciones nuevas de `migraciones/` se aplican solas.
4. Ejecutar `py -m pytest -q` y revisar el Monitor.

### 9.4 Herramientas de soporte

| Herramienta | Para qué sirve |
|---|---|
| `tools/calibrar_rostros.py` | Medir distancias reales de un residente o de una persona no registrada frente a una cámara, y comparar umbrales |
| `tools/medir_reconocimiento.py` | Medir aciertos del reconocimiento con una cámara real, sin guardar imágenes |
| `tools/auditar_red.py` | Abrir el programa registrando a qué destinos se conecta y qué campos envía, sin guardar valores |
| `tools/generar_licencias.py` | Revisar las licencias de las dependencias |

## 10. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| «Dependencias faltantes» al abrir | Falta un paquete | Instalar el paquete indicado (sección 5.2) |
| Una cámara muestra «Sin señal» | Fuente incorrecta, cámara apagada o red caída | Cámaras → **Probar**; revisar el grabador y la red. Al volver la red, el sistema reconecta solo |
| Aviso «canal alta res. sin señal» | Falla el canal principal | Revisar la fuente alta. Mientras tanto se usa el canal bajo |
| La detección es lenta (p95 sobre 100 ms) | Mucha carga en la GPU | Cerrar otros programas que usen la GPU; subir `PROCESS_EVERY_N_FRAMES` |
| El programa se cierra con dos cámaras | Controlador de la GPU | Actualizar el controlador NVIDIA. La versión actual ya serializa el uso de la GPU para evitarlo |
| Un residente no es reconocido | Plantillas de mala calidad o mala iluminación | Volver a capturar su rostro con la cámara del condominio y revisar la luz |
| Una persona desconocida se acepta como residente | Umbral demasiado permisivo | Mantener el umbral en 0,50; revisarlo con `tools/calibrar_rostros.py` |
| «SIN CONEXIÓN» permanente | Nube apagada o sin internet | Iniciar el laboratorio de AWS (8.1) y revisar `/api/salud` |
| «El equipo lleva más de 7 días sin conectarse» | Sin contacto con la nube | Restablecer internet e iniciar sesión |
| El enlace del QR no abre desde fuera | La API apunta a una dirección local | `nodo.json` debe usar la dirección HTTPS pública |
| Fechas incorrectas en historial y reportes | Reloj del equipo desfasado | Activar la sincronización automática de la hora |
| Excel muestra el CSV en una sola columna | Versión anterior del programa | La versión actual usa punto y coma; volver a exportar |

## 11. Seguridad y privacidad

- Las contraseñas se guardan con **PBKDF2-SHA256** y sal; nunca en texto plano.
- La API usa solo **HTTPS** (TLS 1.3 verificado), y la base central no tiene acceso desde internet.
- El nodo se identifica ante la API con su **clave**, de la que la nube guarda solo el hash.
- En el registro desde el celular, la nube procesa la foto en memoria, la descarta y entrega el vector **cifrado** (X25519 + AES-256-GCM) para el nodo del condominio.
- El monitoreo **no envía** video, rostros, vectores ni patentes a internet; se verificó con `tools/auditar_red.py`.
- La consola no muestra las credenciales de las cámaras.
- **Pendiente:** cifrar la base local. Mientras tanto, proteger el equipo con BitLocker y una cuenta de Windows con contraseña.
- **Secretos que nunca se comparten:** `nodo.json`, `servidor/secreto.key`, `servidor/licencia_privada.pem`, `/etc/umbral/api.env`, la clave del laboratorio (`labsuser.pem`) y las contraseñas de las cuentas.
