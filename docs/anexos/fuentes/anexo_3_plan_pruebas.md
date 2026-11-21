titulo: Anexo 3 · Plan de pruebas y evidencias
subtitulo: Pruebas de software, red y hardware de Umbral Guardian, con sus resultados
encabezado: Umbral Guardian · Anexo 3 · Plan de pruebas y evidencias
archivo: Anexo_3_Plan_de_pruebas_y_evidencias.docx

## 1. Objetivo y alcance

El plan de pruebas verifica que Umbral Guardian cumpla sus requisitos funcionales, de rendimiento, de seguridad y de privacidad, con los modelos actuales: **RF-DETR Nano** para personas y vehículos, **YuNet** y **SFace** para rostros, y **YOLOv8n** con **fast-plate-ocr** para patentes.

Las pruebas se ejecutaron entre el **12 y el 20 de noviembre de 2026**: las automáticas en el equipo de desarrollo; las de integración, rendimiento y seguridad en la portería del Condominio Parque Fray Jorge, con sus cámaras reales; y las de patentes de residentes, en un entorno controlado con un vehículo propio.

Cada resultado se registra tal como ocurrió, aunque sea una falla. Las fallas se corrigieron, se volvieron a probar y se documentan en la sección 7.

## 2. Entorno de pruebas

### 2.1 Hardware y red

| Elemento | Detalle |
|---|---|
| PC de la portería | Windows 11 Home (compilación 26200), 16 GB de RAM |
| Tarjeta gráfica | NVIDIA GTX 1650 Ti con 4 GB, ONNX Runtime con DirectML |
| Cámaras | 2 cámaras en un grabador por RTSP: Acceso Principal (rostros) y Portón Principal (vehículos) |
| Canales de video | Bajo de 352x288 para detectar; alto de 1280x720 para rostros y patentes |
| Red local | Wi-Fi del condominio, red 192.168.1.0/24 |
| Nube | AWS Academy: EC2 t3.small (Ubuntu 24.04) y RDS MySQL 8.4, HTTPS en `umbralguardian-mt.duckdns.org` |

### 2.2 Software

| Componente | Versión |
|---|---|
| Python | 3.12.7 |
| OpenCV / NumPy | 4.13.0 / 2.5.0 |
| ONNX Runtime DirectML | 1.24.4 |
| pytest | 9.1.1 |
| Umbral | Reconocimiento: distancia 0,50, margen 0,09, 2 votos, 5 intentos. Detección cada 5 cuadros |

## 3. Tipos de prueba y criterios

| Tipo | Qué se prueba | Cómo | Criterio de aprobación |
|---|---|---|---|
| **Unitarias (PU)** | Funciones aisladas: patentes, RUT, contraseñas, votación, seguimiento | pytest, automático | Todos los casos aprobados |
| **Integración (PI)** | Cámaras, motor, interfaz, base de datos y nube funcionando juntos | Manual en el condominio, con captura | Comportamiento esperado visible en pantalla y registrado en la base |
| **Rendimiento (PR)** | Latencia, precisión, disponibilidad e integridad | Medición con registro automático | Latencia p95 bajo 100 ms; precisión facial ≥ 92 %; lectura de patentes ≥ 90 %; disponibilidad ≥ 95 %; sin eventos perdidos |
| **Seguridad (PS)** | Permisos, contraseñas, HTTPS, cifrado y salida de datos | Manual y herramientas de auditoría | Sin acceso indebido ni datos expuestos |
| **Aceptación (PA)** | Uso real por el conserje y el administrador | Con los usuarios | Operación sin ayuda y acta firmada |

Clasificación según el área evaluada:

| Área | Pruebas |
|---|---|
| **Software** | PU-01 a PU-13; PI-01 a PI-12; PR-02, PR-03 y PR-05; PS-01, PS-02 y PS-04 |
| **Redes** | PI-02 (doble canal RTSP), PI-09 (sin internet), PI-13 (corte y reconexión), PS-03 (HTTPS) y PS-05 (datos hacia la nube) |
| **Hardware** | PI-03 y PR-01 (dos cámaras en la GPU), PR-04 (disponibilidad) y PR-06 (operación nocturna) |

