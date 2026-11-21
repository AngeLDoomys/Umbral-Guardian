// Genera las secciones XI a XIII del informe de título de Umbral Guardian.
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType,
  ShadingType, AlignmentType, HeadingLevel, LevelFormat, BorderStyle, PageBreak, ImageRun,
} = require("docx");

const EVID = process.env.EVIDENCIAS;   // carpeta tests/evidencias del proyecto
let figuraN = 14; // el informe usa hasta la Figura 13 en los anexos

function figura(archivo, titulo, nota) {
  const buf = fs.readFileSync(`${EVID}/${archivo}`);
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);   // cabecera PNG
  const ancho = 600, alto = Math.round(h * ancho / w);
  const n = figuraN++;
  return [
    new Paragraph({ children: [new TextRun({ text: `Figura ${n}`, bold: true, font: FONT, size: 20 })],
      spacing: { before: 200, after: 0 }, keepNext: true }),
    new Paragraph({ children: [new TextRun({ text: titulo, italics: true, font: FONT, size: 20 })],
      spacing: { after: 80 }, keepNext: true }),
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true,
      children: [new ImageRun({ type: "png", data: buf, transformation: { width: ancho, height: alto } })] }),
    new Paragraph({ children: [new TextRun({ text: "Nota. ", italics: true, font: FONT, size: 18 }),
      new TextRun({ text: nota, font: FONT, size: 18 })], spacing: { after: 200 } }),
  ];
}

const NAVY = "1F3864";
const ALT = "EEF2F8";
const FONT = "Calibri";
const TABLE_W = 9360; // carta con márgenes de 1": 12240 - 2*1440

let tablaN = 25; // el informe usa hasta la Tabla 24 en los anexos

// ── helpers ────────────────────────────────────────────────────────────────

function runs(text, opts = {}) {
  // **negrita** dentro del texto
  return text.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map(part =>
    part.startsWith("**")
      ? new TextRun({ text: part.slice(2, -2), bold: true, font: FONT, size: opts.size || 22 })
      : new TextRun({ text: part, font: FONT, size: opts.size || 22, italics: opts.italics }));
}

const p = (text, opts = {}) => new Paragraph({
  children: runs(text, opts),
  alignment: opts.align || AlignmentType.JUSTIFIED,
  spacing: { after: 160, line: 276 },
});

const h1 = text => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  children: [new TextRun({ text, bold: true, font: FONT, size: 28, color: "000000" })],
  spacing: { before: 360, after: 200 },
});

const h2 = text => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  children: [new TextRun({ text, bold: true, font: FONT, size: 22, color: "000000" })],
  spacing: { before: 240, after: 120 },
});

const h3 = text => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  children: [new TextRun({ text, bold: true, font: FONT, size: 22, color: "000000" })],
  spacing: { before: 200, after: 100 },
});

const bullet = text => new Paragraph({
  numbering: { reference: "bullets", level: 0 },
  children: runs(text),
  alignment: AlignmentType.JUSTIFIED,
  spacing: { after: 80, line: 276 },
});

const num = (text, ref = "prerreq") => new Paragraph({
  numbering: { reference: ref, level: 0 },
  children: runs(text),
  alignment: AlignmentType.JUSTIFIED,
  spacing: { after: 80, line: 276 },
});

function caption(title) {
  const n = tablaN++;
  return [
    new Paragraph({
      children: [new TextRun({ text: `Tabla ${n}`, bold: true, font: FONT, size: 20 })],
      spacing: { before: 200, after: 0 }, keepNext: true,
    }),
    new Paragraph({
      children: [new TextRun({ text: title, italics: true, font: FONT, size: 20 })],
      spacing: { after: 80 }, keepNext: true,
    }),
  ];
}

const border = { style: BorderStyle.SINGLE, size: 4, color: "808080" };
const borders = { top: border, bottom: border, left: border, right: border };

function cell(text, width, { header = false, shade = null } = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    borders,
    shading: header
      ? { fill: NAVY, type: ShadingType.CLEAR, color: "auto" }
      : shade ? { fill: shade, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: String(text).split("\n").map(line => new Paragraph({
      children: header
        ? [new TextRun({ text: line, bold: true, color: "FFFFFF", font: FONT, size: 18 })]
        : runs(line, { size: 18 }),
      spacing: { after: 40 },
    })),
  });
}

function table(title, headers, widths, rows) {
  const total = widths.reduce((a, b) => a + b, 0);
  const scale = TABLE_W / total;
  const w = widths.map(x => Math.round(x * scale));
  w[w.length - 1] += TABLE_W - w.reduce((a, b) => a + b, 0);
  return [
    ...caption(title),
    new Table({
      width: { size: TABLE_W, type: WidthType.DXA },
      columnWidths: w,
      rows: [
        new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, w[i], { header: true })) }),
        ...rows.map((r, ri) => new TableRow({
          cantSplit: true,
          children: r.map((c, i) => cell(c, w[i], { shade: ri % 2 ? ALT : null })),
        })),
      ],
    }),
    new Paragraph({ children: [], spacing: { after: 120 } }),
  ];
}

// ── contenido ──────────────────────────────────────────────────────────────

