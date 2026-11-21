titulo: Anexo 9 · Manual de usuario
subtitulo: Guía de uso para conserjes, administradores, residentes y visitas
encabezado: Umbral Guardian · Anexo 9 · Manual de usuario
archivo: Anexo_9_Manual_de_usuario.docx

## 1. Presentación

Umbral Guardian es el sistema de control de accesos del condominio. Observa las cámaras de la portería y avisa al conserje cuando llega un residente, una visita autorizada o una persona que el sistema no reconoce. También lee las patentes de los vehículos y deja un registro de cada acceso.

El sistema **no abre puertas ni portones**: ayuda al conserje a decidir, y la decisión sigue siendo de una persona.

Este manual explica cómo usarlo según el papel de cada persona. Cada sección se puede leer por separado.

> Las imágenes de este manual usan datos de ejemplo: los nombres, RUT y patentes son ficticios. En las capturas tomadas en el condominio, los rostros y las patentes están difuminados.

### 1.1 Quién usa el sistema y qué puede hacer

| Persona | Cómo accede | Qué puede hacer |
|---|---|---|
| **Conserje** | Programa en el PC de la portería | Ver las cámaras, atender avisos, registrar visitas y vehículos, generar invitaciones y consultar el historial |
| **Administrador** | Programa en el PC de la portería | Todo lo del conserje, más registrar residentes con su rostro, configurar cámaras, exportar reportes, atender derechos de privacidad, administrar cuentas y ajustar la configuración |
| **Residente o visita** | Su celular, con el enlace o QR que le entrega el condominio | Registrar sus datos, aceptar el consentimiento y tomar las fotos de su rostro |
| **Proveedor** | Programa con su cuenta propia | Administrar condominios clientes, planes y pagos. Se describe en el Anexo 6 |

### 1.2 Cómo se ven los avisos en las cámaras

| Color del recuadro | Significado | Qué hacer |
|---|---|---|
| **Verde**, con nombre y unidad | Residente reconocido | Verificar visualmente y permitir el acceso según el reglamento |
| **Amarillo**, con «VISITA» | Visita autorizada para hoy, o visita frecuente | Registrar su ingreso en Registro móvil → Visitas autorizadas |
| **Naranja**, «NO RECONOCIDO» | Persona sin registro, o rostro que no coincide | Atender como una visita normal: pedir carnet y registrar |
| **Gris**, «Analizando…» | El sistema todavía no decide | Esperar unos segundos; la persona debe mirar hacia la cámara |
| **Naranja**, patente «NO REGISTRADO» | Vehículo sin registro en el condominio | Consultar destino y registrar como visita |

> El sistema puede equivocarse, sobre todo con poca luz, de perfil o con una persona muy parecida a un residente. Ante cualquier duda, el conserje debe pedir identificación.

## 2. Primeros pasos

### 2.1 Iniciar sesión

1. Abra Umbral Guardian en el PC de la portería.
2. Escriba su **correo** y su **contraseña**, y pulse **Ingresar**.
3. Si su contraseña es temporal, el programa le pedirá cambiarla antes de entrar. La nueva debe cumplir las reglas que muestra la ventana.

![Ventana de inicio de sesión](capturas/00_inicio_sesion.png)

**Sin internet:** si no hay conexión, el programa avisa «No hay conexión con la nube» y permite entrar con la última copia de las cuentas, hasta por 7 días. Las cámaras, residentes y patentes siguen funcionando. La gestión de cuentas y el registro desde el celular necesitan internet.

![Programa funcionando sin conexión a internet: arriba se indica «SIN CONEXIÓN»](capturas/real_sin_conexion.png)

### 2.2 La pantalla principal

- **Arriba:** el nombre del condominio, el plan y la fecha de pago; el estado de conexión (**EN LÍNEA** o **SIN CONEXIÓN**); su nombre y rol; y los botones **Mi contraseña** y **Cerrar sesión**.
- **A la izquierda:** el menú. Cada persona ve solo las opciones de su rol.
- **Al centro:** la pantalla elegida.

![Pantalla principal del administrador, con todas las opciones del menú](capturas/admin_01_monitor.png)

![Menú del conserje: no incluye Cámaras, Reportes, Privacidad, Cuentas ni Configuración](capturas/conserje_01_monitor.png)

### 2.3 Cambiar su contraseña y cerrar sesión

- **Mi contraseña:** pide la contraseña actual y la nueva. Requiere internet.
- **Cerrar sesión:** detiene las cámaras y vuelve a la ventana de inicio. Ciérrela al terminar su turno.

