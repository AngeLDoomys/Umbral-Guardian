# -*- coding: utf-8 -*-
"""
servidor/api.py - API central de Umbral Guardian (se despliega en la nube, EC2).

Es el único componente con acceso a la base central. Los nodos de los
condominios se comunican con ella por HTTPS para:
  - iniciar sesión y verificar la suscripción,
  - sincronizar cuentas y recibir la licencia firmada.
El proveedor (superadmin) la usa para administrar condominios y pagos.
Ningún dato personal de residentes ni dato biométrico pasa por aquí.

Ejecutar (desarrollo):  python -m servidor.api
Producción: detrás de un servidor WSGI (waitress/gunicorn) con HTTPS.
"""

import hashlib
import os
import secrets
import sys
from datetime import date, datetime, timedelta
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from mysql.connector import Error as MySQLError

from core import licencia
from core.security import (format_rut, password_problem, temporary_password, valid_rut,
                           verify_password)
from servidor import config_servidor as cfg
from servidor.central_db import CentralDB

app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024   # fotos del registro desde el celular

from servidor.registro_movil import bp as _registro_movil  # noqa: E402
app.register_blueprint(_registro_movil)

_esquema_revisado = False


@app.before_request
def _asegurar_esquema():
    """Bases centrales creadas antes de agregar columnas nuevas: se actualizan solas."""
    global _esquema_revisado
    if not _esquema_revisado:
        with CentralDB() as db:
            db.asegurar_esquema()
        _esquema_revisado = True


def _serializer():
    with open(cfg.SECRET_FILE, encoding="utf-8") as f:
        return URLSafeTimedSerializer(f.read().strip(), salt="ug-sesion")


def _error(msg, status):
    return jsonify({"error": msg}), status


def hash_clave_nodo(clave: str) -> str:
    return hashlib.sha256(clave.encode()).hexdigest()


def nueva_clave_nodo() -> str:
    return "ugn_" + secrets.token_urlsafe(32)


# ─────────────────────────────────────────────────────────────────────────────
# Licencia
# ─────────────────────────────────────────────────────────────────────────────

def _licencia(db: CentralDB, idcondominio: int) -> dict:
    susc = db.suscripcion_vigente(idcondominio)
    datos = {
        "idcondominio": idcondominio,
        "condominio": susc["condominio"] if susc else "",
        "plan": susc["plan"] if susc else "",
        "max_camaras": susc["max_camaras"] if susc else 0,
        "fecha_fin": susc["fecha_fin"].isoformat() if susc else None,
        "estado": susc["estado"] if susc else "sin_suscripcion",
        "dias_gracia": cfg.DIAS_GRACIA_SUSCRIPCION,
        "emitida": datetime.now().isoformat(timespec="seconds"),
    }
    return licencia.firmar(datos, cfg.PRIVATE_KEY_FILE)


def _problema_suscripcion(db: CentralDB, idcondominio: int):
    susc = db.suscripcion_vigente(idcondominio)
    if not susc or susc["estado"] != "activa":
        return "El condominio no tiene una suscripción activa. Contacte al proveedor."
    if date.today() > susc["fecha_fin"] + timedelta(days=cfg.DIAS_GRACIA_SUSCRIPCION):
        return (f"La suscripción venció el {susc['fecha_fin']:%d/%m/%Y}. "
                "Regularice el pago para seguir usando el sistema.")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Autenticación
# ─────────────────────────────────────────────────────────────────────────────

def _nodo_actual(db: CentralDB):
    clave = request.headers.get("X-Nodo-Clave", "")
    return db.nodo_por_clave_hash(hash_clave_nodo(clave)) if clave else None