const xi = [
  h1("XI.\tImplementación de los KPI y SLA"),
  p("Este punto traslada a la operación los niveles de servicio declarados como compromiso de diseño en el punto 4.2.4. Para cada indicador se describe cómo quedó implementada su medición dentro del propio sistema, de qué fuente se obtiene el dato y cuál es su estado al cierre de esta redacción. Se distinguen dos planos: los **KPI**, que son indicadores continuos del desempeño del producto en operación, y los **SLA**, que son los compromisos con umbral sobre los que se resuelve la aceptación del MVP. La medición formal de ambos se ejecuta en el paquete 1.5.2, «Pruebas de precisión, latencia y disponibilidad en condiciones reales», programado entre el 14 de septiembre y el 20 de noviembre de 2026. Al 17 de octubre de 2026 se cuenta con mediciones preliminares en banco, que se informan como tales."),
  p("La medición se apoya en una decisión de implementación que responde a la segunda recomendación técnica de las conclusiones de la Formulación: instrumentar el tiempo de inferencia de forma **permanente** y no sólo durante la ventana de validación. El motor de detección incorpora un medidor de latencias (clase LatencyMeter del módulo engine/security_engine.py) que registra, para cada etapa del procesamiento, una ventana móvil de las últimas 200 muestras y calcula su promedio, su percentil 95 y su máximo. Las etapas medidas son la lectura del fotograma, la detección completa, cada inferencia YOLO por separado, el seguimiento de vehículos, el reconocimiento facial, el OCR de patentes y el tiempo total desde que llega el fotograma hasta que se entrega a la interfaz. El resumen se imprime en la consola del nodo cada diez segundos y los valores principales se muestran de forma continua al conserje, sobre el video y bajo cada panel de cámara del Monitor."),

  h3("Ajustes técnicos respecto de la Formulación"),
  p("La fase de optimización (entregable 1.3) introdujo cinco cambios sobre la solución formulada, que inciden directamente en los indicadores de este punto y deben leerse en conjunto con el punto IX:"),
  bullet("**Reconocimiento facial:** se reemplazó VGG-Face por **ArcFace**, con el detector de rostros **YuNet** y alineación por los ojos, ambos a través de DeepFace. Se agregaron filtros de calidad (confianza mínima del detector de 0,75 y nitidez mínima medida como varianza del Laplaciano) y una **votación entre intentos**: un residente se confirma con dos coincidencias y clara mayoría, y tras cinco rostros válidos sin confirmar la persona se clasifica como no reconocida."),
  bullet("**Detección de personas y vehículos:** se adoptó **YOLO26** en su variante small en lugar de la nano. La medición en banco mostró margen suficiente de latencia en GPU, y la variante small es más precisa."),
  bullet("**Lectura de patentes:** el OCR genérico se reemplazó por **fast-plate-ocr**, un modelo entrenado específicamente para patentes. EasyOCR se mantiene como respaldo automático. Cada lectura exige formato chileno válido y una confianza mínima por carácter, y la patente se confirma por **votación** de al menos dos lecturas idénticas."),
  bullet("**Doble stream y dos cámaras simultáneas:** cada cámara puede operar con dos canales del grabador. La detección corre sobre el canal de baja resolución, y los recortes de rostros y patentes se toman del canal principal de alta resolución. El sistema monitorea **dos cámaras en paralelo**, cada una con su propio motor, conforme a la restricción R-02."),
  bullet("**Arquitectura de datos:** la nube conserva únicamente las cuentas de usuario y la licencia firmada del condominio. Los datos personales, las plantillas biométricas y el historial de accesos permanecen en la base de datos **local** del nodo de borde. Este cambio refuerza la minimización por diseño exigida por el art. 14 quáter."),

  h2("4.1\tDescripción de KPI."),
  p("La tabla siguiente define los indicadores de desempeño del producto, su fórmula, la fuente de la que el sistema los obtiene y la meta asociada. Las metas de los indicadores KPI-01, KPI-06, KPI-09 y KPI-10 son las de los SLA comprometidos. Las demás son metas internas que el equipo propone para orientar la operación y que no condicionan la aceptación."),
  ...table("Indicadores de desempeño del producto (KPI)",
    ["ID", "Indicador", "Definición o fórmula", "Fuente en el sistema", "Meta"],
    [700, 1500, 2700, 2400, 1300],
    [
      ["KPI-01", "Latencia de detección por fotograma", "Tiempo de las inferencias YOLO (personas, vehículos y patentes) de un fotograma procesado; se informa promedio y percentil 95.", "LatencyMeter, etapa «deteccion»; HUD y panel del Monitor.", "p95 < 100 ms (SLA-02)"],
      ["KPI-02", "Latencia total por fotograma", "Tiempo desde que el fotograma llega del flujo de video hasta que se entrega a la interfaz, con detecciones dibujadas.", "LatencyMeter, etapa «frame_total».", "< 50 ms promedio (meta interna)"],
      ["KPI-03", "Tasa de procesamiento por cámara", "Fotogramas procesados por segundo en cada panel, con las dos cámaras en operación simultánea.", "Contador del motor; panel del Monitor.", "≥ 10 FPS por cámara (meta interna)"],
      ["KPI-04", "Tiempo hasta identificación facial", "Espera en cola más reconocimiento, desde que se encola el rostro hasta conocer el resultado.", "LatencyMeter, etapa «rostro_total».", "< 2 s (HU-01)"],
      ["KPI-05", "Tiempo hasta lectura de patente", "Espera en cola más OCR, desde que se encola el vehículo hasta conocer la patente.", "LatencyMeter, etapa «ocr_total».", "< 2 s (meta interna)"],
      ["KPI-06", "Tasa de verdaderos positivos facial", "VP / (VP + FN) sobre el conjunto de validación de residentes enrolados.", "Protocolo PR-02 (punto XII).", "≥ 92% (SLA-01)"],
      ["KPI-07", "Tasa de falsos positivos facial", "Personas no registradas clasificadas como residentes / total de personas no registradas presentadas.", "Protocolo PR-02 (punto XII).", "0 en el conjunto de prueba (meta interna)"],
      ["KPI-08", "Tasa de lectura correcta de patentes", "Patentes confirmadas correctamente / vehículos con patente visible en el conjunto de prueba.", "Protocolo PR-03 (punto XII).", "≥ 90% (meta propuesta; EN-02 no fijó umbral)"],
      ["KPI-09", "Disponibilidad", "(Horas del horario operativo − horas sin servicio) / horas del horario operativo.", "Registro de operación del nodo (ver 6.1).", "≥ 95% (SLA-03)"],
      ["KPI-10", "Integridad del registro", "Eventos persistidos en la base de datos / eventos clasificados por el motor en el mismo intervalo.", "Contadores de sesión del motor contra las tablas de detecciones.", "100% (SLA-04)"],
      ["KPI-11", "Patentes sin confirmar", "Lecturas informadas como «SIN CONFIRMAR» / total de patentes informadas.", "Tabla de detecciones de vehículos.", "Indicador de seguimiento; sin umbral"],
    ]),

  h3("Mediciones preliminares en banco"),
  p("La tabla siguiente registra las primeras mediciones de los indicadores de latencia, tomadas en banco el 7 de octubre de 2026 en tres momentos de la misma jornada, siempre con **dos cámaras operando simultáneamente**, sobre un equipo con GPU NVIDIA GeForce GTX 1650 Ti (gama media). Las cámaras RTSP corresponden al grabador Hikvision del condominio; en la muestra B se usó además una cámara USB conectada al equipo. Los valores se leyeron del panel del Monitor (muestras B y C en las Figuras 17 y 18; la captura de la muestra A no se conservó) y corresponden a la ventana móvil vigente en ese momento: son muestras puntuales, no la medición formal del paquete 1.5.2."),
  ...table("Mediciones preliminares de latencia con dos cámaras simultáneas (7 de octubre de 2026)",
    ["Muestra", "Cámara", "Modo de captura", "FPS", "Latencia total por fotograma (KPI-02)", "Detección promedio (KPI-01)", "Detección p95 (KPI-01)"],
    [800, 1700, 1700, 700, 1500, 1400, 1300],
    [
      ["A", "Portón del condominio (RTSP)", "Un canal", "14,8", "17 ms", "81 ms", "88 ms"],
      ["A", "Conserjería (RTSP)", "Doble stream", "14,8", "10 ms", "47 ms", "50 ms"],
      ["B", "Entrada principal (cámara USB)", "Un canal", "19,7", "20 ms", "130 ms", "**126 ms**"],
      ["B", "Conserjería (RTSP)", "Doble stream", "11,8", "10 ms", "144 ms", "73 ms"],
      ["C", "Conserjería (RTSP)", "Doble stream", "15,1", "16 ms", "73 ms", "87 ms"],
      ["C", "Portón del condominio (RTSP)", "Un canal", "15,1", "16 ms", "76 ms", "86 ms"],
    ]),
  p("En las cinco lecturas de cámaras RTSP, el percentil 95 de la detección se mantuvo entre 50 y 88 ms, bajo el umbral de 100 ms del SLA-02, con dos cámaras en paralelo. La excepción es la **cámara USB de la muestra B, que operó a un solo canal en alta resolución y registró un p95 de 126 ms, por sobre el umbral**. El resultado no se omite: indica que el SLA-02 se sostiene con cámaras IP y doble stream, que es la configuración comprometida en RF-07, pero no con una cámara de un solo canal en alta resolución, por lo que la configuración de la fuente alta debe exigirse en las cámaras de acceso. La comparación de la muestra A confirma el beneficio del doble stream: detectar sobre el canal de baja resolución reduce la latencia de detección a cerca de la mitad (47 ms contra 81 ms), y los recortes para el reconocimiento se siguen tomando en alta resolución. En la muestra B, el promedio de Conserjería (144 ms) supera su p95 (73 ms), lo que sólo ocurre cuando unas pocas muestras son muy altas; esos picos aislados deben investigarse en la medición de una hora (PR-01). En la misma jornada se verificó el módulo de patentes sobre un vehículo real: el detector localizó la placa con confianza 0,75 dentro del vehículo detectado con confianza 0,80, y el OCR leyó la patente YC-47-33 con una confianza mínima por carácter de 99,9%."),

  h2("4.2\tDescripción de SLA."),
  p("La tabla siguiente describe, para cada nivel de servicio comprometido, los mecanismos del sistema que permiten alcanzarlo, el método con que se mide y su estado al 17 de octubre de 2026. La columna de estado se completará con el resultado de la medición formal del paquete 1.5.2 y se respaldará en el anexo «Plan de pruebas y evidencias»."),
  ...table("Implementación y estado de los niveles de servicio comprometidos",
    ["SLA", "Umbral", "Implementación en el sistema", "Método de medición", "Estado al 17-oct-2026"],
    [700, 900, 3100, 2300, 2000],
    [
      ["SLA-01 Precisión facial", "≥ 92%", "ArcFace con detector YuNet y alineación; filtros de calidad del rostro; umbral de distancia coseno 0,55 con margen mínimo de 0,08 frente al segundo candidato; votación entre intentos.", "Tasa de verdaderos positivos sobre un conjunto de validación no utilizado en el enrolamiento (PR-02).", "Pendiente de medición formal."],
      ["SLA-02 Latencia", "< 100 ms", "Inferencia en GPU (CUDA, FP16); doble stream; detección cada N fotogramas configurable; OCR y reconocimiento facial en hilos separados del flujo de video.", "Percentil 95 de la etapa de detección del LatencyMeter durante una jornada de operación (PR-01).", "Cumplido en banco con cámaras RTSP (p95 entre 50 y 88 ms); no cumplido con cámara USB de un canal (126 ms). Falta la confirmación en jornada completa."],
      ["SLA-03 Disponibilidad", "≥ 95%", "Reconexión automática de los flujos RTSP; respaldo al canal bajo si falla el canal alto; operación sin internet hasta siete días; cambios de configuración aplicados en caliente, sin reiniciar.", "Registro de operación continua del nodo durante la validación en terreno (PR-04).", "Instrumento pendiente: el sistema aún no registra su tiempo de servicio (ver 6.1)."],
      ["SLA-04 Integridad", "100%", "Cada clasificación de rostro o patente se persiste con cámara, zona, marca de tiempo, resultado y confianza; los errores de escritura quedan registrados en la consola.", "Comparación entre los contadores de la sesión y los registros en la base de datos del mismo intervalo (PR-05).", "Pendiente de medición formal."],
      ["SLA-05 Seguridad y Ley N.º 19.628", "100% de la lista", "Ver Tabla siguiente.", "Lista de verificación de la Tabla 19 y pruebas PS-01 a PS-05.", "Cumplimiento parcial; brechas identificadas."],
    ]),
  p("El SLA-05 agrupa controles de naturaleza distinta, por lo que su estado se desagrega a continuación. La tabla distingue lo que ya está implementado en el software, con la evidencia que lo respalda, de lo que permanece pendiente. Se declaran explícitamente las brechas para que su cierre se programe antes del acta de validación del 20 de noviembre de 2026."),
  ...table("Estado de los controles de seguridad y cumplimiento que componen el SLA-05",
    ["Control", "Estado", "Evidencia o acción pendiente"],
    [3000, 1500, 4860],
    [
      ["Control de acceso por roles (superadministrador, administrador, conserje)", "Implementado", "core/session.py; menú de vistas filtrado por rol en gui/app.py. Hallazgo: el perfil de conserjería puede registrar y editar residentes y registrar o eliminar vehículos, lo que contradice la regla RN-04. Debe ajustarse el código o la regla."],
      ["Contraseñas almacenadas sin texto plano", "Implementado", "PBKDF2-SHA256 con sal aleatoria y 260.000 iteraciones (core/security.py); política mínima de 8 caracteres con letras y números."],
      ["Licencia del condominio verificable", "Implementado", "Licencia firmada digitalmente por la nube y verificada con clave pública en el nodo (core/licencia.py)."],
      ["Minimización: video y biometría no salen del nodo", "Implementado", "La API central sólo recibe credenciales y entrega cuentas y licencia (core/cloud.py)."],
      ["No persistencia biométrica de personas no registradas (RNF-09)", "Implementado", "El evento «no reconocido» se registra sin plantilla ni imagen asociada."],
      ["Consentimiento con versión y revocación (RF-12)", "Implementado", "Registro con versión del formulario y medio; la revocación cierra el consentimiento y elimina las plantillas en una sola transacción."],
      ["Derechos del titular: acceso, portabilidad, supresión, bloqueo (RF-09 a RF-11)", "Implementado", "Vista «Privacidad»: registro de solicitudes, exportación en JSON, supresión con anonimización del historial y bloqueo temporal. Las plantillas bloqueadas dejan de usarse de inmediato."],
      ["Política de retención (V-13)", "Implementado", "Purga automática al iniciar sesión: detecciones con más de 90 días y visitas con más de 30 días (gui/login.py)."],
      ["Cifrado de las comunicaciones con HTTPS (V-09)", "Pendiente", "La API central opera en ambiente de desarrollo sobre HTTP. Se requiere desplegarla con TLS y configurar su URL con https en nodo.json."],
      ["Cifrado AES-256 en reposo (V-08)", "Pendiente", "No implementado en la base local. Alternativas: cifrado de tablespaces InnoDB de MySQL o BitLocker (XTS-AES 256) sobre el disco del nodo."],
      ["Despliegue de la nube en Amazon EC2 y RDS (EN-05)", "Pendiente", "La API y la base central corren hoy en el equipo de desarrollo. Al desplegar, verificar la región (V-15)."],
      ["Evaluación de impacto y política de tratamiento (V-06, V-07)", "Pendiente", "Entregables documentales; no dependen del software."],
    ]),
];