===

## 3. Manual del conserje

### 3.1 Monitor: ver las cámaras

1. En **Cámara 1** y **Cámara 2**, elija la cámara de cada panel.
2. Pulse **▶ Iniciar** en cada uno.
3. Use **⛶** para ver un panel en pantalla completa. Para salir, haga doble clic o presione **Esc**.
4. **Pausa** congela el video sin cerrar la cámara.

En **Eventos recientes**, a la derecha, aparece cada aviso con la hora, la cámara y el resultado. Bajo cada video se muestran los cuadros por segundo (FPS), la demora de la detección y los contadores del turno.

![Monitor en el condominio: residente reconocido en verde, con su nombre y unidad](capturas/real_residente_reconocido.png)

![Persona no registrada, marcada en naranja como «NO RECONOCIDO»](capturas/real_no_reconocido.png)

![Vehículo con patente no registrada (patente difuminada)](capturas/real_patente_no_registrada.png)

**Avisos que puede ver:**

- **«ya se está monitoreando en el otro panel»:** eligió la misma cámara en los dos paneles. Elija otra.
- **«canal alta res. sin señal»:** la cámara sigue funcionando con menor calidad. Avise al administrador si se mantiene.
- Si una cámara pierde la conexión, el sistema la recupera solo al volver la red, sin que deba pulsar nada.

### 3.2 Visitas: registrar ingreso y salida

Use esta pantalla para las visitas que llegan sin registro previo.

1. Escriba el **RUT**, **nombres** y **apellidos**. Si viene en auto, escriba la **patente**.
2. Elija la **unidad de destino** y pulse **Registrar visita**.
3. Cuando la visita se retire, selecciónela en la lista y pulse **Marcar salida**.

La casilla **Solo dentro del condominio** muestra solo las visitas que aún no salen. Para proteger su privacidad, el RUT de las visitas se muestra parcialmente oculto (por ejemplo, `20.675.***-*`). Estos datos no incluyen el rostro y se eliminan a los 30 días.

![Registro de visitas](capturas/conserje_02_visits.png)

### 3.3 Registro móvil: invitar a una visita o a un residente

Con esta pantalla se genera un código QR para que la persona se registre desde su propio celular.

1. Elija el tipo de invitación:
   - **Residente nuevo:** una persona que vivirá en el condominio.
   - **Solo rostro:** un residente ya registrado que debe agregar su rostro.
   - **Visita:** marque **Visita frecuente** si viene seguido (por ejemplo, una asesora del hogar).
2. Elija la **unidad** y, si corresponde, el **residente**.
3. Elija la **vigencia** del enlace y pulse **Generar QR**.
4. Se abre una ventana con el QR. La persona lo escanea con su celular, o usted pulsa **Copiar enlace (WhatsApp)** y se lo envía.

![Pantalla Registro móvil, con las solicitudes por revisar a la derecha](capturas/admin_04_registro.png)

![Ventana del QR: el enlace sirve una sola vez y vence según la vigencia elegida](capturas/admin_registro_qr.png)

**Revisar las solicitudes que llegan**

Las solicitudes aparecen en **Solicitudes por revisar**. El programa revisa la nube cada minuto; para hacerlo de inmediato, pulse **Revisar nuevos**.

- **Ver detalle:** muestra los datos enviados.
- **Aprobar:** confirme primero la identidad de la persona con su carnet. Al aprobar, la cámara empieza a reconocerla.
- **Rechazar:** puede indicar el motivo.

**Visitas autorizadas**

Pulse **Visitas autorizadas** para ver las visitas aprobadas. Cuando una de ellas llega, selecciónela y pulse **Registrar ingreso**. **Revocar** elimina la autorización junto con su rostro.

![Visitas autorizadas: una frecuente y una para el día de hoy](capturas/admin_registro_autorizadas.png)

> Las visitas ocasionales se borran solas, con su rostro, al día siguiente de su visita. Las frecuentes se mantienen hasta que se revocan.

### 3.4 Residentes y vehículos

En **Residentes**, el conserje puede buscar a un residente y revisar si tiene consentimiento vigente y rostro registrado. En **Vehículos** puede registrar la patente de un residente, elegir su unidad y su tipo, o eliminarla.

![Vehículos autorizados del condominio (patentes ficticias)](capturas/conserje_05_vehicles.png)

### 3.5 Historial

En **Historial → Detecciones** se ven los accesos más recientes primero. Use **Todos**, **Personas** o **Vehículos** para filtrar y **Actualizar** para refrescar.

