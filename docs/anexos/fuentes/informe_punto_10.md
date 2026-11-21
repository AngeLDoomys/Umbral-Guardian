titulo: Punto 10 · Diseño de la solución
subtitulo: Diagramas de arquitectura, procesos, casos de uso, datos e infraestructura
encabezado: Umbral Guardian · Informe final · Punto 10
archivo: ../informe/Punto_10_Diseno_de_la_solucion.docx

## 10. Diseño de la solución

Este punto presenta el diseño de Umbral Guardian a través de trece diagramas, ordenados desde la vista general hasta el detalle físico: arquitectura y componentes, procesos de negocio, casos de uso, modelo de datos e infraestructura. Respecto de la versión revisada anteriormente, los diagramas incorporan el **registro móvil por invitación QR**, que permite a un residente o a una visita inscribirse desde su propio celular, y reflejan que la base de datos del nodo de borde es ahora **SQLite**.

## 10.1 Arquitectura de la solución

### 10.1.1 Arquitectura en dos planos

![Arquitectura en dos planos](../informe/diagramas/3-7_arquitectura.png)

La solución se divide en dos planos con responsabilidades separadas. El **plano de control** vive en la nube del proveedor (AWS) y contiene la API REST en Flask, el formulario de registro móvil y la base central `umbral_central` (MySQL en RDS, nueve tablas). Allí se administran condominios, planes, suscripciones, pagos, cuentas y nodos, y se emite la licencia firmada con Ed25519 que habilita a cada nodo.

El **plano de datos** es el nodo de borde instalado en la portería. Recibe el video del grabador Hikvision por RTSP en modo sólo lectura y ejecuta un motor de visión por cámara, que detecta sobre el canal de baja resolución y recorta desde el principal. La rama peatonal encadena RF-DETR Nano, YuNet, filtros de calidad y SFace; compara el vector de 128 dimensiones contra residentes y visitas autorizadas con distancia coseno 0,50 y margen 0,09, y confirma la identidad con dos coincidencias. La rama vehicular encadena RF-DETR Nano, un seguidor propio por IoU, el detector de patentes y fast-plate-ocr, y confirma la patente con dos lecturas idénticas. El resultado se registra en la base local `umbral_local` (SQLite, veinte tablas) y se avisa en vivo a la interfaz del conserje.

El **registro móvil** une ambos planos sin exponer el nodo: el celular del residente o la visita envía sus datos, su consentimiento y cinco fotos al formulario en la nube, que calcula el vector SFace, descarta las fotos y cifra la solicitud con la clave pública del nodo. El nodo descarga esas solicitudes cada 60 segundos, las descifra y las deja pendientes hasta que el conserje o el administrador las aprueba. El video y el historial de accesos nunca salen del plano de datos, y la decisión de abrir el portón sigue siendo humana (RN-01).

### 10.1.2 Componentes de software e interfaces

![Componentes de software e interfaces](../informe/diagramas/3-8_componentes.png)

El diagrama de componentes detalla los módulos de cada subsistema y las interfaces por las que se comunican. En el nodo de borde, `InterfazConserjeria` (Tkinter) consume los servicios de monitoreo, autenticación, verificación de licencia, reportes y registro móvil. `MotorVision` orquesta un hilo por cámara y usa los componentes de captura, detección de objetos, reconocimiento facial y lectura de patentes. Todo acceso a la persistencia pasa por `AccesoDatos` (`database.py`), la única puerta hacia la base SQLite embebida.

Los componentes nuevos son `ClienteRegistroMovil`, que consulta la nube cada 60 segundos y guarda las solicitudes por aprobar; `Cifrado`, que descifra cada solicitud con X25519, HKDF y AES-256-GCM; y, en la nube, `RegistroMovil`, que publica el formulario del QR al celular por HTTPS. Las conexiones del nodo hacia la nube son siempre salientes por HTTPS 443, a través de `IApiCentral`.

## 10.2 Procesos de negocio

### 10.2.1 Situación actual

![Proceso de control de acceso · situación actual](../informe/diagramas/bpmn_situacion_actual.png)