const xii = [
  h1("XII.\tPlan de Pruebas y Aseguramiento de Calidad."),
  p("El plan de pruebas verifica que cada requerimiento del punto III se cumpla con evidencia objetiva y que los niveles de servicio del punto XI se midan con un procedimiento repetible. Se organiza en cinco niveles: pruebas **unitarias** sobre las funciones del sistema que no dependen de cámaras ni de la base de datos; pruebas de **integración** entre cámaras, motor de detección, base de datos e interfaz; pruebas de **rendimiento** sobre los umbrales comprometidos; pruebas de **seguridad y cumplimiento**; y pruebas de **usuario** con el personal de conserjería y la administración, que culminan en la aceptación del cliente."),

  h2("1.1.\tPlan de Pruebas (unitarias, integrales, de usuario)."),
  h3("Organización de las pruebas"),
  bullet("**Entornos.** El banco de pruebas es el equipo de desarrollo con GPU NVIDIA GTX 1650 Ti, con MySQL local y conectado por RTSP a las cámaras del grabador del condominio. El entorno de terreno es el nodo de borde instalado en la portería. Las pruebas de rendimiento se ejecutan en ambos entornos, y sólo el resultado en terreno es válido para la aceptación."),
  bullet("**Responsables.** Conforme a la matriz RACI, el plan y protocolo de pruebas y las pruebas en condiciones reales están a cargo de Aníbal Farías Piedrabuena; la corrección de hallazgos, de Matías Tejada Carrizo; las pruebas de seguridad del entorno de nube, de Jan Ordenes Aldunate; y la aceptación, del stakeholder cliente."),
  bullet("**Herramientas.** Las pruebas unitarias se automatizan con **pytest** y se ejecutan antes de generar cada versión del ejecutable. Las pruebas de integración y de usuario se ejecutan manualmente con un protocolo escrito y quedan respaldadas con capturas de pantalla, el resumen de latencias de la consola y consultas a la base de datos."),
  bullet("**Criterio de entrada.** Una versión entra a pruebas de usuario sólo si aprueba la totalidad de las pruebas unitarias y de integración."),
  bullet("**Gestión de hallazgos.** Cada hallazgo se registra con su severidad: crítica, alta, media o baja. Un hallazgo crítico (por ejemplo, un falso positivo facial o un evento no persistido) bloquea el acta de validación hasta su corrección y nueva prueba. Los de severidad baja pueden quedar documentados como mejoras."),
  bullet("**Criterio de salida.** Todos los casos asociados a un requerimiento aprobados, los SLA dentro de umbral en la medición en terreno y ningún hallazgo crítico o alto abierto."),

  h3("Pruebas unitarias"),
  p("Las pruebas unitarias se concentran en la lógica que decide un resultado: validación de patentes y de RUT, votaciones, asociación entre placa y vehículo, seguridad de contraseñas y aplicación de la configuración. Los casos se implementaron con pytest en el archivo tests/test_unitarias.py del proyecto, que suma 58 verificaciones, y se ejecutan con el comando «py -m pytest -v tests»."),
  ...table("Casos de prueba unitarios",
    ["ID", "Componente", "Caso de prueba", "Resultado esperado"],
    [700, 2100, 3500, 3060],
    [
      ["PU-01", "core/plate_utils: validación y corrección de patentes", "Lecturas en formato nuevo (LLLL-NN) y antiguo (LL-NNNN); vocales en el formato nuevo; caracteres confundibles (0/O, 8/B, 2/Z).", "Acepta sólo formatos chilenos válidos; aplica la corrección según la posición; rechaza vocales en el formato nuevo."],
      ["PU-02", "core/security: RUT", "RUT válidos e inválidos, con dígito verificador K, con y sin puntos y guion.", "Valida el dígito verificador; normaliza; enmascara el RUT para el perfil de conserjería."],
      ["PU-03", "core/security: contraseñas", "Hash y verificación de una contraseña; contraseña incorrecta; mismo texto con dos sales.", "Verifica sólo la clave correcta; dos hashes de la misma clave son distintos; el hash no contiene la clave."],
      ["PU-04", "core/security: política de contraseñas", "Claves con menos de 8 caracteres, sólo letras o sólo números.", "Rechaza las claves débiles con un mensaje explicativo."],
      ["PU-05", "core/security: normalización de patentes", "Patentes con guiones, espacios y minúsculas.", "Produce la misma clave de búsqueda que el registro de vehículos."],
      ["PU-06", "LatencyMeter", "Muestras conocidas en una etapa; ventana llena; acceso concurrente.", "Promedio, p95 y máximo correctos; conserva sólo las últimas 200 muestras."],
      ["PU-07", "get_car", "Placa dentro, fuera y en el borde de vehículos rastreados.", "Asocia la placa sólo al vehículo que la contiene."],
      ["PU-08", "Votación de patentes", "Lecturas idénticas, lecturas en conflicto y seis lecturas sin consenso.", "Confirma con dos lecturas idénticas y mayoritarias; tras seis sin consenso informa «SIN CONFIRMAR»."],
      ["PU-09", "Votación facial", "Secuencias de coincidencias y no coincidencias para una misma persona.", "Confirma con dos coincidencias y mayoría de 2 a 1; tras cinco intentos sin confirmar clasifica como no reconocido."],
      ["PU-10", "_scale_box (doble stream)", "Recuadros con distintos márgenes y en los bordes de la imagen.", "Lleva el recuadro al canal alto con su margen, sin salir de la imagen."],
      ["PU-11", "core/events y base de datos", "Escrituras de residentes, vehículos, visitas y consentimientos.", "Cada escritura incrementa la versión de datos; el motor recarga sin esperar la recarga periódica."],
      ["PU-12", "config.reload", "Cambiar un parámetro y restaurar los valores por defecto.", "Los valores vuelven a los de config.py y se aplica settings.json; las rutas de modelos se resuelven a la carpeta del programa."],
    ]),

  h3("Pruebas de integración"),
  ...table("Casos de prueba de integración",
    ["ID", "Integración verificada", "Procedimiento", "Resultado esperado"],
    [700, 2000, 3400, 3260],
    [
      ["PI-01", "Cámara RTSP → motor → interfaz", "Iniciar una cámara desde el Monitor.", "Video con detecciones superpuestas e indicadores de FPS, latencia y estado de la base de datos."],
      ["PI-02", "Doble stream", "Configurar la fuente alta de una cámara; luego desconectar el canal alto.", "Indicador «Canal alta res.: OK»; al fallar el canal alto, el sistema continúa con el canal bajo y lo informa en pantalla."],
      ["PI-03", "Dos cámaras simultáneas", "Iniciar una cámara en cada panel; intentar abrir la misma cámara en ambos.", "Ambos paneles operan en paralelo con su propio registro de eventos; se impide duplicar una cámara."],
      ["PI-04", "Rostro de residente → registro", "Presentar a un residente enrolado con consentimiento vigente.", "Clasificación «residente» con nombre y unidad, y registro en la tabla de detecciones de rostro con cámara, zona, hora y confianza."],
      ["PI-05", "Persona no registrada → registro sin biometría", "Presentar a una persona no enrolada.", "Clasificación «no reconocido»; evento registrado; la tabla de plantillas faciales no cambia."],
      ["PI-06", "Patente → registro", "Presentar vehículos de residente, de visita activa y no registrado.", "Estados «residente», «visita» y «no registrado» correctos, con registro en la tabla de detecciones de vehículo."],
      ["PI-07", "Cambios en caliente", "Durante el monitoreo: registrar un vehículo, editar la fuente de una cámara y cambiar un umbral en Configuración.", "El vehículo se reconoce sin reiniciar; sólo se reinicia el panel de la cámara editada; el umbral rige desde el siguiente fotograma."],
      ["PI-08", "Bloqueo y revocación", "Bloquear a un residente y revocar el consentimiento de otro mientras se monitorea.", "Ambos dejan de ser reconocidos de inmediato; la revocación elimina sus plantillas."],
      ["PI-09", "Inicio de sesión híbrido", "Iniciar sesión con y sin internet; simular más de siete días sin sincronizar; alterar la licencia.", "Ingresa sin internet dentro del plazo; se rechaza tras siete días y con la licencia alterada."],
      ["PI-10", "Retención", "Cargar detecciones de más de 90 días y visitas de más de 30, e iniciar sesión.", "Los registros vencidos se eliminan y la consola informa la cantidad."],
      ["PI-11", "Reportes", "Generar reportes de tráfico por horario y por zona.", "Archivos PDF y CSV con los datos del período solicitado."],
      ["PI-12", "Derechos del titular", "Registrar y atender solicitudes de acceso, portabilidad y supresión.", "Exportación en JSON; supresión con anonimización del historial; solicitud cerrada con constancia."],
      ["PI-13", "Reconexión", "Cortar la red de una cámara durante el monitoreo y restablecerla.", "El panel recupera el video sin intervención del operador."],
    ]),

  h3("Pruebas de rendimiento y de seguridad"),
  ...table("Casos de prueba de rendimiento y de seguridad",
    ["ID", "Objetivo", "Procedimiento", "Criterio de aprobación"],
    [700, 1900, 3800, 2960],
    [
      ["PR-01", "Latencia (SLA-02, RNF-02, RNF-06)", "Dos cámaras simultáneas durante al menos una hora en horario de tráfico; registrar el resumen del LatencyMeter.", "p95 de la etapa de detección < 100 ms en ambas cámaras, en el nodo de borde definitivo."],
      ["PR-02", "Precisión facial (SLA-01, RNF-01)", "Conjunto de validación con residentes enrolados y personas no registradas, capturado en condiciones de iluminación estándar y en sesiones distintas a la del enrolamiento.", "Tasa de verdaderos positivos ≥ 92% y ningún falso positivo."],
      ["PR-03", "Lectura de patentes (EN-02)", "Conjunto de vehículos con patente visible en el acceso, con la patente real anotada.", "Tasa de lectura correcta ≥ 90%; las lecturas sin confirmar se informan por separado."],
      ["PR-04", "Disponibilidad (SLA-03, RNF-03)", "Operación continua durante la validación en terreno, con registro del tiempo de servicio.", "≥ 95% del horario operativo."],
      ["PR-05", "Integridad (SLA-04, RNF-07)", "Comparar los eventos clasificados por el motor con los registros de la base de datos en el mismo intervalo.", "100% de los eventos persistidos con marca de tiempo y zona."],
      ["PR-06", "Operación nocturna (exploratoria)", "Repetir PR-02 y PR-03 de noche.", "Sin umbral comprometido; el resultado alimenta los desafíos futuros declarados en la Formulación."],
      ["PS-01", "Control por roles (RN-04)", "Iniciar sesión como conserje e intentar acceder a Cámaras, Reportes, Privacidad, Cuentas y Configuración, y dar de alta o baja residentes y vehículos.", "Sólo dispone de las funciones de su perfil."],
      ["PS-02", "Almacenamiento de contraseñas", "Inspeccionar la tabla de cuentas en la base de datos.", "Sólo existen hashes PBKDF2 con sal; ninguna clave en texto plano."],
      ["PS-03", "Cifrado en tránsito (V-09)", "Inspeccionar el tráfico entre el nodo y la API desplegada.", "Toda comunicación ocurre sobre HTTPS con certificado válido."],
      ["PS-04", "Cifrado en reposo (V-08)", "Verificar el cifrado de la base local.", "Datos ilegibles sin la clave."],
      ["PS-05", "Minimización hacia la nube (RNF-05, RNF-09)", "Capturar las solicitudes que el nodo envía a la API durante una jornada.", "Ninguna contiene video, imágenes, plantillas ni datos de residentes."],
    ]),

  h3("Pruebas de usuario y de aceptación"),
  ...table("Casos de prueba de usuario y de aceptación",
    ["ID", "Usuario", "Escenario", "Criterio de aprobación"],
    [700, 1400, 4100, 3160],
    [
      ["PA-01", "Conserje sin experiencia previa en el sistema", "Tras una única sesión de capacitación, operar un turno: iniciar y detener cámaras, interpretar el semáforo, registrar una visita y consultar el historial.", "Completa las tareas sin asistencia, sin consola y sin editar archivos (RNF-08, HU-05)."],
      ["PA-02", "Administrador", "Registrar un residente con su consentimiento, enrolar su rostro, registrar su vehículo y dar de baja a otro residente.", "Completa el flujo sin asistencia técnica y sin reentrenar modelos (HU-06)."],
      ["PA-03", "Administrador", "Reconstruir los accesos de un día y de una persona determinada.", "Obtiene los eventos en menos de un minuto de trabajo (HU-07)."],
      ["PA-04", "Administrador", "Generar y exportar el reporte de tráfico de un mes por horario y por zona.", "Reporte PDF y CSV correcto (HU-08)."],
      ["PA-05", "Administrador ante un titular", "Atender una solicitud de copia, una de supresión y una de bloqueo.", "Atención dentro de los plazos de 30 días corridos y 2 días hábiles, con constancia (RNF-10)."],
      ["PA-06", "Stakeholder cliente", "Revisar los resultados de PR-01 a PR-05 y la operación en terreno.", "Firma del acta de validación y aceptación del MVP (paquete 1.5.4)."],
    ]),

  h3("Resultados de la ejecución al 17 de octubre de 2026"),
  p("La ejecución del plan comenzó en banco con los niveles que no requieren la presencia del equipo en el condominio: las pruebas unitarias y las de integración con la base de datos. Las de integración se ejecutan sobre una base temporal creada con el mismo esquema de la base local (sql/local.sql) y eliminada al terminar, de modo que nunca modifican los datos reales del condominio; la única excepción es PS-02, que sólo **lee** la tabla de cuentas de la base real. Se agregan las capturas del Monitor tomadas por el equipo el 7 de octubre de 2026. Las pruebas de interfaz restantes, las de rendimiento en jornada completa y las de usuario se ejecutarán en el condominio durante la validación (paquete 1.5.2)."),
  ...table("Resultado de la ejecución de las pruebas al 17 de octubre de 2026",
    ["Prueba", "Fecha", "Verificaciones", "Resultado", "Evidencia"],
    [2600, 1100, 1300, 2560, 1800],
    [
      ["PU-01 a PU-05 (patentes, RUT, contraseñas)", "17-10-2026", "36", "Aprobadas 36 de 36", "Figura 14"],
      ["PU-06 a PU-12 (latencias, votaciones, doble stream, configuración)", "17-10-2026", "22", "Aprobadas 22 de 22", "Figura 15"],
      ["PI-04/05, PI-06, PI-08, PI-10, PI-12, PR-05 y PS-02 (base de datos)", "17-10-2026", "13", "Aprobadas 13 de 13", "Figura 16"],
      ["PI-01, PI-02, PI-03a y PI-04a (Monitor)", "07-10-2026", "—", "Aprobadas", "Figuras 17 y 18"],
      ["PR-01 (muestras puntuales)", "07-10-2026", "6 lecturas", "5 de 6 bajo 100 ms; la cámara USB de un canal superó el umbral", "Tabla 26"],
      ["PI-05 a PI-07, PI-09, PI-11 a PI-13, PS-01, PS-03 a PS-05, PR-01 a PR-04, PA-01 a PA-06", "—", "—", "Pendientes de ejecución en el condominio", "—"],
    ]),
  p("**Incidencia registrada durante la ejecución.** En la primera ejecución de las pruebas unitarias falló un caso de la votación facial (PU-09). El análisis mostró que el error estaba en el diseño del caso y no en el sistema: con los votos 5, 6 y 5, la regla de mayoría de 2 a 1 confirma correctamente al residente en el tercer intento, y el caso esperaba que no decidiera hasta el cuarto. Se corrigió el caso y se agregó uno nuevo que verifica la ausencia de mayoría (dos votos frente a dos coincidencias con otros residentes); en la ejecución siguiente se aprobaron los 58 casos."),
  ...figura("PU-01a05.png", "Ejecución de las pruebas unitarias PU-01 a PU-05",
    "Captura de la consola del equipo de pruebas el 17 de octubre de 2026: 36 verificaciones aprobadas. Elaboración propia."),
  ...figura("PU-06a12.png", "Ejecución de las pruebas unitarias PU-06 a PU-12",
    "Captura de la consola del equipo de pruebas el 17 de octubre de 2026: 22 verificaciones aprobadas. Elaboración propia."),
  ...figura("PI-BD_integracion.png", "Ejecución de las pruebas de integración con la base de datos",
    "Captura de la consola del equipo de pruebas el 17 de octubre de 2026: 13 verificaciones aprobadas sobre una base temporal; PS-02 sobre la tabla de cuentas de la base real, en modo de sólo lectura. Elaboración propia."),
  ...figura("PI-04a_PI-02_residente_reconocido.png", "Monitor con dos cámaras: residente reconocido y canal de alta resolución activo",
    "Captura del 7 de octubre de 2026. Cámara 1: residente enrolado reconocido, con recuadro verde, nombre y unidad (PI-04a). Cámara 2: Conserjería con doble stream e indicador «Canal alta res.: OK» (PI-02). Ambas en operación simultánea (PI-03a). El residente reconocido es integrante del equipo de proyecto. Elaboración propia."),
  ...figura("PI-03a_dos_camaras.png", "Monitor con dos cámaras RTSP del condominio en operación simultánea",
    "Captura del 7 de octubre de 2026. Conserjería y Portón del condominio en paralelo, con latencia de detección p95 de 87 y 86 ms (muestra C de la Tabla 26). Elaboración propia."),

  h2("1.2.\tNormas y Estándares utilizados."),
  p("El aseguramiento de calidad se ajusta al marco normativo chileno aplicable al proyecto. Los criterios de aceptación de cada prueba se derivan de los requerimientos del punto III y de las obligaciones legales identificadas en la Formulación. El proyecto no declara la conformidad ni la certificación con normas internacionales de calidad o de pruebas de software."),
  ...table("Marco normativo aplicado al aseguramiento de calidad",
    ["Norma", "Aplicación en el plan de pruebas"],
    [3000, 6360],
    [
      ["Ley N.º 19.628, modificada por la Ley N.º 21.719", "La lista de verificación de la Tabla 19 se ejecuta como prueba de cumplimiento: cada ítem V-01 a V-17 requiere evidencia (PS-05, PI-05, PI-08, PI-10, PI-12, PA-05)."],
      ["Ley N.º 19.223 sobre delitos informáticos", "Fundamenta las pruebas de control de acceso y de protección de los datos almacenados (PS-01 a PS-04)."],
      ["Ley N.º 21.442 sobre copropiedad inmobiliaria", "Verificación de la autorización de la administración del condominio para instalar el sistema y tratar datos en espacios comunes (V-17)."],
      ["NIST FIPS 197 — Advanced Encryption Standard", "Referencia técnica del algoritmo AES-256 exigido por RNF-04; criterio de aceptación de PS-04."],
    ]),

  h2("1.3.\tMatriz de trazabilidad entre requerimientos y pruebas"),
  p("La matriz vincula cada requerimiento del punto III con los casos que lo verifican, de modo que ningún requerimiento quede sin prueba asignada. Amplía la matriz del anexo «Detalle Levantamiento de Requerimientos» con el identificador del caso de prueba, conforme se anticipó en ese anexo. El resultado de cada ejecución se registra en el libro de cálculo de trazabilidad."),
  ...table("Matriz de trazabilidad entre requerimientos y casos de prueba",
    ["Requerimiento", "Casos de prueba", "Niveles", "Estado al 17-10-2026"],
    [1500, 2100, 1900, 3860],
    [
      ["RF-01 Reconocimiento facial", "PU-09, PI-04, PI-05, PR-02", "Unitaria, integración, rendimiento", "PU-09 y PI-04 aprobadas; PI-05 aprobada en base de datos, falta su captura en el Monitor; PR-02 pendiente."],
      ["RF-02 Lectura de patentes", "PU-01, PU-05, PU-07, PU-08, PI-06, PR-03", "Unitaria, integración, rendimiento", "Unitarias aprobadas; PI-06 aprobada en base de datos, falta en el Monitor con un vehículo; PR-03 pendiente."],
      ["RF-03 Motor de decisión", "PI-04, PI-06", "Integración", "No implementado: cada módulo clasifica su evento por separado; la combinación de rostro y patente en una única decisión no existe."],
      ["RF-04 Registro de detecciones", "PI-04, PI-06, PR-05", "Integración, rendimiento", "Aprobadas en banco."],
      ["RF-05 Interfaz de conserjería", "PI-01, PI-03, PA-01, PA-03", "Integración, usuario", "PI-01 y PI-03a aprobadas; PI-03b y pruebas de usuario pendientes."],
      ["RF-06 Reportes PDF y CSV", "PI-11, PA-04", "Integración, usuario", "Pendientes."],
      ["RF-07 Cámaras IP sin intervenir el grabador", "PI-01, PI-02, PI-13", "Integración", "PI-01 y PI-02 aprobadas; PI-13 pendiente."],
      ["RF-08 Gestión de residentes y vehículos", "PI-07, PA-02, PS-01", "Integración, usuario, seguridad", "Pendientes. Hallazgo de roles abierto (Tabla 28)."],
      ["RF-09 Exportación de datos del titular", "PI-12, PA-05", "Integración, usuario", "PI-12 aprobada en base de datos; PA-05 pendiente."],
      ["RF-10 Supresión verificable", "PI-12, PA-05", "Integración, usuario", "PI-12 aprobada en base de datos; PA-05 pendiente."],
      ["RF-11 Bloqueo temporal", "PI-08, PA-05", "Integración, usuario", "PI-08 aprobada; PA-05 pendiente."],
      ["RF-12 Evidencia del consentimiento", "PI-08, PA-02", "Integración, usuario", "PI-08 aprobada; PA-02 pendiente."],
      ["RNF-01 Precisión ≥ 92%", "PR-02", "Rendimiento", "Pendiente."],
      ["RNF-02 Latencia < 100 ms", "PU-06, PR-01", "Unitaria, rendimiento", "PU-06 aprobada. Muestras de PR-01: se cumple con cámaras RTSP, no con la cámara USB de un canal. Falta la jornada de una hora."],
      ["RNF-03 Disponibilidad ≥ 95%", "PI-09, PI-13, PR-04", "Integración, rendimiento", "Pendiente; requiere el registro de operación descrito en 6.1."],
      ["RNF-04 HTTPS, AES-256 y roles", "PU-03, PS-01, PS-02, PS-03, PS-04", "Unitaria, seguridad", "PU-03 y PS-02 aprobadas; PS-01 pendiente; HTTPS y AES-256 sin implementar."],
      ["RNF-05 Cumplimiento normativo", "PS-05, lista V-01 a V-17", "Seguridad y cumplimiento", "Pendiente."],
      ["RNF-06 Hardware de costo acotado", "PR-01", "Rendimiento", "Muestras sobre GPU de gama media (GTX 1650 Ti)."],
      ["RNF-07 Integridad del registro", "PR-05", "Rendimiento", "Aprobada en banco; falta la medición en terreno."],
      ["RNF-08 Usabilidad", "PA-01", "Usuario", "Pendiente."],
      ["RNF-09 Minimización biométrica", "PI-05, PS-05", "Integración, seguridad", "PI-05 aprobada en base de datos; PS-05 pendiente."],
      ["RNF-10 Plazos de atención", "PA-05", "Usuario", "Pendiente."],
    ]),
];