**Latencia p95:** el 95 % de las detecciones tarda ese tiempo o menos. Se usa en lugar del promedio porque refleja los momentos de mayor carga.

===

## 4. Resultados

### 4.1 Resumen

| Estado | Pruebas |
|---|---|
| **Aprobadas** | PU-01 a PU-13; PI-01, PI-02a, PI-03a, PI-03b, PI-04a, PI-04b, PI-05, PI-06b, PI-07c, PI-09, PI-10, PI-11a, PI-11b, PI-12, PI-13; PS-01a a PS-01c, PS-02, PS-03, PS-04a y PS-05a |
| **Aprobadas en entorno controlado** | PI-06a, PI-07a y PI-07b, con un vehículo propio y la cámara de un celular |
| **Parciales** | PI-08, PR-01, PR-03 (muestra en entorno controlado), PR-05 y PS-05 |
| **No ejecutadas** | PI-02b, PR-02, PR-04, PR-06 y PA-01 a PA-06 |
| **No implementada** | PS-04b (cifrado de la base local) |

Pruebas automáticas: **158 aprobadas, 0 fallidas** y 28 no ejecutadas porque requieren el servidor MySQL local del entorno de desarrollo.

### 4.2 Pruebas unitarias

| ID | Qué verifica | Casos | Resultado |
|---|---|---|---|
| PU-01 | Formato y corrección de patentes chilenas | 25/25 | Aprobada |
| PU-02 | Validación y formato del RUT | 12/12 | Aprobada |
| PU-03 | Hash de contraseñas | 3/3 | Aprobada |
| PU-04 | Política de contraseñas | 4/4 | Aprobada |
| PU-05 | Normalización de patentes para búsqueda | 4/4 | Aprobada |
| PU-06 | Medidor de latencia | 3/3 | Aprobada |
| PU-07 | Asociación de patente con vehículo | 3/3 | Aprobada |
| PU-08 | Votación de patentes | 4/4 | Aprobada |
| PU-09 | Votación facial | 9/9 | Aprobada |
| PU-10 | Recuadros entre canal bajo y alto | 2/2 | Aprobada |
| PU-11 | Aviso de cambios a los motores | 2/2 | Aprobada |
| PU-12 | Recarga de la configuración | 2/2 | Aprobada |
| PU-13 | Seguimiento de personas | 7/7 | Aprobada |

Además, 15 casos verifican a nivel de base de datos el registro de rostros (PI-04/05), patentes (PI-06), bloqueo y revocación (PI-08), retención (PI-10), derechos del titular (PI-12) e integridad (PR-05): 15/15 aprobados.

### 4.3 Pruebas de integración