Hoy el control de acceso depende por completo del conserje: identifica visualmente a quien ingresa, consulta por citófono cuando no lo reconoce y anota el ingreso en un cuaderno. El proceso no deja un registro confiable cuando el conserje omite la anotación, y su exactitud depende de que el conserje conozca a cada residente.

### 10.2.2 Proceso propuesto

![Proceso de control de acceso · situación propuesta](../informe/diagramas/bpmn_propuesto.png)

En el proceso propuesto, Umbral Guardian identifica primero a la persona o al vehículo y entrega el resultado al conserje. Para personas, el sistema detecta y alinea el rostro con YuNet, calcula el vector con SFace y lo compara con los residentes y las visitas autorizadas, de modo que la persona queda marcada como residente, como visita autorizada o como no reconocida. Para vehículos, delimita la placa, la lee con fast-plate-ocr y valida el formato chileno. Toda detección queda registrada.

La conserjería decide con esa información. A un residente reconocido se le abre el portón dentro del horario de apertura automática. A una **visita autorizada mediante QR** se le abre directamente, porque ya fue aprobada y su vigencia se verificó. A una persona no reconocida se le aplica el procedimiento habitual de consulta por citófono. Cada ingreso queda registrado con fecha, hora y medio de identificación.

### 10.2.3 Inscripción de residentes y visitas

![Proceso de inscripción presencial y por invitación QR](../informe/diagramas/bpmn_inscripcion.png)

La inscripción admite dos caminos. En el **presencial**, la conserjería completa la ficha, presenta el formulario de consentimiento, registra al tutor si se trata de un menor de 16 años (art. 16 quáter de la Ley 19.628), captura el rostro y registra los vehículos; el nodo calcula y almacena la plantilla facial junto al consentimiento y la cuenta que lo obtuvo. Si la persona no otorga el consentimiento, se registra la negativa y la inscripción no se realiza.

En el camino **por celular**, la conserjería genera una invitación QR de residente o de visita. La persona la escanea, lee y acepta el consentimiento, ingresa sus datos y toma cinco fotos. La nube valida que la invitación esté vigente y no se haya usado, verifica que las fotos tengan un rostro claro, calcula los vectores SFace, descarta las fotos y cifra la solicitud para el nodo. El nodo la descarga y la descifra, y la conserjería la revisa: si la aprueba, se crea el residente o la visita autorizada con sus plantillas; si no, la solicitud se rechaza.

## 10.3 Casos de uso

### 10.3.1 Conserje

![Casos de uso del conserje](../informe/diagramas/cu_conserje.png)

El conserje inicia sesión, monitorea el acceso de personas y vehículos (ambos casos incluyen registrar la detección), registra visitas y marca su salida, y puede buscar a un residente por fotografía, búsqueda que se extiende a la consulta del historial. Con el registro móvil se agregan tres casos: generar una invitación QR, revisar una solicitud de registro, cuya aprobación se extiende a crear el residente o la visita autorizada, y consultar las visitas autorizadas.

### 10.3.2 Administrador del condominio

![Casos de uso del administrador del condominio](../informe/diagramas/cu_administrador.png)

El administrador gestiona a los residentes y sus vehículos, las cámaras y las zonas, los reportes de acceso y las solicitudes de derechos del titular. Registrar un residente se extiende a capturar la plantilla facial sólo cuando el residente otorga el consentimiento informado. Al igual que el conserje, el administrador puede generar invitaciones QR y revisar las solicitudes de registro, y además administra las visitas autorizadas y su vigencia.

### 10.3.3 Proveedor del servicio

![Casos de uso del proveedor del servicio](../informe/diagramas/cu_proveedor.png)

El proveedor opera únicamente sobre el plano de control: administra los condominios y sus planes, las suscripciones y los pagos, las cuentas de cada condominio, la licencia del nodo y los parámetros del sistema. No accede a los datos personales ni a las plantillas biométricas, que residen en el nodo del condominio. El registro móvil no modifica sus casos de uso.

### 10.3.4 Residente o visita

![Casos de uso del residente o la visita desde su celular](../informe/diagramas/cu_residente_visita.png)