const xiii = [
  h1("XIII.\tPlan de Implementación"),
  p("El plan de implementación define cómo la solución, una vez instalada en la portería (entregable 1.4), se mantiene disponible, se recupera ante una falla y se conserva en buen estado durante su operación. Se construye sobre dos condiciones del cliente declaradas en la Formulación: el condominio no tiene personal técnico (R-10) y el MVP no incluye soporte posterior a la entrega (punto 4.1.2). Por eso cada mecanismo privilegia lo automático sobre lo manual, y las tareas que sí requieren intervención humana se describen con su frecuencia y su responsable, para que la comunidad pueda dimensionarlas y contratarlas."),
  p("Antes de la transferencia operativa deben cumplirse tres **prerrequisitos de puesta en producción**:"),
  num("**Generar un ejecutable actualizado.** El ejecutable disponible es anterior a la arquitectura actual (base local, nube e inicio de sesión), por lo que debe reconstruirse con la versión vigente del código."),
  num("**Consolidar las dependencias en un único archivo con versiones fijas.** Los cuatro archivos actuales se contradicen entre sí. Además, uno de ellos incluye un paquete cuyo nombre imita al conector oficial de MySQL (mysql-conector-python, con una sola «n»), que debe eliminarse y verificarse que no esté instalado en el nodo."),
  num("**Cerrar las brechas de seguridad del SLA-05:** cifrado en reposo, HTTPS y despliegue de la nube."),

  h2("6.1\tGestión de Disponibilidad."),
  p("El objetivo es sostener una disponibilidad igual o superior al 95% del horario operativo (SLA-03). Si el horario operativo es continuo, de 24 horas, el umbral equivale a un máximo de 36 horas sin servicio en un mes de 30 días. El horario operativo debe acordarse formalmente con la administración, porque es el denominador del indicador. La disponibilidad se sostiene con mecanismos que el sistema ya incorpora y se complementa con medidas de instalación que se recomiendan para el nodo de borde."),
  ...table("Mecanismos de disponibilidad del nodo de borde",
    ["Causa de indisponibilidad", "Mecanismo implementado en el sistema", "Medida complementaria recomendada"],
    [2200, 3800, 3360],
    [
      ["Corte del flujo de una cámara", "Reconexión automática de los flujos RTSP; con doble stream, si cae el canal alto el sistema continúa con el canal bajo e informa «SIN SEÑAL» en pantalla.", "Conexión cableada de cámaras y grabador; nada de enlaces inalámbricos en el camino del video."],
      ["Caída del enlace a internet", "Operación local completa: detección, registro e interfaz no dependen de la nube. Inicio de sesión sin conexión hasta siete días; sincronización cada seis horas.", "Ninguna; el diseño la absorbe."],
      ["Falla o ausencia de la GPU", "Respaldo automático a CPU (core/gpu.py), con mayor latencia.", "Monitorear la latencia: un aumento brusco indica una falla de la GPU o de su controlador."],
      ["Cambios de configuración", "Cámaras, parámetros, modelos y datos de residentes se aplican en caliente, sin reiniciar el programa.", "—"],
      ["Corte de energía", "—", "UPS para el nodo, el grabador y el switch, con autonomía de al menos 30 minutos; arranque automático de Windows, MySQL y la aplicación al volver la energía."],
      ["Cierre o falla de la aplicación", "Indicadores de estado visibles para el conserje: base de datos, FPS y canal alto.", "Tarea programada de Windows que reinicie la aplicación si no está en ejecución."],
    ]),
  p("**Instrumento de medición.** Para medir el SLA-03 el sistema debe registrar su propio tiempo de servicio. Se propone que el motor escriba cada minuto un registro de latido con la marca de tiempo y el estado de cada cámara y de la base de datos. La disponibilidad del período se calcula a partir de los intervalos sin latido. Este registro **no existe aún** en el código y es condición para ejecutar la prueba PR-04."),

  h2("6.2\tGestión de Continuidad Operativa."),
  p("La continuidad descansa en un principio establecido desde la Formulación: la **degradación segura** (RN-07). El sistema apoya al conserje y no sustituye su decisión, por lo que ante cualquier falla mayor la portería vuelve al procedimiento manual de control de acceso, sin quedar bloqueada. Los objetivos de recuperación se definen sobre ese respaldo: el tiempo máximo para restablecer el servicio (RTO) y la pérdida máxima aceptable de registros (RPO)."),
  ...table("Escenarios de continuidad, respuesta y objetivos de recuperación",
    ["Escenario", "Respuesta", "RTO", "RPO"],
    [2000, 4960, 1200, 1200],
    [
      ["Falla de una cámara", "La otra cámara continúa operando; el conserje usa el grabador para el acceso afectado; se reemplaza o repara la cámara.", "Reconexión automática; 1 día hábil si hay reemplazo", "0"],
      ["Caída prolongada de internet", "Sin efecto sobre la operación. Si supera siete días, se bloquea el inicio de sesión hasta reconectar.", "No aplica", "0"],
      ["Falla del equipo de borde (hardware o disco)", "Procedimiento manual en portería. Instalación del ejecutable en un equipo de reemplazo, configuración del nodo (nodo.json, clave pública de la licencia y settings.json) y restauración del último respaldo manual mensual de la base local. Las cuentas y la licencia se recuperan al sincronizar con la base central en la nube.", "1 día hábil", "Hasta 1 mes"],
      ["Corrupción de la base de datos local", "Restauración del último respaldo manual mensual.", "4 h", "Hasta 1 mes"],
      ["Corte de energía", "La UPS cubre los cortes breves; en cortes prolongados, procedimiento manual y arranque automático al volver la energía.", "15 min tras volver la energía", "0"],
      ["Brecha de seguridad en el nodo", "Procedimiento de notificación descrito a continuación.", "Según el alcance", "Según el alcance"],
    ]),
  h3("Respaldo manual mensual"),
  p("El sistema no automatiza los respaldos. La continuidad de los datos se resguarda con un **respaldo manual mensual**, que ejecuta el responsable de soporte o la administración con el siguiente procedimiento:"),
  bullet("**Contenido:** exportación completa de la base local umbral_local, que contiene residentes, consentimientos, plantillas faciales, vehículos, visitas, cámaras e historial de accesos. La base central, con las cuentas y la licencia, opera en la nube y no forma parte de este respaldo."),
  bullet("**Ubicación:** la copia se guarda fuera del equipo de borde. Una copia en el mismo disco no protege ante la falla de ese disco."),
  bullet("**Protección:** el respaldo contiene datos personales y plantillas biométricas, que son datos sensibles. Queda bajo custodia de la administración, con acceso restringido y la misma finalidad de control de acceso declarada en la política de tratamiento."),
  bullet("**Retención:** se conservan sólo los tres últimos respaldos, alrededor de 90 días, y se eliminan los anteriores. Así una copia antigua no mantiene datos que la política de retención ya debió suprimir."),
  bullet("**Registro:** cada respaldo se anota con su fecha y el nombre de quien lo ejecutó. En la primera ejecución se verifica que el archivo pueda restaurarse."),
  p("La consecuencia de que el respaldo sea mensual es que, ante una falla del disco o de la base, se pierden los datos registrados desde el último respaldo, hasta un mes de historial y los enrolamientos posteriores (RPO de la tabla anterior)."),
  h3("Procedimiento ante una brecha de seguridad (art. 14 sexies)"),
  num("**Contención:** desconectar el nodo de la red, cambiar las contraseñas de las cuentas y de la base de datos, y revocar la clave del nodo en la nube.", "brecha"),
  num("**Evaluación:** determinar qué datos se expusieron, en especial si incluyen plantillas biométricas, que son datos sensibles.", "brecha"),
  num("**Notificación:** informar a la Agencia de Protección de Datos Personales sin dilaciones indebidas y, tratándose de datos sensibles, comunicar también a los titulares afectados. La notificación corresponde al condominio como responsable del tratamiento, con el apoyo del encargado.", "brecha"),
  num("**Recuperación y registro:** corregir la causa, restablecer la operación y dejar constancia escrita del incidente y de las medidas adoptadas.", "brecha"),

  h2("6.3\tPlan de Mantención Técnica."),
  p("La mantención se organiza en tres tipos: preventiva, correctiva y evolutiva. Las tareas que no requieren conocimiento técnico quedan a cargo de la administración del condominio. Las técnicas quedan a cargo del proveedor de soporte que la comunidad contrate una vez cerrado el proyecto, porque el MVP no incluye soporte posterior a la entrega."),
  ...table("Plan de mantención técnica",
    ["Tipo", "Actividad", "Frecuencia", "Responsable"],
    [1100, 5060, 1500, 1700],
    [
      ["Preventiva", "Revisar el resumen de latencias y FPS, y el registro de disponibilidad.", "Semanal", "Proveedor de soporte (remoto)"],
      ["Preventiva", "Revisar altas y bajas de residentes, vigencia de consentimientos y bloqueos (RN-09).", "Mensual", "Administración"],
      ["Preventiva", "Verificar que la purga de retención se esté aplicando.", "Mensual", "Proveedor de soporte"],
      ["Preventiva", "Actualizaciones de Windows y del controlador de la GPU, en una ventana fuera de horario punta y con prueba de latencia posterior (PR-01).", "Mensual", "Proveedor de soporte"],
      ["Preventiva", "Respaldo manual de la base local y eliminación de las copias con más de 90 días.", "Mensual", "Proveedor de soporte o administración"],
      ["Preventiva", "Limpieza física del equipo y revisión de la ventilación y de la UPS.", "Trimestral", "Proveedor de soporte"],
      ["Preventiva", "Revisar vulnerabilidades de las dependencias (por ejemplo, con pip-audit) y actualizar las versiones fijadas.", "Semestral", "Proveedor de soporte"],
      ["Preventiva", "Recalibrar los umbrales de reconocimiento ante cambios de iluminación estacionales, repitiendo PR-02 y PR-03.", "Semestral", "Proveedor de soporte"],
      ["Correctiva", "Atender las fallas reportadas por conserjería, registrarlas como incidente y distribuir la corrección como una nueva versión del ejecutable.", "A demanda", "Proveedor de soporte"],
      ["Evolutiva", "Actualizar modelos de detección u OCR, siempre con validación previa en banco (PR-01 a PR-03) antes de instalar en terreno.", "Según necesidad", "Proveedor de soporte"],
      ["Evolutiva", "Cambiar el modelo de reconocimiento facial. Las plantillas se guardan por modelo: el cambio obliga a volver a enrolar a todos los residentes.", "Excepcional", "Proveedor de soporte y administración"],
    ]),
  p("**Control de versiones.** Cada versión entregada al condominio se identifica con un número de versión y un registro de cambios. Se genera con el archivo único de dependencias y aprueba las pruebas unitarias y de integración antes de instalarse. La actualización conserva los archivos de configuración del nodo (settings.json y nodo.json) y la base local, de modo que cambiar de versión no obliga a reconfigurar las cámaras ni a volver a enrolar a los residentes."),
];