def requiere_sesion(*roles, permitir_temporal: bool = False):
    """Valida el token 'Authorization: Bearer ...' y el rol de la cuenta.
    Una cuenta con contraseña temporal solo puede usar los endpoints marcados con
    permitir_temporal (cambiar su contraseña)."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            try:
                data = _serializer().loads(token, max_age=cfg.TOKEN_HORAS * 3600)
            except (BadSignature, SignatureExpired):
                return _error("Sesión expirada. Inicie sesión nuevamente.", 401)
            with CentralDB() as db:
                cuenta = db.cuenta_por_id(data["idcuenta"])
                if not cuenta or not cuenta["activa"]:
                    return _error("Cuenta desactivada", 401)
                if cuenta["debe_cambiar_password"] and not permitir_temporal:
                    return _error("Debe cambiar su contraseña temporal antes de continuar.", 403)
                if roles and cuenta["rol"] not in roles:
                    return _error("No tiene permisos para esta operación", 403)
                g.cuenta, g.db = cuenta, db
                return fn(*args, **kwargs)
        return wrapper
    return deco


@app.post("/api/login")
def login():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    with CentralDB() as db:
        cuenta = db.cuenta_por_email(email)
        if not cuenta or not verify_password(body.get("password") or "", cuenta["password_hash"]):
            return _error("Correo o contraseña incorrectos", 401)
        if not cuenta["activa"]:
            return _error("La cuenta está desactivada. Contacte al administrador.", 401)

        respuesta = {
            "token": _serializer().dumps({"idcuenta": cuenta["idcuenta"]}),
            "cuenta": {
                "idcuenta": cuenta["idcuenta"], "email": cuenta["email"],
                "nombre": f"{cuenta['nombres']} {cuenta['apellidos']}",
                "rol": cuenta["rol"], "idcondominio": cuenta["idcondominio"],
                "debe_cambiar_password": bool(cuenta["debe_cambiar_password"]),
            },
        }
        if cuenta["rol"] != "superadmin":
            nodo = _nodo_actual(db)
            if not nodo or nodo["idcondominio"] != cuenta["idcondominio"]:
                return _error("Este equipo no está autorizado para el condominio de la cuenta.",
                              403)
            problema = _problema_suscripcion(db, cuenta["idcondominio"])
            if problema:
                return _error(problema, 403)
            db.registrar_contacto_nodo(nodo["idnodo"])
            respuesta["licencia"] = _licencia(db, cuenta["idcondominio"])
        db.registrar_acceso(cuenta["idcuenta"])
        return jsonify(respuesta)


@app.get("/api/nodo/sincronizar")
def sincronizar():
    """El nodo descarga su licencia y las cuentas de su condominio (para operar sin conexión)."""
    with CentralDB() as db:
        nodo = _nodo_actual(db)
        if not nodo:
            return _error("Nodo no autorizado", 401)
        db.registrar_contacto_nodo(nodo["idnodo"])
        cuentas = [
            {k: c[k] for k in ("idcuenta", "rol", "rut", "nombres", "apellidos", "email",
                               "password_hash", "debe_cambiar_password", "activa")}
            for c in db.cuentas_condominio(nodo["idcondominio"])
        ]
        return jsonify({"licencia": _licencia(db, nodo["idcondominio"]), "cuentas": cuentas})


# ─────────────────────────────────────────────────────────────────────────────
# Nodo: registro desde el celular (invitaciones y registros cifrados)
# ─────────────────────────────────────────────────────────────────────────────

def requiere_nodo(fn):
    """Endpoints que usa el equipo de la portería, autenticado con su clave."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with CentralDB() as db:
            nodo = _nodo_actual(db)
            if not nodo:
                return _error("Nodo no autorizado", 401)
            g.nodo, g.db = nodo, db
            return fn(*args, **kwargs)
    return wrapper


@app.post("/api/nodo/clave-registro")
@requiere_nodo
def clave_registro():
    """Clave pública con la que la nube cifra los registros para este nodo."""
    pem = (request.get_json(silent=True) or {}).get("clave_publica") or ""
    if "BEGIN PUBLIC KEY" not in pem or len(pem) > 1000:
        return _error("Clave pública inválida", 400)
    g.db.guardar_clave_registro(g.nodo["idnodo"], pem)
    return jsonify({"ok": True})


@app.post("/api/nodo/invitaciones")
@requiere_nodo
def crear_invitacion_registro():
    b = request.get_json(silent=True) or {}
    if b.get("tipo") not in ("residente", "visita"):
        return _error("Tipo inválido", 400)
    th = b.get("token_hash") or ""
    if len(th) != 64:
        return _error("Token inválido", 400)
    horas = int(b.get("horas") or 48)
    if not 1 <= horas <= 24 * 14:
        return _error("Vigencia inválida", 400)
    g.db.crear_invitacion_registro(
        g.nodo["idnodo"], th, b["tipo"], int(b["id_local"]), str(b.get("unidad", ""))[:20],
        bool(b.get("solo_rostro")), str(b.get("consentimiento_version") or "")[:20], horas,
        frecuente=bool(b.get("frecuente")), rostro=bool(b.get("rostro", True)))
    return jsonify({"ok": True}), 201


@app.get("/api/nodo/registros")
@requiere_nodo
def registros_pendientes():
    """Registros enviados desde celulares, cifrados para este nodo."""
    g.db.purgar_invitaciones_registro()
    return jsonify([{"idenvio": e["idenvio"], "id_local": e["id_local"], "tipo": e["tipo"],
                     "paquete": e["paquete"]} for e in g.db.envios_pendientes(g.nodo["idnodo"])])


