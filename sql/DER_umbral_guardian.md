# Modelo de datos (DER) — Umbral Guardian

Arquitectura híbrida borde–nube con **dos bases de datos**, ambas en 3FN:

| Base | Dónde vive | Qué contiene | Script |
|---|---|---|---|
| `umbral_central` | Nube (RDS), solo la API accede | Clientes, planes, suscripciones, pagos, cuentas, nodos | `sql/central.sql` |
| `umbral_local` | PC de la portería de cada condominio | Residentes, consentimientos, plantillas faciales, vehículos, visitas, cámaras, detecciones, solicitudes | `sql/local.sql` |

Los datos personales y biométricos **nunca salen del condominio** (art. 14 quáter).
Para exportar como imagen: pegar cada bloque en https://mermaid.live o usar MySQL
Workbench → Database → Reverse Engineer sobre cada base.

## 1. Base central (plano de control)

```mermaid
erDiagram
    PLAN ||--o{ SUSCRIPCION : "se contrata en"
    CONDOMINIO ||--o{ SUSCRIPCION : "contrata"
    SUSCRIPCION ||--o{ PAGO : "se paga con"
    CONDOMINIO ||--o{ CUENTA : "tiene"
    ROL ||--o{ CUENTA : "define permisos de"
    CONDOMINIO ||--o{ NODO : "tiene instalado"

    PLAN {
        int idplan PK
        varchar nombre UK
        int precio_mensual
        tinyint max_camaras
        bool activo
    }
    CONDOMINIO {
        int idcondominio PK
        varchar rut UK
        varchar nombre
        varchar direccion
        varchar comuna
        varchar email_contacto
        varchar telefono
        datetime fecha_registro
    }
    SUSCRIPCION {
        int idsuscripcion PK
        int idcondominio FK
        int idplan FK
        date fecha_inicio
        date fecha_fin
        enum estado
    }
    PAGO {
        int idpago PK
        int idsuscripcion FK
        date fecha_pago
        int monto
        tinyint meses
        enum medio
        varchar referencia
    }
    ROL {
        tinyint idrol PK
        varchar nombre UK
    }
    CUENTA {
        int idcuenta PK
        int idcondominio FK
        tinyint idrol FK
        varchar rut
        varchar nombres
        varchar apellidos
        varchar email UK
        varchar password_hash
        bool activa
        datetime fecha_creacion
        datetime ultimo_acceso
    }
    NODO {
        int idnodo PK
        int idcondominio FK
        varchar nombre
        char clave_hash UK
        datetime fecha_alta
        datetime ultimo_contacto
        bool activo
    }
```

## 2. Base local de cada condominio (plano de datos)