La pestaña **Búsqueda por foto** permite cargar la foto de una persona para saber si es un residente con consentimiento vigente.

![Historial de accesos con datos de ejemplo](capturas/admin_07_history.png)

===

## 4. Manual del administrador

El administrador ve todo lo anterior y además las opciones de esta sección.

### 4.1 Registrar un residente en la portería

1. En **Residentes**, complete el formulario **Nuevo residente** y pulse **Guardar**. La fecha de nacimiento solo se usa para saber si es menor de 16 años.
2. Seleccione al residente en la lista y pulse **Consentimiento**. Lea o entregue la información al titular, elija el **medio** (escrito, digital o verbal), marque la casilla y pulse **Registrar consentimiento**. Si es menor de 16 años, debe indicar al **tutor** que autoriza.
3. Pulse **Capturar rostro**. Encienda la cámara del equipo y tome 5 capturas, cambiando un poco la pose entre una y otra. El sistema rechaza una captura borrosa o demasiado parecida a la anterior.

![Residentes del condominio con su estado de consentimiento y rostro (datos ficticios)](capturas/admin_03_residents.png)

![Consentimiento para el tratamiento biométrico](capturas/admin_residentes_consentimiento.png)

- **Editar** sirve para corregir datos (rectificación).
- **Dar de baja** elimina al residente con su rostro y su consentimiento. El historial de accesos queda anonimizado.

> Sin consentimiento vigente, el sistema no usa el rostro de esa persona. Quien no consiente ingresa por el procedimiento normal de conserjería.

### 4.2 Cámaras

En **Cámaras** se agregan, editan, prueban y eliminan las cámaras. Cada cámara tiene un **nombre**, una **zona**, una **fuente** de video (canal de baja resolución) y, opcionalmente, una **fuente alta** (canal principal, que mejora la lectura de rostros y patentes). El botón **Probar** comprueba que la cámara responda. El plan contratado limita la cantidad de cámaras.

![Cámaras configuradas (las direcciones se muestran sin contraseña)](capturas/admin_06_cameras.png)

### 4.3 Reportes

1. Elija el período: **Hoy**, **Esta semana**, **Este mes** o **Personalizado**.
2. En la tarjeta del reporte, pulse **CSV** (para Excel) o **PDF**.

Reportes disponibles: accesos peatonales, accesos vehiculares, tráfico por zona y horario, resumen general y residentes.

![Pantalla de reportes con las estadísticas del período](capturas/admin_08_reports.png)

![Reporte de tráfico por zona y horario en PDF](capturas/real_reporte_pdf.png)

> Los «accesos peatonales» del reporte son **eventos de reconocimiento**, no personas distintas: una misma persona puede generar varios eventos.

### 4.4 Privacidad: derechos de los titulares

Cuando un residente pide ejercer un derecho sobre sus datos:

1. Elija al **titular** y el **derecho**, y pulse **Registrar solicitud**.
2. Seleccione la solicitud y pulse **Ejecutar y cerrar**, o **Rechazar (fundado)** indicando la causa.

| Derecho | Qué hace el sistema |
|---|---|
| Acceso o portabilidad | Entrega un archivo con los datos del titular, sin los vectores faciales |
| Rectificación | Se corrigen los datos en Residentes → Editar |
| Supresión | Elimina al titular y anonimiza su historial |
| Oposición | Detiene el reconocimiento facial y borra su rostro |
| Bloqueo temporal | Suspende el reconocimiento sin borrar datos; se levanta con **Levantar bloqueo** |

El plazo de respuesta es de 30 días corridos, y de 2 días hábiles para el bloqueo. Las solicitudes vencidas se marcan en rojo.

![Solicitudes de derechos de los titulares (datos ficticios)](capturas/admin_09_privacy.png)

### 4.5 Cuentas

En **Cuentas** se crean las cuentas de conserjes y administradores. La contraseña inicial es temporal: la persona debe cambiarla al entrar. **Activar / desactivar** bloquea o habilita una cuenta, y **Restablecer contraseña** genera una nueva contraseña temporal. Arriba se muestra el plan y la fecha de pago. Esta pantalla necesita internet.

![Cuentas del condominio y estado de la suscripción](capturas/admin_10_accounts.png)

### 4.6 Configuración

Esta pantalla ajusta el funcionamiento técnico. Los cambios se aplican sin reiniciar el programa al pulsar **Guardar en settings.json**.

![Configuración del sistema](capturas/admin_11_settings.png)