@app.post("/api/nodo/registros/<int:idenvio>/recibido")
@requiere_nodo
def registro_recibido(idenvio):
    """El nodo guardó el registro: se elimina de la nube."""
    if not g.db.borrar_envio(g.nodo["idnodo"], idenvio):
        return _error("Registro no encontrado", 404)
    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────────────────
# Administrador del condominio: cuentas
# ─────────────────────────────────────────────────────────────────────────────

def _cuenta_publica(c):
    return {"idcuenta": c["idcuenta"], "rut": c["rut"], "nombres": c["nombres"],
            "apellidos": c["apellidos"], "email": c["email"], "rol": c["rol"],
            "activa": bool(c["activa"]),
            "debe_cambiar_password": bool(c["debe_cambiar_password"]),
            "ultimo_acceso": c["ultimo_acceso"].isoformat() if c["ultimo_acceso"] else None}


def _restablecer(cuenta):
    """Contraseña temporal nueva: se muestra una sola vez a quien restablece, y la
    cuenta deberá cambiarla al iniciar sesión."""
    temporal = temporary_password()
    g.db.cambiar_password(cuenta["idcuenta"], temporal, temporal=True)
    return jsonify({"email": cuenta["email"], "password_temporal": temporal})


# ─────────────────────────────────────────────────────────────────────────────
# Cualquier cuenta: cambiar la propia contraseña
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/cuenta/password")
@requiere_sesion(permitir_temporal=True)
def cambiar_mi_password():
    body = request.get_json(silent=True) or {}
    actual, nueva = body.get("actual") or "", body.get("nueva") or ""
    if not verify_password(actual, g.cuenta["password_hash"]):
        return _error("La contraseña actual no es correcta", 400)
    problema = password_problem(nueva)
    if problema:
        return _error(problema, 400)
    if nueva == actual:
        return _error("La contraseña nueva debe ser distinta de la actual", 400)
    g.db.cambiar_password(g.cuenta["idcuenta"], nueva, temporal=False)
    return jsonify({"ok": True})


def _cuenta_del_condominio(idcuenta):
    c = g.db.cuenta_por_id(idcuenta)
    return c if c and c["idcondominio"] == g.cuenta["idcondominio"] else None


def _validar_nueva_cuenta(body):
    faltan = [k for k in ("rut", "nombres", "apellidos", "email", "password") if not body.get(k)]
    if faltan:
        return "Complete todos los campos"
    if not valid_rut(body["rut"]):
        return "RUT inválido"
    if "@" not in body["email"]:
        return "Correo inválido"
    return password_problem(body["password"])


@app.get("/api/cuentas")
@requiere_sesion("administrador")
def listar_cuentas():
    return jsonify([_cuenta_publica(c)
                    for c in g.db.cuentas_condominio(g.cuenta["idcondominio"])])


@app.post("/api/cuentas")
@requiere_sesion("administrador")
def crear_cuenta():
    body = request.get_json(silent=True) or {}
    problema = _validar_nueva_cuenta(body)
    if problema:
        return _error(problema, 400)
    if body.get("rol") not in ("administrador", "conserje"):
        return _error("Rol inválido", 400)
    try:
        idc = g.db.crear_cuenta(g.cuenta["idcondominio"], body["rol"], format_rut(body["rut"]),
                                body["nombres"].strip(), body["apellidos"].strip(),
                                body["email"].strip(), body["password"], temporal=True)
    except MySQLError as e:
        if e.errno == 1062:
            return _error("Ese correo ya está en uso", 409)
        raise
    return jsonify({"idcuenta": idc}), 201


@app.post("/api/cuentas/<int:idcuenta>/activa")
@requiere_sesion("administrador")
def activar_cuenta(idcuenta):
    c = _cuenta_del_condominio(idcuenta)
    if not c:
        return _error("Cuenta no encontrada", 404)
    if idcuenta == g.cuenta["idcuenta"]:
        return _error("No puede desactivar su propia cuenta", 400)
    g.db.activar_cuenta(idcuenta, bool((request.get_json(silent=True) or {}).get("activa")))
    return jsonify({"ok": True})


@app.post("/api/cuentas/<int:idcuenta>/password")
@requiere_sesion("administrador")
def restablecer_password(idcuenta):
    """El administrador restablece la contraseña de una cuenta de su condominio."""
    c = _cuenta_del_condominio(idcuenta)
    if not c:
        return _error("Cuenta no encontrada", 404)
    if idcuenta == g.cuenta["idcuenta"]:
        return _error("Para su propia cuenta use «Cambiar mi contraseña»", 400)
    return _restablecer(c)