```mermaid
erDiagram
    UNIDAD ||--o{ RESIDENTE : "habitada por"
    TIPO_RESIDENTE ||--o{ RESIDENTE : "clasifica"
    RESIDENTE ||--o{ CONSENTIMIENTO : "otorga"
    RESIDENTE |o--o{ CONSENTIMIENTO : "autoriza como tutor"
    CUENTA_LOCAL |o--o{ CONSENTIMIENTO : "registra"
    RESIDENTE ||--o{ PLANTILLA_FACIAL : "tiene"
    UNIDAD ||--o{ VEHICULO : "tiene autorizado"
    VISITANTE ||--o{ VISITA : "realiza"
    UNIDAD ||--o{ VISITA : "recibe"
    CUENTA_LOCAL |o--o{ VISITA : "registra"
    ZONA ||--o{ CAMARA : "es vigilada por"
    CAMARA ||--o{ DETECCION_ROSTRO : "genera"
    RESIDENTE |o--o{ DETECCION_ROSTRO : "es reconocido en"
    CAMARA ||--o{ DETECCION_VEHICULO : "genera"
    VEHICULO |o--o{ DETECCION_VEHICULO : "es leído en"
    VISITA |o--o{ DETECCION_VEHICULO : "es leída en"
    RESIDENTE |o--o{ SOLICITUD_DERECHO : "presenta"
    CUENTA_LOCAL |o--o{ SOLICITUD_DERECHO : "gestiona"

    CUENTA_LOCAL {
        int idcuenta PK "mismo id que en la nube"
        enum rol
        varchar rut
        varchar nombres
        varchar apellidos
        varchar email UK
        varchar password_hash
        bool activa
        datetime sincronizada_en
    }
    LICENCIA {
        tinyint idlicencia PK "fila única"
        text contenido "JSON firmado"
        varchar firma "Ed25519"
        datetime verificada_en
    }
    UNIDAD {
        int idunidad PK
        varchar codigo UK
    }
    TIPO_RESIDENTE {
        tinyint idtipo_residente PK
        varchar nombre UK
    }
    RESIDENTE {
        int idresidente PK
        int idunidad FK
        tinyint idtipo_residente FK
        varchar rut UK
        varchar nombres
        varchar apellidos
        date fecha_nacimiento
        varchar telefono
        varchar email
        datetime fecha_alta
        bool tratamiento_bloqueado
    }
    CONSENTIMIENTO {
        int idconsentimiento PK
        int idresidente FK
        int idrepresentante FK
        int idcuenta_registro FK
        varchar version_formulario
        enum medio
        datetime fecha_otorgamiento
        datetime fecha_revocacion
    }
    PLANTILLA_FACIAL {
        int idplantilla PK
        int idresidente FK
        blob embedding
        varchar modelo
        datetime fecha_captura
    }
    VEHICULO {
        int idvehiculo PK
        int idunidad FK
        varchar patente UK
        enum tipo
        varchar marca
        varchar modelo
        varchar color
        datetime fecha_registro
    }
    VISITANTE {
        int idvisitante PK
        varchar rut UK
        varchar nombres
        varchar apellidos
    }
    VISITA {
        int idvisita PK
        int idvisitante FK
        int idunidad FK
        int idcuenta_registro FK
        varchar patente
        datetime fecha_ingreso
        datetime fecha_salida
    }
    ZONA {
        int idzona PK
        varchar nombre UK
    }
    CAMARA {
        int idcamara PK
        int idzona FK
        varchar nombre
        enum tipo_fuente
        varchar fuente
        smallint ancho
        smallint alto
        tinyint fps
        bool activa
    }
    DETECCION_ROSTRO {
        bigint iddeteccion PK
        int idcamara FK
        int idresidente FK
        datetime fecha_hora
        enum resultado
        decimal confianza
    }
    DETECCION_VEHICULO {
        bigint iddeteccion PK
        int idcamara FK
        int idvehiculo FK
        int idvisita FK
        datetime fecha_hora
        varchar patente_leida
        enum resultado
        decimal confianza
    }
    SOLICITUD_DERECHO {
        int idsolicitud PK
        int idresidente FK
        int idcuenta_gestion FK
        varchar rut_titular
        enum tipo
        datetime fecha_solicitud
        enum estado
        datetime fecha_respuesta
        varchar observacion
    }
```

## Cómo se relacionan las dos bases

Las claves foráneas no pueden cruzar de una base a otra; el vínculo es lógico:

- Cada nodo se identifica ante la API con su **clave de nodo** (en la nube solo se guarda su hash en `NODO`). Así la API sabe a qué condominio pertenece el equipo.
- `CUENTA_LOCAL` es una **réplica** de las cuentas de `CUENTA` de ese condominio, con el mismo `idcuenta`. Se actualiza en cada sincronización y permite iniciar sesión sin internet.
- `LICENCIA` guarda el último estado de la suscripción **firmado** por la API (Ed25519). El nodo la verifica con la clave pública y no puede modificarla.
- Por ser una base de un solo condominio, las tablas locales no llevan `idcondominio`.

## Decisiones de normalización

| Decisión | Motivo |
|---|---|
| Separar base central y base local | Los datos biométricos y el historial no salen del condominio (art. 14 quáter; se evita la transferencia internacional de datos sensibles, arts. 27–28). La nube solo administra identidades y suscripciones. |
| `CUENTA` (quien opera el sistema) separada de `RESIDENTE` (titular reconocido) | Son entidades distintas: el residente no inicia sesión y la cuenta no es titular biométrico. |
| `UNIDAD` como entidad propia | Evita repetir el texto del departamento en residentes, vehículos y visitas (3FN). |
| `VEHICULO` depende de `UNIDAD` y no del residente | Los residentes rotan; la unidad permanece. |
| `VISITANTE` separado de `VISITA` | El nombre depende del RUT, no de cada ingreso (3FN). |
| Una sola tabla `PLANTILLA_FACIAL`, sin foto | Se eliminó la duplicación de vectores y no se almacena la imagen (minimización, art. 3 c). |
| Patente guardada sin guiones | La versión "sin guion" era un dato derivado. |
| Tutor como FK a `RESIDENTE` | Evita guardar nombre y RUT del tutor dentro del consentimiento. |
| `resultado` en las detecciones | Registra el resultado al momento del evento y se conserva cuando el residente se suprime y el evento queda anonimizado. |
| `rut_titular` en `SOLICITUD_DERECHO` | Constancia de la solicitud (art. 11) que sobrevive a la supresión del titular. |
| `CUENTA_LOCAL` y `LICENCIA` | Réplicas controladas de la nube para operar sin conexión; no son fuente de verdad. |