Ajustes de uso habitual:

- **Retención:** días que se guarda el historial de accesos (90) y los datos de visitas (30).
- **Reglamento: las visitas registran su rostro:** si está marcado, toda visita invitada por QR debe aceptar el consentimiento y registrar su rostro.
- **Vista de cámaras:** datos técnicos sobre el video y ampliación del último rostro.

> No cambie los umbrales de reconocimiento sin asesoría técnica: fueron calibrados con pruebas. Un umbral más alto acepta a más personas desconocidas. **Restaurar defaults** vuelve a los valores originales.

===

## 5. Guía para residentes y visitas

Esta guía es para quien recibe una invitación del condominio. No necesita instalar ninguna aplicación: basta con el navegador del celular.

### 5.1 Pasos para registrarse

1. **Abra el enlace o escanee el QR** que le entregó la administración o la portería. El enlace sirve **una sola vez** y vence en el plazo indicado.
2. **Complete sus datos.** Si es residente, puede agregar su vehículo.
3. **Lea el consentimiento.** Explica para qué se usa su rostro, por cuánto tiempo y cuáles son sus derechos. Si está de acuerdo, marque la casilla y pulse **Continuar**.
4. **Tome las 5 fotos de su rostro**, una por cada pose indicada, sin lentes de sol ni gorro y con buena luz. Cada foto se revisa al instante: si sale borrosa o sin rostro, se le pedirá repetirla.
5. Pulse **Enviar registro**. El condominio revisará su solicitud y, al aprobarla, la cámara de la portería lo reconocerá.

![Paso 1: datos del residente](capturas/celular_1_datos_residente.png)

![Paso 2: consentimiento](capturas/celular_2_consentimiento.png)

![Paso 3: fotos del rostro, una por pose](capturas/celular_3_fotos.png)

![Registro enviado](capturas/celular_5_listo.png)

**Si es una visita**, el formulario pide nombre, RUT, fecha de la visita y, si viene en auto, su patente. Las visitas frecuentes no indican fecha.

![Formulario para visitas](capturas/celular_4_visita.png)

### 5.2 Qué pasa con su información

- **Su foto no se guarda.** Se procesa en el momento para obtener un vector numérico y luego se descarta.
- El vector viaja **cifrado** hasta el equipo de la portería del condominio, el único que puede leerlo.
- Las cámaras analizan el video **dentro del condominio**: el monitoreo no envía imágenes, rostros ni patentes a internet.
- Una visita ocasional se borra al día siguiente de su visita; una frecuente, cuando se revoca la autorización.
- Puede pedir en la administración el **acceso** a sus datos, su **corrección**, su **eliminación**, la **oposición** al reconocimiento o el **bloqueo** temporal.
- Los menores de 16 años se registran en la administración, con su madre, padre o tutor.

## 6. Preguntas frecuentes y problemas comunes

| Situación | Qué hacer |
|---|---|
| La cámara no me reconoce | Mire de frente a la cámara unos segundos, sin gorro ni lentes de sol. Si se repite, pida a la administración que registre de nuevo su rostro con la cámara del condominio |
| Un residente aparece como «NO RECONOCIDO» | Puede estar de perfil o con poca luz: el sistema vuelve a revisar cada 2 segundos. Verifique su identidad de la forma habitual |
| El enlace del registro dice «no disponible» | Ya se usó o venció. Pida uno nuevo a la administración |
| El programa dice «SIN CONEXIÓN» | Las cámaras siguen funcionando. Avise al administrador si se mantiene: sin internet no funcionan las cuentas ni el registro desde el celular |
| Una cámara muestra «Sin señal» | Pulse **Iniciar**. Si no vuelve, revise que el grabador y la red estén encendidos y avise al administrador |
| Las fechas del historial o de los reportes no coinciden con la hora real | El PC debe tener la hora sincronizada automáticamente con internet. Avise al administrador |

## 7. Glosario

| Término | Significado |
|---|---|
| Consentimiento | Autorización expresa del titular para usar su rostro con la finalidad descrita |
| Vector facial | Serie de números que representa un rostro; no permite reconstruir la foto |
| Visita frecuente | Visita autorizada sin fecha de término, hasta que se revoque |
| Evento | Cada vez que el sistema registra un reconocimiento o una patente |
| Canal alto y canal bajo | Dos calidades de video de una misma cámara: el bajo para detectar y el alto para leer rostros y patentes |
| Retención | Tiempo que se guardan los datos antes de borrarse automáticamente |