| ID | Qué se hace | Resultado | Datos medidos |
|---|---|---|---|
| PI-01 | Cámara → motor → Monitor | Aprobada | Acceso Principal: 15 FPS, 50 ms, p95 82 ms. Portón Principal: 15 FPS, 48 ms, p95 78 ms |
| PI-02a | Doble canal activo | Aprobada | Canal bajo 352x288 y alto 1280x720 en ambas cámaras, sin avisos de falla |
| PI-02b | Canal alto caído: sigue con el bajo | No ejecutada | — |
| PI-03a | Dos cámaras a la vez | Aprobada | Ambas a 15 FPS; p95 82 y 78 ms |
| PI-03b | Misma cámara en dos paneles | Aprobada | El segundo panel no se inicia y muestra el aviso |
| PI-04a | Residente reconocido | Aprobada | Recuadro verde con nombre y unidad; confianza 0,60 |
| PI-04b | Residente visible en Historial | Aprobada | Registro con hora, cámara, zona y 60 % de confianza |
| PI-05 | Persona no registrada | Aprobada | Recuadro naranja «NO RECONOCIDO» |
| PI-06a | Patente de residente | Aprobada (entorno controlado) | Recuadro verde con patente y unidad; confianza de lectura 99,9 % |
| PI-06b | Patente no registrada | Aprobada | «NO REGISTRADO»; confianza de lectura 99,8 % |
| PI-07a | Registrar una patente sin detener el Monitor | Aprobada (entorno controlado) | La patente salió «NO REGISTRADO» y se registró con el Monitor funcionando |
| PI-07b | Reconocer la patente sin reiniciar | Aprobada (entorno controlado) | Primera lectura como residente 64 s después de registrarla, sin reiniciar el programa |
| PI-07c | Cambio de configuración sin reiniciar | Aprobada | Mensaje «Guardado y aplicado»; valor guardado |
| PI-08 | Bloqueo y revocación con el Monitor funcionando | Parcial | Bloqueo aprobado: deja de reconocer en menos de 36 s y vuelve a reconocer al levantarlo, sin perder las plantillas. Falta la revocación en vivo |
| PI-09 | Inicio de sesión sin internet | Aprobada | Ingreso con la copia local y aviso «SIN CONEXIÓN» |
| PI-10 | Retención al iniciar sesión | Aprobada | Visitas vencidas de 3 a 0 y sus plantillas faciales de 15 a 0 |
| PI-11a | Reporte PDF | Aprobada | Totales iguales a la base de datos |
| PI-11b | Reporte CSV | Aprobada | Excel lo abre con 4 columnas y 12 filas |
| PI-12 | Derechos del titular | Aprobada | Solicitud de acceso acogida; el archivo entregado no incluye vectores faciales |
| PI-13 | Corte y reconexión de red | Aprobada | Corte de 26 s; las cámaras se recuperaron solas 12 s después de volver la red |

### 4.4 Pruebas de rendimiento

| ID | Qué se mide | Criterio | Resultado | Datos |
|---|---|---|---|---|
| PR-01 | Dos cámaras en funcionamiento continuo | p95 < 100 ms durante 1 hora | Parcial | Muestra de 20,7 min sin caídas y con conexiones estables; al final, p95 de 76 y 80 ms. No alcanzó la hora exigida |
| PR-02 | Precisión del reconocimiento facial | ≥ 92 % | No ejecutada | Sin conjunto de validación en terreno. Referencia de laboratorio con la base LFW: 97,9 % por intento, sin desconocidos aceptados |
| PR-03 | Lectura de patentes | ≥ 90 % | Parcial (entorno controlado) | 19 de 19 lecturas correctas (100 %) de un solo vehículo, con distintas distancias y ángulos. No reemplaza la medición con varios autos en el condominio |
| PR-04 | Disponibilidad | ≥ 95 % | No ejecutada | Requiere un registro de varios días |
| PR-05 | Eventos en pantalla iguales a eventos en la base | Sin pérdidas | Parcial | 24 eventos en pantalla y 24 en la base, con las mismas horas, en 20 min. Sin eventos de vehículos en el período |
| PR-06 | Operación nocturna | Por definir | No ejecutada | Sin autorización para ingresar de noche al condominio |

> En muestras breves con varios vehículos en cuadro, el p95 llegó a 128, 178 y 205 ms. Se redujo la carga de búsqueda de patentes en la GPU (sección 7, n.º 14), y en la muestra posterior el p95 quedó en 76 y 80 ms. La confirmación definitiva requiere completar PR-01.

### 4.5 Pruebas de seguridad

| ID | Qué se verifica | Resultado | Datos |
|---|---|---|---|
| PS-01a | El conserje no ve Cámaras, Reportes, Privacidad, Cuentas ni Configuración | Aprobada | Menú limitado al rol |
| PS-01b | El conserje puede registrar y eliminar vehículos | Aprobada | Comportamiento esperado según el protocolo |
| PS-01c | RUT enmascarado en Visitas | Aprobada | Se muestra como `20.675.***-*` |
| PS-02 | Contraseñas sin texto plano | Aprobada | Solo hashes PBKDF2 en la base |
| PS-03 | HTTPS en la API | Aprobada | TLS 1.3, certificado válido, HTTP redirige a HTTPS; puertos 5000 y 3306 cerrados desde internet |
| PS-04a | Cifrado del registro móvil | Aprobada | X25519 + AES-256-GCM: otra clave no lo abre y un paquete alterado se rechaza |
| PS-04b | Cifrado de la base local | No implementada | Se declara como limitación |
| PS-05a | Los modelos no envían información fuera del condominio | Aprobada | En 6,5 min con dos cámaras, los modelos no abrieron conexiones; Windows solo registró conexiones a las cámaras locales |
| PS-05 | Datos que salen hacia la nube | Parcial | No cubre el inicio de sesión en línea ni el registro móvil, que envía datos y foto a la nube con consentimiento |

