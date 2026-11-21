titulo: Anexo 5 · Diseño estructural
subtitulo: Arquitectura del sistema, modelo de vistas 4+1, red y datos
encabezado: Umbral Guardian · Anexo 5 · Diseño estructural
archivo: Anexo_5_Diseno_estructural.docx

## 1. Introducción

Este anexo describe la arquitectura de Umbral Guardian con el modelo de **vistas 4+1** de Kruchten: una vista de escenarios, que guía a las demás, y las vistas lógica, de procesos, de desarrollo y física. Se agregan el diagrama de red y los modelos de datos.

Los diagramas describen el sistema tal como está implementado. Los modelos entidad-relación se generaron automáticamente desde el esquema real de las bases de datos.

### 1.1 Estilo de arquitectura

El sistema usa una arquitectura **borde y nube**:

- **Borde (portería del condominio):** el video se procesa en el mismo PC que lo recibe. Las imágenes, los vectores faciales y el historial de accesos quedan dentro del condominio, y el sistema sigue operando si se corta internet.
- **Nube (proveedor):** administra clientes, cuentas, licencias y el registro desde el celular. No recibe el video ni el historial de accesos.

| Decisión | Motivo |
|---|---|
| Procesar el video en el condominio | Privacidad de los datos biométricos, menor latencia y operación sin internet |
| Modelos ONNX en la GPU con DirectML | Funciona con cualquier tarjeta compatible con DirectX 12, sin instalar CUDA |
| Dos canales de video por cámara | El canal bajo permite detectar rápido; el alto, leer rostros y patentes con detalle |
| SQLite como base local | Sin servidor que instalar ni mantener en la portería |
| Licencia firmada digitalmente | El nodo verifica plan y pago sin consultar la nube en cada uso |
| Registro móvil cifrado para el nodo | La nube procesa la foto y la descarta; solo el nodo puede leer el resultado |

===

## 2. Vista de escenarios

Muestra quién usa el sistema y para qué. Estos casos de uso orientan las demás vistas.

![Casos de uso por actor](diagramas/01_casos_de_uso.png)

| Actor | Escenario principal |
|---|---|
| Conserje | Ve las cámaras, recibe los avisos de reconocimiento y registra las visitas |
| Administrador | Además, registra residentes con consentimiento, configura cámaras y atiende derechos de privacidad |
| Residente o visita | Se registra desde su celular con datos, consentimiento y fotos |
| Proveedor | Administra condominios, planes, pagos y claves de nodo |

===

## 3. Vista lógica

Presenta las clases principales y sus responsabilidades. La interfaz (`UmbralGuardianApp` y sus vistas) delega el video en un `SecurityEngine` por cada panel de cámara. El motor usa los detectores ONNX, los lectores de video y los módulos de rostros y patentes, y guarda cada evento con `DatabaseManager`.

![Diagrama de clases principales](diagramas/02_clases.png)

| Clase o módulo | Responsabilidad |
|---|---|
| `UmbralGuardianApp` | Ventana principal, menú según el rol y navegación entre vistas |
| `MonitorView` y `CameraSlot` | Dos paneles de cámara, eventos recientes y estadísticas |
| `SecurityEngine` | Motor de visión de una cámara: detección, seguimiento, rostros, patentes y registro |
| `OnnxDetector` | Ejecuta RF-DETR y el detector de patentes en la GPU, con un candado común |
| `LiveStream` y `HighResStream` | Leen el canal bajo y el alto, y reconectan solos si se pierde la señal |
| `face_utils` | YuNet, SFace, comparación, seguimiento de personas y dibujo |
| `plate_utils` | Lectura de patentes y validación del formato chileno |
| `DatabaseManager` | Acceso a la base local, retención y exportación de datos del titular |
| `Session` y `cloud` | Inicio de sesión con la nube o sin conexión, y verificación de licencia |
| `registro_remoto` | Invitaciones del registro móvil y descarga de solicitudes cifradas |
| `ReportGenerator` | Reportes PDF y CSV |

===

## 4. Vista de procesos

Describe cómo colaboran los procesos e hilos en tiempo de ejecución.

### 4.1 Hilos del nodo

Cada cámara activa tiene su propio motor, con tres hilos:

| Hilo | Tarea |
|---|---|
| Video y detección | Lee el cuadro más reciente, ejecuta RF-DETR cada 5 cuadros, sigue a las personas y dibuja el resultado |
| Rostros | Busca el rostro en el canal alto, lo compara y vota la identidad |
| Patentes | Busca la patente del vehículo en el canal alto y la lee (una búsqueda a la vez por cámara) |

Los lectores de video corren en hilos aparte y descartan los cuadros atrasados, para que el video no se retrase. Todos los usos de la GPU pasan por un **candado común**, porque DirectML no admite inferencias simultáneas.

### 4.2 Reconocimiento de una persona

![Secuencia de reconocimiento facial en el Monitor](diagramas/03_secuencia_reconocimiento.png)

### 4.3 Decisión de identidad

El reconocimiento no se decide con una sola imagen: se acumulan votos, se evita decidir mientras dos personas se superponen y se verifica periódicamente a quien ya fue reconocido.

