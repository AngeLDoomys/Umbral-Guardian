# Protocolo de pruebas manuales — Umbral Guardian

Pruebas que necesitan la interfaz y las cámaras. Guarda cada pantallazo en
`tests/evidencias/` con el **nombre exacto** indicado (Windows: `Win + Shift + S`,
pegar en Paint y guardar como PNG). Si una prueba falla, toma igual el pantallazo
y anota qué pasó: un resultado fallido también es evidencia.

Anota fecha y hora de cada prueba en la tabla del final.

---

## Con cuenta de **administrador**

| ID | Pasos | El pantallazo debe mostrar | Archivo |
|---|---|---|---|
| PI-01 | Monitor → elegir una cámara en el panel 1 → Iniciar. | El video con el HUD (FPS, latencia, BD: OK). | `PI-01.png` |
| PI-02 | Iniciar la cámara que tiene fuente alta configurada. | La línea **"Canal alta res.: OK"** en el video. | `PI-02.png` |
| PI-03a | Iniciar una cámara distinta en cada panel. | Los dos videos funcionando a la vez. | `PI-03a.png` |
| PI-03b | Con el panel 1 corriendo, elegir **la misma cámara** en el panel 2 e Iniciar. | El aviso "ya se está monitoreando en el otro panel" en Eventos recientes. | `PI-03b.png` |
| PI-04a | Un residente enrolado (con consentimiento) se para frente a la cámara. | Recuadro verde con su nombre y unidad, y el evento "RESIDENTE" en Eventos recientes. | `PI-04a.png` |
| PI-04b | Ir a **Historial**. | El registro recién creado con fecha, hora, cámara y zona. | `PI-04b.png` |
| PI-05 | Una persona **no** enrolada frente a la cámara. | Recuadro naranja "NO RECONOCIDO". | `PI-05.png` |
| PI-06a | Vehículo con patente **registrada** de residente. | Recuadro verde con patente y unidad. | `PI-06a.png` |
| PI-06b | Vehículo con patente **no registrada**. | Recuadro naranja "NO REGISTRADO". | `PI-06b.png` |
| PI-06c | (Opcional) Registrar una visita con patente en **Visitas** y pasar ese vehículo. | Recuadro amarillo "VISITA". | `PI-06c.png` |
| PI-07a | Con un vehículo no registrado en pantalla: ir a **Vehículos** y registrar su patente **sin detener el Monitor**. | El formulario con el vehículo recién registrado. | `PI-07a.png` |
| PI-07b | Volver al Monitor y pasar de nuevo el vehículo (o esperar que salga y entre). | Ahora aparece como residente, **sin haber reiniciado** el programa. | `PI-07b.png` |
| PI-07c | **Configuración** → cambiar "Procesar cada N frames" → Guardar. | El mensaje "✅ Guardado y aplicado". | `PI-07c.png` |
| PI-11a | **Reportes** → generar el reporte por horario/zona → exportar PDF y abrirlo. | El PDF abierto. | `PI-11a.png` |
| PI-11b | Exportar el CSV y abrirlo en Excel. | El CSV abierto. | `PI-11b.png` |
| PI-12 | **Privacidad** → registrar una solicitud de acceso de un residente de prueba → exportar. | El archivo JSON exportado abierto (usa un residente de prueba, no uno real). | `PI-12.png` |

## Con cuenta de **conserje**

| ID | Pasos | El pantallazo debe mostrar | Archivo |
|---|---|---|---|
| PS-01a | Cerrar sesión e ingresar como conserje. | El menú lateral **sin** Cámaras, Reportes, Privacidad, Cuentas ni Configuración. | `PS-01a.png` |
| PS-01b | Ir a **Vehículos**. | La pantalla con los botones "Registrar vehículo" y "Eliminar" disponibles (hallazgo RN-04). | `PS-01b.png` |
| PS-01c | Ir a **Visitas**. | El RUT de las visitas enmascarado (`12.345.***-*`). | `PS-01c.png` |

## Rendimiento (dejar corriendo)

| ID | Pasos | El pantallazo debe mostrar | Archivo |
|---|---|---|---|
| PR-01a | Dos cámaras simultáneas durante **al menos 1 hora** en horario con tráfico. | El Monitor con los dos paneles y sus estadísticas al final de la hora. | `PR-01a.png` |
| PR-01b | En la consola donde corre `python main.py`. | El último bloque `[Latencia] ventana móvil (ms)` (con `deteccion` p95). | `PR-01b.png` |

---

## Registro de ejecución (completar)

| ID | Fecha | Hora | ¿Aprobada? | Observación |
|---|---|---|---|---|
| PI-01 | | | | |
| PI-02 | | | | |
| PI-03 | | | | |
| PI-04 | | | | |
| PI-05 | | | | |
| PI-06 | | | | |
| PI-07 | | | | |
| PI-11 | | | | |
| PI-12 | | | | |
| PS-01 | | | | |
| PR-01 | | | | |

Las pruebas de usuario con el conserje real (PA-01 a PA-06) y las mediciones de
precisión (PR-02, PR-03) se hacen en terreno durante la validación; se agregan al
informe cuando estén.