### 4.6 Pruebas de aceptación

PA-01 a PA-06 (turno del conserje sin ayuda, registro de residente por el administrador, consulta del historial, reportes, solicitudes del titular y firma del acta) **no se ejecutaron** por falta de coordinación con el personal del condominio. Quedan como pendientes.

===

## 5. Evidencias visuales

Las capturas son del condominio. Los rostros y las patentes se difuminaron para proteger a las personas.

![PI-04a: residente reconocido en verde con su unidad, y evento en el panel lateral](capturas/real_residente_reconocido.png)

![PI-05: persona no registrada, en naranja como «NO RECONOCIDO»](capturas/real_no_reconocido.png)

![PI-06b: vehículo con patente no registrada (patente difuminada)](capturas/real_patente_no_registrada.png)

![PI-03b: la misma cámara no se abre en dos paneles; aviso en Eventos recientes](capturas/real_misma_camara.png)

![PI-13: ambas cámaras recuperadas después de un corte de red, sin intervención](capturas/real_reconexion.png)

![PI-09: inicio de sesión sin internet, con el aviso «SIN CONEXIÓN»](capturas/real_sin_conexion.png)

![PI-07c: cambio de configuración aplicado sin reiniciar](capturas/real_configuracion_aplicada.png)

![PI-11a: reporte de tráfico por zona y horario en PDF](capturas/real_reporte_pdf.png)

![PS-01a: menú del conserje, sin opciones de administración](capturas/real_menu_conserje.png)

### 5.1 Pruebas de vehículos en entorno controlado

Se hicieron el 20 de noviembre de 2026, entre las 19:45 y las 19:50, con el auto del autor y la cámara de un celular conectada al PC como cámara USB. La patente está difuminada.

![PI-07a: antes de registrarla, la patente sale «NO REGISTRADO»](capturas/casa_patente_no_registrada.png)

![PI-07a: la patente se registra en Vehículos sin detener el Monitor](capturas/casa_registro_vehiculo.png)

![PI-06a y PI-07b: el mismo auto, ahora en verde con su unidad y sin reiniciar el programa](capturas/casa_patente_reconocida.png)

===

## 6. Prueba de salida de datos (solicitada por el profesor)

**Pregunta:** ¿los modelos envían información fuera del condominio?

**Método:** el programa se abrió con la herramienta `tools/auditar_red.py`, que registra cada conexión que hace el programa y el módulo que la origina, sin guardar contenido. En paralelo, Windows registró dos veces por segundo las conexiones del proceso, incluidas las de las bibliotecas internas. Se mantuvieron las dos cámaras funcionando durante 6,5 minutos, con 4 eventos de rostro y 1 de vehículo.

**Resultado:**

| Revisión | Resultado |
|---|---|
| Conexiones abiertas por los modelos | Ninguna |
| Conexiones del programa vistas por Windows | Solo las cámaras de la red local (puerto 554) |
| Datos, imágenes o campos sensibles enviados | Ninguno |
| Único intento hacia internet | El inicio de sesión (`core/cloud.py`) |

**Alcance:** durante la prueba la nube estaba apagada, por lo que no se observó un inicio de sesión en línea. El registro desde el celular, que sí envía datos y foto con consentimiento, es un flujo aparte. La conclusión correcta es que **el monitoreo y sus modelos no envían información fuera del condominio**.

## 7. Hallazgos corregidos durante las pruebas