![Actividad: decisión de identidad y verificación](diagramas/06_actividad_decision.png)

### 4.4 Registro desde el celular

![Secuencia del registro desde el celular](diagramas/04_secuencia_registro_movil.png)

### 4.5 Inicio de sesión con o sin conexión

![Secuencia del inicio de sesión](diagramas/05_secuencia_inicio_sesion.png)

===

## 5. Vista de desarrollo

Muestra cómo se organiza el código fuente y qué paquetes dependen de cuáles.

![Paquetes del proyecto y sus dependencias](diagramas/07_paquetes.png)

| Paquete | Lenguaje y bibliotecas | Pruebas automáticas |
|---|---|---|
| `gui/` | Python, Tkinter | Vista de cámaras e historial |
| `engine/` | Python, OpenCV, NumPy | Seguimiento, votación, reinicio del motor |
| `core/` | ONNX Runtime, OpenCV, cryptography, requests | Detectores, rostros, cifrado, patentes, RUT y contraseñas |
| `database.py` y `migraciones/` | SQLite | Integración con base temporal |
| `reports/` | ReportLab | Formato CSV |
| `servidor/` | Flask, MySQL | Registro móvil y proveedor |

Las pruebas usan **pytest**: 158 pruebas aprobadas y 28 que requieren MySQL local (detalle en el Anexo 3).

===

## 6. Vista física

Indica dónde se ejecuta cada componente.

![Despliegue: condominio y nube](diagramas/08_despliegue.png)

| Nodo | Componentes | Características |
|---|---|---|
| PC de la portería | Programa, modelos, base SQLite | Windows 11, GTX 1650 Ti de 4 GB, 16 GB de RAM |
| Grabador y cámaras | Dos cámaras con canal bajo (352x288) y alto (1280x720) | RTSP en la red local |
| Servidor EC2 `umbral-api` | Caddy, gunicorn y API Flask | Ubuntu 24.04, t3.small, AWS us-east-1 |
| Base RDS `umbral-central` | MySQL 8.4 | Sin acceso público |
| DuckDNS | Nombre `umbralguardian-mt.duckdns.org` | Se actualiza al arrancar el servidor |
| Celular | Navegador | Solo para el registro por invitación |

===

## 7. Diagrama de red

![Red del condominio y de la nube, con puertos y reglas de acceso](diagramas/09_red.png)

| Origen | Destino | Puerto | Para qué |
|---|---|---|---|
| PC de la portería | Grabador (red local) | 554/TCP (RTSP) | Video, dos canales por cámara |
| PC de la portería | API en AWS | 443/TCP (HTTPS) | Inicio de sesión, licencia, cuentas e invitaciones |
| Celular | API en AWS | 443/TCP (HTTPS) | Formulario de registro |
| Internet | Servidor EC2 | 80/TCP | Solo para emitir el certificado de Let's Encrypt |
| IP del administrador | Servidor EC2 | 22/TCP (SSH) | Mantenimiento |
| Servidor EC2 | RDS | 3306/TCP | Base central; RDS no acepta otro origen |

El condominio **no abre puertos hacia internet**: todas sus conexiones son salientes. Se verificó que los puertos 5000 y 3306 no responden desde internet y que el monitoreo solo se conecta a las cámaras de la red local (Anexo 3, PS-03 y PS-05a).

===

## 8. Modelo de datos

### 8.1 Base local del condominio (SQLite)

Contiene residentes, consentimientos, plantillas faciales, vehículos, visitas, cámaras, eventos de detección, solicitudes de derechos y el registro móvil. Por su tamaño se presenta en tres diagramas por tema; las tablas `unidad` y `residente` aparecen en más de uno porque los conectan.

![Base local: residentes, cámaras y eventos de acceso](diagramas/10a_er_local_residentes_accesos.png)

![Base local: visitas y registro desde el celular](diagramas/10b_er_local_visitas_registro_movil.png)

![Base local: cuentas, licencia y derechos del titular](diagramas/10c_er_local_cuentas_privacidad.png)

### 8.2 Base central del proveedor (MySQL)

Contiene planes, condominios, suscripciones, pagos, cuentas, nodos y los envíos cifrados del registro móvil. **No contiene datos biométricos ni el historial de accesos.**

![Modelo entidad-relación de la base central (generado desde el esquema)](diagramas/11_er_central.png)

### 8.3 Dónde vive cada dato

| Dato | Dónde se guarda | Cuánto tiempo |
|---|---|---|
| Video | No se guarda | — |
| Foto del registro móvil | No se guarda: se procesa en memoria en la nube | — |
| Vector facial de residente | Base local | Mientras tenga consentimiento vigente |
| Vector facial de visita | Base local | Ocasional: hasta el día siguiente. Frecuente: hasta que se revoque |
| Eventos de acceso | Base local | 90 días |
| Datos de visitas | Base local | 30 días |
| Registro móvil en tránsito | Base central, cifrado para el nodo | Hasta que el nodo lo descarga |
| Cuentas y licencias | Base central, con copia en la base local | Mientras exista el contrato |