Este actor es nuevo y aparece con el registro móvil. Desde su propio celular abre la invitación QR y envía su solicitud de registro, lo que incluye otorgar el consentimiento informado y tomar las fotos del rostro. No inicia sesión ni instala una aplicación: el enlace del QR vence y sirve una sola vez, y las fotos se descartan en la nube después de calcular el vector facial.

## 10.4 Modelo de datos

### 10.4.1 Base local del nodo (SQLite)

![Modelo entidad-relación de la base local del nodo](../informe/diagramas/der_local.png)

La base local reside en el nodo de borde y usa **SQLite**, un motor embebido que se guarda como un archivo y no abre ningún puerto de red. Por eso los tipos son los de SQLite: `integer`, `text`, `real`, `blob`, `date` y `datetime`. Las fechas se guardan como texto en formato ISO, y los valores lógicos como enteros 0 o 1. Contiene veinte tablas, agrupadas por función:

- **Residentes y accesos:** `unidad`, `tipo_residente`, `residente`, `consentimiento`, `plantilla_facial`, `vehiculo`, `zona`, `camara`, `deteccion_rostro` y `deteccion_vehiculo`.
- **Visitas:** `visitante`, `visita` (registro por carnet), `visita_autorizada` y `plantilla_visita`.
- **Registro móvil:** `invitacion`, `solicitud_registro` y `solicitud_plantilla`, que guardan la invitación, los datos recibidos y los vectores faciales hasta que la solicitud se revisa.
- **Cuentas y privacidad:** `cuenta_local`, `solicitud_derecho` y `licencia`.

`deteccion_rostro` puede apuntar a un residente o a una visita autorizada, según quién fue reconocido. La tabla `licencia` no se relaciona con otras porque guarda un único registro, la licencia firmada del nodo; su vínculo con el condominio está en la base central.

### 10.4.2 Base central (MySQL en AWS RDS)

![Modelo entidad-relación de la base central](../informe/diagramas/der_central.png)

La base central reside en la nube y contiene sólo datos de administración del servicio: `condominio`, `plan`, `suscripcion`, `pago`, `rol`, `cuenta` y `nodo`. Para el registro móvil se agregan `invitacion_registro`, que guarda el hash del token del QR, su tipo y su vencimiento, y `envio_registro`, que guarda la solicitud **ya cifrada** para el nodo, ilegible para el proveedor. El nodo publica su clave pública en `nodo.clave_registro`. Además, `cuenta.debe_cambiar_password` obliga a cambiar la contraseña temporal en el primer ingreso, y `pago` registra la anulación de un pago. Esta base no contiene video, historial de accesos ni fotos.

## 10.5 Infraestructura y comunicaciones

### 10.5.1 Infraestructura física

![Infraestructura física](../informe/diagramas/infraestructura.png)

El diagrama muestra qué equipo hay, dónde está y cuál se compra. Las dos cámaras IP, el grabador, el portón, el citófono y el router ya existen en el condominio. El proyecto aporta sólo el PC dedicado del nodo de borde, con una GPU NVIDIA GTX 1650 Ti, y una cámara USB para enrolar en la caseta. En la nube se arriendan el servidor de aplicación (EC2) y la base central (RDS). El registro por QR no agrega equipo, porque cada residente o visita usa su propio celular, que se conecta sólo a la nube.

### 10.5.2 Topología de comunicación

![Topología de comunicación](../informe/diagramas/topologia.png)

La topología muestra por dónde viaja cada dato y en qué sentido:

- **Video:** el video viaja por RTSP 554 desde el grabador al nodo, dentro de la red del condominio, y no sale de ella.
- **Base local:** el nodo accede a SQLite como un archivo local, sin puerto de red.
- **Nodo hacia la nube:** el único enlace entre el condominio y la nube es HTTPS 443, y siempre lo abre el nodo. Cada seis horas sincroniza cuentas y licencia, y cada 60 segundos consulta las solicitudes del QR. Desde internet no hay forma de entrar al nodo.
- **Celular:** se comunica sólo con la API de la nube, también por HTTPS 443.
- **Base central:** está en una red privada sin IP pública y sólo acepta conexiones de la API por TCP 3306.