| N.º | Hallazgo | Corrección |
|---|---|---|
| 1 | En la nube, después de las 21:00, una visita quedaba autorizada para el día siguiente (servidor en UTC) | El instalador fija la zona horaria de Chile |
| 2 | Una persona no registrada, parecida a un residente, fue aceptada (distancia 0,54) | Umbral ajustado de 0,60 a 0,50 tras medirlo con LFW |
| 3 | Quien ocupaba el lugar de una persona reconocida heredaba su nombre | Verificación cada 3 s; se descarta con 2 rostros distintos seguidos |
| 4 | Dos personas que se cruzaban podían intercambiar su identidad | Predicción de movimiento y verificación al separarse |
| 5 | El programa se cerraba con dos cámaras (falla del controlador de la GPU) | Uso de la GPU de a una tarea y un solo modelo cargado |
| 6 | El CSV se abría en una sola columna en Excel | Separador punto y coma |
| 7 | El encabezado del PDF casi no se leía | Colores corregidos |
| 8 | La etiqueta «NO RECONOCIDO» se cortaba | El fondo cubre todo el texto |
| 9 | Un PDF podía guardarse con extensión .csv | La ventana muestra solo el formato elegido |
| 10 | El mensaje «Guardado y aplicado» quedaba fuera de la ventana | Botones en una fila inferior |
| 11 | Al reiniciar una cámara sin red podía quedar una conexión duplicada | Cada inicio tiene su propia señal de detención |
| 12 | Con el reloj retrasado, los registros nuevos no aparecían en Historial | Orden por registro, no por fecha |
| 13 | Los nombres largos se cortaban y los acentos salían como «??» | Etiqueta ajustada a la imagen y sin acentos |
| 14 | La búsqueda continua de patentes recargaba la GPU | Una búsqueda a la vez por cámara; se ignoran vehículos muy pequeños |
| 15 | La consola mostraba usuario y contraseña de las cámaras | Se ocultan en la consola |

Cada corrección quedó cubierta por pruebas automáticas, salvo las de interfaz (7, 8, 10 y 13), que se verificaron con capturas.

## 8. Limitaciones y observaciones

- **Las fechas de algunas evidencias** del 12 al 18 de noviembre se tomaron con el reloj del PC desfasado (marcaba 12-11-2026). En el registro se anotó la hora real obtenida de internet. Desde el 18-11-2026 a las 11:40, el reloj está sincronizado.
- **«Accesos» no equivale a personas:** los reportes cuentan eventos de reconocimiento, y una misma persona puede generar varios.
- **Eventos repetidos:** con dos personas juntas frente a la cámara se registraron varios eventos en pocos segundos. Queda pendiente revisar si la verificación periódica los multiplica.
- **Precisión facial en terreno (PR-02):** solo hay una referencia de laboratorio (LFW), que no reemplaza la medición con las cámaras del condominio.
- **Operación nocturna (PR-06):** no se evaluó; el informe no afirma desempeño de noche.
- **Pruebas de vehículos:** PI-06a, PI-07a, PI-07b y la muestra de PR-03 se hicieron con un vehículo propio y la cámara de un celular. Son pruebas en entorno controlado: demuestran la función, pero no el desempeño con las cámaras y el tráfico del condominio.
- **Base local sin cifrar (PS-04b):** se recomienda proteger el equipo con BitLocker.

## 9. Archivos de evidencia

Las evidencias originales están en `tests/evidencias/rfdetr_sface/` del repositorio:

| Archivo | Contenido |
|---|---|
| `REGISTRO.md` | Planilla con fecha, hora, resultado y datos de cada prueba |
| `Respaldo_pruebas_Umbral_Guardian.docx` | Respaldo de resultados y hallazgos |
| `PU_resultados.txt`, `PI-BD_resultados.txt`, `suite_completa.txt` | Resultados de las pruebas automáticas |
| `entorno.txt` | Versiones y huellas SHA-256 de los modelos |
| `PI-*.png`, `PS-*.png`, `PR-*.png` | Capturas originales (con datos personales: no publicar sin difuminar) |
| `PI-13_conexiones.csv`, `PR-01_monitor.csv` | Mediciones segundo a segundo |
| `PR-03_muestra_casa.csv` | Lecturas de patente de la prueba en casa, sin la patente |
| `PS-03.txt`, `PS-04a.txt`, `PS-05_resumen.txt` | Resultados de seguridad |