# ─────────────────────────────────────────────────────────────────────────────
# Proveedor (superadmin): condominios, suscripciones y pagos
# ─────────────────────────────────────────────────────────────────────────────

def _iso(filas, *campos):
    """Fechas a texto ISO (jsonify las convertiría a formato HTTP)."""
    for f in filas:
        for k in campos:
            if f.get(k) is not None:
                f[k] = f[k].isoformat()
    return filas


@app.get("/api/proveedor/planes")
@requiere_sesion("superadmin")
def planes():
    """?todos=1 incluye los planes desactivados (pantalla de planes)."""
    return jsonify(g.db.planes(todos=request.args.get("todos") == "1"))


def _validar_plan(body):
    nombre = (body.get("nombre") or "").strip()
    try:
        precio, camaras = int(body.get("precio_mensual")), int(body.get("max_camaras"))
    except (TypeError, ValueError):
        return None, "Precio y número de cámaras deben ser números enteros"
    if not nombre or len(nombre) > 40:
        return None, "El nombre es obligatorio (máximo 40 caracteres)"
    if not 0 <= precio <= 99_999_999:
        return None, "Precio mensual inválido"
    if not 1 <= camaras <= 64:
        return None, "El número de cámaras debe estar entre 1 y 64"
    return (nombre, precio, camaras), None


@app.post("/api/proveedor/planes")
@requiere_sesion("superadmin")
def crear_plan():
    datos, problema = _validar_plan(request.get_json(silent=True) or {})
    if problema:
        return _error(problema, 400)
    try:
        return jsonify({"idplan": g.db.crear_plan(*datos)}), 201
    except MySQLError as e:
        if e.errno == 1062:
            return _error("Ya existe un plan con ese nombre", 409)
        raise


@app.post("/api/proveedor/planes/<int:idplan>")
@requiere_sesion("superadmin")
def actualizar_plan(idplan):
    body = request.get_json(silent=True) or {}
    if not g.db.plan(idplan):
        return _error("Plan no encontrado", 404)
    datos, problema = _validar_plan(body)
    if problema:
        return _error(problema, 400)
    try:
        g.db.actualizar_plan(idplan, *datos, bool(body.get("activo", True)))
    except MySQLError as e:
        if e.errno == 1062:
            return _error("Ya existe un plan con ese nombre", 409)
        raise
    return jsonify({"ok": True})


@app.post("/api/proveedor/suscripciones/<int:idsuscripcion>/plan")
@requiere_sesion("superadmin")
def cambiar_plan(idsuscripcion):
    """Cambia el plan de un condominio. El límite de cámaras nuevo llega al nodo
    con la licencia en su próxima sincronización."""
    plan = g.db.plan(int((request.get_json(silent=True) or {}).get("idplan") or 0))
    if not plan or not plan["activo"]:
        return _error("Plan inválido o desactivado", 400)
    g.db.cambiar_plan(idsuscripcion, plan["idplan"])
    return jsonify({"ok": True})


@app.get("/api/proveedor/condominios/<int:idcondominio>/pagos")
@requiere_sesion("superadmin")
def pagos_condominio(idcondominio):
    return jsonify(_iso(g.db.pagos_condominio(idcondominio), "fecha_pago", "fecha_anulacion"))


@app.post("/api/proveedor/pagos/<int:idpago>/anular")
@requiere_sesion("superadmin")
def anular_pago(idpago):
    motivo = ((request.get_json(silent=True) or {}).get("motivo") or "").strip()
    if not motivo:
        return _error("Indique el motivo de la anulación", 400)
    problema = g.db.anular_pago(idpago, motivo[:200])
    if problema:
        return _error(problema, 400)
    return jsonify({"ok": True})


@app.post("/api/proveedor/cuentas/<int:idcuenta>/activa")
@requiere_sesion("superadmin")
def proveedor_activar_cuenta(idcuenta):
    if not g.db.cuenta_por_id(idcuenta):
        return _error("Cuenta no encontrada", 404)
    if idcuenta == g.cuenta["idcuenta"]:
        return _error("No puede desactivar su propia cuenta", 400)
    g.db.activar_cuenta(idcuenta, bool((request.get_json(silent=True) or {}).get("activa")))
    return jsonify({"ok": True})


@app.get("/api/proveedor/condominios")
@requiere_sesion("superadmin")
def condominios():
    filas = g.db.condominios()
    for f in filas:
        for k in ("fecha_fin", "ultimo_contacto"):
            if f[k]:
                f[k] = f[k].isoformat()
    return jsonify(filas)