// ── pendientes (nota de trabajo, no forma parte del informe) ───────────────

const aviso = text => new Paragraph({
  children: [new TextRun({ text, bold: true, color: "C00000", font: FONT, size: 22 })],
  shading: { fill: "FFF2CC", type: ShadingType.CLEAR, color: "auto" },
  spacing: { after: 160 },
});

const check = text => new Paragraph({
  numbering: { reference: "checks", level: 0 },
  children: runs(text),
  spacing: { after: 60, line: 264 },
});

const pendientes = [
  h1("PENDIENTES — nota de trabajo"),
  aviso("Esta página no forma parte del informe: ELIMINARLA antes de entregar. Lista de lo que falta para completar los puntos XI a XIII, al 17 de octubre de 2026."),
  p("Para retomar, pedirle a Claude: «completemos el punto XII con las pruebas del condominio» y adjuntar los pantallazos con su fecha. Seguir el protocolo del archivo tests/PROTOCOLO_PRUEBAS_MANUALES.md del proyecto y guardar las capturas en tests/evidencias/ con el nombre que allí se indica."),

  h3("Pruebas a ejecutar en el condominio (con pantallazo)"),
  check("**PI-05:** persona no registrada frente a la cámara; esperar a que pase de «Analizando…» a «NO RECONOCIDO»."),
  check("**PI-06a y PI-06b:** vehículo con patente registrada de residente (recuadro verde) y vehículo con patente no registrada («NO REGISTRADO»). Opcional PI-06c: patente de visita."),
  check("**PI-07a, b y c:** registrar una patente sin detener el Monitor y ver que pasa a residente; cambiar un parámetro en Configuración y ver «Guardado y aplicado»."),
  check("**PI-03b:** elegir la misma cámara en los dos paneles y capturar el aviso."),
  check("**PI-11a y PI-11b:** reporte por horario y zona abierto en PDF y en CSV."),
  check("**PI-12:** exportación JSON de un residente de prueba desde la vista Privacidad."),
  check("**PS-01a, b y c:** con la cuenta de conserje: menú lateral, pantalla Vehículos (botón Eliminar) y RUT enmascarado en Visitas."),
  check("**PR-01:** dos cámaras RTSP durante al menos una hora en horario con tráfico; capturar el Monitor y el último bloque «[Latencia]» de la consola. Revisar los picos de latencia vistos en la muestra B."),
  check("**PI-09 y PI-13 (opcionales):** inicio de sesión sin internet y reconexión tras desconectar una cámara."),

  h3("Pruebas de validación en terreno (paquete 1.5.2)"),
  check("**PR-02:** precisión facial con un conjunto de validación (residentes enrolados y personas no registradas, en sesiones distintas al enrolamiento). Meta: ≥ 92% y ningún falso positivo."),
  check("**PR-03:** lectura de patentes sobre vehículos reales con la patente anotada. Meta propuesta: ≥ 90%."),
  check("**PR-04:** disponibilidad durante la validación (requiere antes el registro de operación del punto 6.1)."),
  check("**PR-05 en terreno:** comparar los eventos del motor con los registros de la base en una jornada."),
  check("**PA-01 a PA-06:** pruebas con el conserje y el administrador, y firma del acta de validación."),
  check("**PS-03 a PS-05:** HTTPS, cifrado en reposo y tráfico hacia la nube sin datos personales (después de implementarlos)."),

  h3("Desarrollo pendiente que condiciona los SLA"),
  check("Registro de disponibilidad (latido cada minuto) para medir el SLA-03."),
  check("HTTPS y despliegue de la API en AWS (EC2 y RDS), verificando la región."),
  check("Cifrado AES-256 de la base local (InnoDB o BitLocker)."),
  check("Resolver el hallazgo de roles (RN-04): el conserje puede registrar residentes y registrar o eliminar vehículos."),
  check("Decidir sobre RF-03 (combinación de rostro y patente): implementarlo o justificar su ajuste de alcance."),
  check("Configurar la fuente alta (doble stream) en todas las cámaras de acceso: la cámara de un canal superó los 100 ms."),
  check("Ejecutable actualizado, archivo único de dependencias y eliminar el paquete mysql-conector-python."),
  check("Respaldo manual mensual: definir quién lo ejecuta y dónde se guarda la copia fuera del equipo, y hacer el primero con prueba de restauración."),

  h3("Ajustes del informe"),
  check("Renumerar tablas (25 a 38) y figuras (14 a 18) según cómo quede la Segunda Parte."),
  check("Revisar que los puntos IX y X describan la misma solución (ArcFace, YOLO26 small, fast-plate-ocr, nube sólo con cuentas y licencias)."),
  check("Acordar con la administración el horario operativo, base del cálculo de disponibilidad."),
  check("Actualizar la Tabla 33 (resultados), la matriz de trazabilidad y los estados de los SLA con los resultados del condominio."),
];

// ── documento ──────────────────────────────────────────────────────────────

const doc = new Document({
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: FONT, color: "000000" }, paragraph: { outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: FONT, color: "000000" }, paragraph: { outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: FONT, color: "000000" }, paragraph: { outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "checks", levels: [{ level: 0, format: LevelFormat.BULLET, text: "☐", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      ...["prerreq", "brecha"].map(ref => ({ reference: ref, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.",
        alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] })),
    ],
  },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 },
      margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    children: [
      ...(process.env.MODO === "pendientes" ? pendientes : [
        ...xi, new Paragraph({ children: [new PageBreak()] }),
        ...xii, new Paragraph({ children: [new PageBreak()] }),
        ...xiii]),
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  const out = process.argv[2] || "Secciones_XI_XIII_UmbralGuardian.docx";
  fs.writeFileSync(out, buf);
  console.log("OK", out, `(tablas ${25} a ${tablaN - 1})`);
});