@app.post("/api/proveedor/condominios")
@requiere_sesion("superadmin")
def crear_condominio():
    """Alta de cliente: condominio + suscripción de prueba + administrador + nodo."""
    b = request.get_json(silent=True) or {}
    c, adm = b.get("condominio") or {}, b.get("administrador") or {}
    if not all(c.get(k) for k in ("rut", "nombre", "direccion", "comuna", "email")):
        return _error("Complete los datos del condominio", 400)
    if not valid_rut(c["rut"]):
        return _error("RUT del condominio inválido", 400)
    problema = _validar_nueva_cuenta(adm)
    if problema:
        return _error(f"Administrador: {problema}", 400)
    if g.db.cuenta_por_email(adm["email"].strip().lower()):
        return _error("El correo del administrador ya está en uso", 409)

    clave_nodo = nueva_clave_nodo()
    try:
        idc = g.db.crear_condominio(format_rut(c["rut"]), c["nombre"], c["direccion"],
                                    c["comuna"], c["email"], c.get("telefono") or None)
        g.db.crear_suscripcion(idc, int(b["idplan"]), cfg.DIAS_PRUEBA)
        g.db.crear_cuenta(idc, "administrador", format_rut(adm["rut"]), adm["nombres"],
                          adm["apellidos"], adm["email"].strip(), adm["password"],
                          temporal=True)
        g.db.reemplazar_nodo(idc, "Portería", hash_clave_nodo(clave_nodo))
    except MySQLError as e:
        if e.errno == 1062:
            return _error("Ya existe un condominio con ese RUT", 409)
        raise
    # la clave del nodo se muestra una sola vez: se instala en el PC de la portería
    return jsonify({"idcondominio": idc, "clave_nodo": clave_nodo}), 201


@app.get("/api/proveedor/condominios/<int:idcondominio>/cuentas")
@requiere_sesion("superadmin")
def cuentas_de_condominio(idcondominio):
    return jsonify([_cuenta_publica(c) for c in g.db.cuentas_condominio(idcondominio)])


@app.post("/api/proveedor/cuentas/<int:idcuenta>/password")
@requiere_sesion("superadmin")
def proveedor_restablecer_password(idcuenta):
    """El proveedor restablece la contraseña de cualquier cuenta (p. ej. el único
    administrador de un condominio que la olvidó). La propia se cambia aparte."""
    c = g.db.cuenta_por_id(idcuenta)
    if not c:
        return _error("Cuenta no encontrada", 404)
    if idcuenta == g.cuenta["idcuenta"]:
        return _error("Para su propia cuenta use «Cambiar mi contraseña»", 400)
    return _restablecer(c)


@app.post("/api/proveedor/condominios/<int:idcondominio>/nodo")
@requiere_sesion("superadmin")
def regenerar_nodo(idcondominio):
    """Nueva clave de nodo (reinstalación o clave extraviada); la anterior deja de valer."""
    clave_nodo = nueva_clave_nodo()
    g.db.reemplazar_nodo(idcondominio, "Portería", hash_clave_nodo(clave_nodo))
    return jsonify({"clave_nodo": clave_nodo})


@app.post("/api/proveedor/suscripciones/<int:idsuscripcion>/pagos")
@requiere_sesion("superadmin")
def registrar_pago(idsuscripcion):
    b = request.get_json(silent=True) or {}
    meses = int(b.get("meses") or 0)
    if not 1 <= meses <= 24:
        return _error("Meses inválidos", 400)
    medio = b.get("medio") or "transferencia"
    if medio not in ("transferencia", "efectivo", "otro"):
        return _error("Medio de pago inválido", 400)
    if not g.db.registrar_pago(idsuscripcion, meses, b.get("referencia"), medio):
        return _error("Suscripción no encontrada", 404)
    return jsonify({"ok": True})


@app.post("/api/proveedor/suscripciones/<int:idsuscripcion>/estado")
@requiere_sesion("superadmin")
def estado_suscripcion(idsuscripcion):
    estado = (request.get_json(silent=True) or {}).get("estado")
    if estado not in ("activa", "suspendida", "cancelada"):
        return _error("Estado inválido", 400)
    g.db.cambiar_estado_suscripcion(idsuscripcion, estado)
    return jsonify({"ok": True})


@app.get("/api/salud")
def salud():
    return jsonify({"ok": True})


@app.get("/")
def inicio():
    return jsonify({"servicio": "API central de Umbral Guardian", "estado": "activa",
                    "nota": "Esta API la usa el programa de escritorio; no tiene interfaz web."})


if __name__ == "__main__":
    print(f"[API] Umbral Guardian central en http://{cfg.HOST}:{cfg.PORT}")
    app.run(host=cfg.HOST, port=cfg.PORT)
