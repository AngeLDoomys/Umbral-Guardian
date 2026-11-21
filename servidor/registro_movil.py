# -*- coding: utf-8 -*-
"""
servidor/registro_movil.py - Registro desde el celular (páginas públicas).

El residente o la visita abre el enlace de su invitación (QR o WhatsApp), desde
cualquier lugar, y completa:
  residente : datos + vehículo (opcional) + consentimiento + 5 fotos del rostro
  solo rostro: consentimiento + 5 fotos (residente ya registrado)
  visita    : datos de la visita y su patente

Fotos: se procesan en memoria (detección, calidad y vector SFace) y se descartan;
no se escriben en disco ni en los registros. Mientras el formulario está abierto
la nube no guarda nada: los vectores aceptados los conserva el propio celular,
firmados (HMAC) para que no puedan falsificarse. Al enviar, todo se cifra con la
clave pública del nodo del condominio (core/cifrado.py) y queda a la espera de
que el nodo lo descargue; la nube no puede leerlo.
"""

import base64
import hashlib
import hmac
import io
import re
from datetime import date, datetime, timezone

import numpy as np
from flask import Blueprint, abort, jsonify, render_template_string, request

import config
from core import cifrado
from core.security import clean_plate, format_rut, valid_rut
from core.textos import (PERIODO_VISITA, PERIODO_VISITA_FRECUENTE, TEXTO_CONSENTIMIENTO,
                         TEXTO_CONSENTIMIENTO_VISITA, TEXTO_REGISTRO_REMOTO)
from servidor import config_servidor as cfg
from servidor.central_db import CentralDB

bp = Blueprint("registro_movil", __name__)

TIPOS_RESIDENTE = {1: "Propietario", 2: "Arrendatario", 3: "Familiar / ocupante"}
TIPOS_VEHICULO = ("auto", "moto", "camioneta", "otro")
_MAX_LADO = 1600   # px; las fotos del celular se reducen antes de procesarlas


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _secreto() -> bytes:
    with open(cfg.SECRET_FILE, "rb") as f:
        return f.read().strip()


def _firmar(token_hash: str, emb_b64: str) -> str:
    return hmac.new(_secreto(), f"{token_hash}:{emb_b64}".encode(), hashlib.sha256).hexdigest()


def _vectores_firmados(token_hash: str, items) -> list:
    """Vectores que el celular devuelve: solo se aceptan los firmados por esta nube
    para esta misma invitación."""
    out = []
    for it in items or []:
        emb_b64, firma = it.get("emb", ""), it.get("firma", "")
        if not hmac.compare_digest(_firmar(token_hash, emb_b64), firma):
            raise ValueError("Foto no válida")
        out.append(np.frombuffer(base64.b64decode(emb_b64), dtype=np.float32))
    return out


def _invitacion(token: str):
    with CentralDB() as db:
        inv = db.invitacion_registro(_token_hash(token))
    if not inv or not inv["nodo_activo"]:
        abort(404)
    return inv


def _pide_rostro(inv) -> bool:
    """Residentes siempre; visitas cuando el reglamento del condominio lo exige."""
    return inv["tipo"] == "residente" or bool(inv.get("rostro"))


def _texto_consentimiento(inv) -> str:
    if inv["tipo"] == "visita":
        periodo = PERIODO_VISITA_FRECUENTE if inv.get("frecuente") else PERIODO_VISITA
        base = TEXTO_CONSENTIMIENTO_VISITA.format(modelo=config.FACE_MODEL, periodo=periodo)
    else:
        base = TEXTO_CONSENTIMIENTO.format(modelo=config.FACE_MODEL)
    return base + TEXTO_REGISTRO_REMOTO


# ── validación de formularios ───────────────────────────────────────────────

def _texto(d, k, maximo, obligatorio=True):
    v = (d.get(k) or "").strip()
    if obligatorio and not v:
        raise ValueError(f"Complete el campo «{k.replace('_', ' ')}»")
    if len(v) > maximo:
        raise ValueError(f"«{k}» es demasiado largo")
    return v or None


def _rut(d, k="rut"):
    v = (d.get(k) or "").strip()
    if not valid_rut(v):
        raise ValueError("RUT inválido (revise el dígito verificador)")
    return format_rut(v)


def _patente(v, tipo="auto"):
    from core.plate_utils import _valid_chilean
    p = clean_plate(v)
    if not _valid_chilean(p, moto=(tipo == "moto")):
        raise ValueError(f"La patente «{v}» no tiene formato chileno")
    return p


def validar_datos(tipo: str, d: dict, frecuente: bool = False) -> dict:
    """Valida y normaliza lo ingresado. Lanza ValueError con un mensaje para el usuario."""
    if tipo == "visita":
        out = {"nombres": _texto(d, "nombres", 60), "apellidos": _texto(d, "apellidos", 60),
               "rut": _rut(d)}
        if (d.get("patente") or "").strip():
            out["patente"] = _patente(d["patente"], d.get("tipo_vehiculo") or "auto")
        if frecuente:      # sin fecha: vale desde la aprobación hasta que se revoque
            return out
        try:
            fecha = date.fromisoformat(d.get("fecha_visita") or "")
        except ValueError:
            raise ValueError("Indique la fecha de la visita")
        if not 0 <= (fecha - date.today()).days <= 60:
            raise ValueError("La fecha de la visita debe ser entre hoy y los próximos 60 días")
        out["fecha_visita"] = fecha.isoformat()
        return out

    out = {"nombres": _texto(d, "nombres", 60), "apellidos": _texto(d, "apellidos", 60),
           "rut": _rut(d), "telefono": _texto(d, "telefono", 20, False)}
    email = _texto(d, "email", 120, False)
    if email and not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ValueError("Correo inválido")
    out["email"] = email
    try:
        out["idtipo_residente"] = int(d.get("idtipo_residente"))
        assert out["idtipo_residente"] in TIPOS_RESIDENTE
    except (TypeError, ValueError, AssertionError):
        raise ValueError("Seleccione el tipo de residente")
    if d.get("fecha_nacimiento"):
        try:
            nac = date.fromisoformat(d["fecha_nacimiento"])
        except ValueError:
            raise ValueError("Fecha de nacimiento inválida")
        hoy = date.today()
        edad = hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))
        if edad < 16:
            # art. 16 quáter: el consentimiento lo da su representante, en la administración
            raise ValueError("Los menores de 16 años se registran en la administración, "
                             "con su madre, padre o tutor")
        out["fecha_nacimiento"] = nac.isoformat()
    if (d.get("patente") or "").strip():
        tipo_v = d.get("tipo_vehiculo") or "auto"
        if tipo_v not in TIPOS_VEHICULO:
            raise ValueError("Tipo de vehículo inválido")
        out["vehiculo"] = {"patente": _patente(d["patente"], tipo_v), "tipo": tipo_v,
                           "marca": _texto(d, "marca", 40, False),
                           "modelo": _texto(d, "modelo", 40, False),
                           "color": _texto(d, "color", 30, False)}
    return out


# ── páginas ─────────────────────────────────────────────────────────────────

@bp.get("/r/<token>")
def formulario(token):
    inv = _invitacion(token)
    if not inv["vigente"]:
        return render_template_string(_PAGINA_FIN, titulo="Invitación no disponible",
                                      mensaje="Este enlace ya se usó o venció. Pida uno nuevo a "
                                              "la administración del condominio."), 410
    rostro = _pide_rostro(inv)
    consentimiento = _texto_consentimiento(inv) if rostro else ""
    resp = render_template_string(
        _PAGINA, inv=inv, token=token, consentimiento=consentimiento, rostro=rostro,
        tipos=TIPOS_RESIDENTE, tipos_vehiculo=TIPOS_VEHICULO, capturas=config.MAX_CAPTURES,
        hoy=date.today().isoformat())
    return resp, 200, {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


@bp.post("/r/<token>/validar")
def validar(token):
    inv = _invitacion(token)
    if not inv["vigente"]:
        return jsonify({"error": "La invitación ya no está disponible"}), 410
    try:
        validar_datos(inv["tipo"], request.get_json(silent=True) or {}, bool(inv["frecuente"]))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


@bp.post("/r/<token>/foto")
def foto(token):
    """Revisa una foto y calcula su vector. La foto no se guarda: se procesa en
    memoria y se descarta al terminar esta función."""
    import json
    import cv2
    from PIL import Image, ImageOps
    from core import face_utils as fu

    inv = _invitacion(token)
    if not inv["vigente"] or not _pide_rostro(inv):
        return jsonify({"error": "La invitación ya no está disponible"}), 410
    th = _token_hash(token)
    try:
        previos = _vectores_firmados(th, json.loads(request.form.get("previos") or "[]"))
    except (ValueError, TypeError):
        return jsonify({"error": "Recargue la página e intente de nuevo"}), 400
    if len(previos) >= config.MAX_CAPTURES:
        return jsonify({"error": "Ya tiene todas las fotos"}), 400
    archivo = request.files.get("foto")
    if not archivo:
        return jsonify({"error": "No llegó la foto"}), 400
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(archivo.read()))).convert("RGB")
    except Exception:
        return jsonify({"error": "No se pudo leer la imagen"}), 400
    img.thumbnail((_MAX_LADO, _MAX_LADO))
    bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    del img

    info = fu.extract_face(bgr)
    del bgr
    if info is None:
        return jsonify({"error": "No se ve un rostro. Mire de frente a la cámara, con buena luz."}), 422
    problema = fu.quality_problem(info)
    if problema:
        consejo = {"rostro pequeño": "Acerque más la cámara a su cara.",
                   "borroso": "La foto salió movida: sostenga firme el celular.",
                   "detección dudosa": "Mejore la luz y mire hacia la cámara."}
        clave = next((k for k in consejo if problema.startswith(k)), None)
        return jsonify({"error": consejo.get(clave, f"Foto no apta: {problema}")}), 422
    emb = info["embedding"].astype(np.float32)
    v = emb / (np.linalg.norm(emb) + 1e-9)
    for p in previos:
        if 1 - float(v @ (p / (np.linalg.norm(p) + 1e-9))) < config.MIN_CAPTURE_DIFF:
            return jsonify({"error": "Es casi igual a una foto anterior. Cambie un poco la pose "
                                     "(gire la cara o mire un poco arriba o abajo)."}), 422
    emb_b64 = base64.b64encode(emb.tobytes()).decode()
    return jsonify({"ok": True, "emb": emb_b64, "firma": _firmar(th, emb_b64)})


@bp.post("/r/<token>/enviar")
def enviar(token):
    inv = _invitacion(token)
    if not inv["vigente"]:
        return jsonify({"error": "La invitación ya no está disponible"}), 410
    if not inv["clave_registro"]:
        return jsonify({"error": "El condominio aún no habilita el registro en línea"}), 503
    body = request.get_json(silent=True) or {}
    th = _token_hash(token)
    paquete = {"tipo": inv["tipo"], "id_local": inv["id_local"], "datos": {},
               "embeddings": [], "modelo": config.FACE_MODEL}
    try:
        if not (inv["tipo"] == "residente" and inv["solo_rostro"]):
            paquete["datos"] = validar_datos(inv["tipo"], body.get("datos") or {},
                                             bool(inv["frecuente"]))
        if _pide_rostro(inv):
            if body.get("consentimiento") is not True:
                raise ValueError("Debe aceptar el consentimiento para registrar su rostro")
            vectores = _vectores_firmados(th, body.get("fotos"))
            if len(vectores) < config.MAX_CAPTURES:
                raise ValueError(f"Faltan fotos ({len(vectores)} de {config.MAX_CAPTURES})")
            paquete["embeddings"] = [base64.b64encode(x.tobytes()).decode() for x in vectores]
            paquete["consentimiento_version"] = inv["consentimiento_version"]
            paquete["consentimiento_fecha"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    cifrado_ = cifrado.cifrar(paquete, inv["clave_registro"])
    with CentralDB() as db:
        actual = db.invitacion_registro(th)       # dos envíos simultáneos: solo vale el primero
        if not actual or not actual["vigente"]:
            return jsonify({"error": "La invitación ya se usó"}), 410
        db.guardar_envio_registro(inv["idinvitacion"], cifrado_)
    return jsonify({"ok": True})


# ── plantillas HTML (sin dependencias externas) ─────────────────────────────

_ESTILO = """
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 :root{--bg:#1e1e2e;--panel:#2d2d44;--item:#3d3d5c;--verde:#00c97a;--txt:#fff;--gris:#aab;--rojo:#ff6b6b}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);
 font:16px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
 main{max-width:520px;margin:0 auto;padding:18px 16px 40px}
 h1{font-size:22px;margin:4px 0 2px;color:var(--verde)} .sub{color:var(--gris);margin:0 0 16px}
 section{background:var(--panel);border-radius:12px;padding:16px;margin:12px 0}
 label{display:block;font-size:14px;color:var(--gris);margin:10px 0 4px}
 input,select{width:100%;max-width:100%;min-width:0;padding:12px;border-radius:8px;
 border:1px solid #556;background:var(--item);color:var(--txt);font-size:16px}
 .fila{display:flex;gap:10px} .fila>div{flex:1 1 0;min-width:0}
 /* Safari en iPhone ignora el ancho de los campos de fecha y los saca del margen */
 input[type=date]{-webkit-appearance:none;appearance:none;display:block;min-height:46px;
 text-align:left} input[type=date]::-webkit-date-and-time-value{text-align:left}
 button{width:100%;padding:14px;border:0;border-radius:10px;background:var(--verde);color:#000;
 font-size:17px;font-weight:700;margin-top:14px} button:disabled{opacity:.45}
 .sec{background:var(--item);color:var(--txt)} .err{color:var(--rojo);min-height:1.2em;margin-top:8px}
 .consent{white-space:pre-wrap;font-size:14px;max-height:260px;overflow:auto;background:var(--item);
 padding:12px;border-radius:8px} .chk{display:flex;gap:10px;align-items:flex-start;margin-top:12px}
 .chk input{width:22px;height:22px;flex:none}
 .pose{display:flex;align-items:center;gap:12px;padding:10px;border-radius:10px;background:var(--item);margin:8px 0}
 .pose b{flex:1} .ok{color:var(--verde);font-weight:700} .oculto{display:none}
</style>"""

_PAGINA_FIN = "<!doctype html><html lang=es><head><meta charset=utf-8><title>{{titulo}}</title>" + \
    _ESTILO + "</head><body><main><h1>{{titulo}}</h1><p>{{mensaje}}</p></main></body></html>"

_PAGINA = "<!doctype html><html lang=es><head><meta charset=utf-8><title>Registro — Umbral Guardian</title>" \
    + _ESTILO + """</head><body><main>
<h1>{{ inv.condominio }}</h1>
<p class=sub>Unidad {{ inv.unidad }} ·
 {% if inv.tipo == 'visita' %}Registro de visita{% if inv.frecuente %} frecuente{% endif %}{% elif inv.solo_rostro %}Registro de rostro{% else %}Registro de residente{% endif %}</p>

{% if not inv.solo_rostro %}
<section id=paso-datos>
 {% if inv.tipo == 'visita' %}
  <h3>{{ '1. ' if rostro }}Datos de la visita</h3>
 {% else %}
  <h3>1. Sus datos</h3>
 {% endif %}
 <div class=fila><div><label>Nombres</label><input id=nombres autocomplete=given-name></div>
 <div><label>Apellidos</label><input id=apellidos autocomplete=family-name></div></div>
 <label>RUT</label><input id=rut placeholder="12.345.678-5">
 {% if inv.tipo == 'visita' %}
  {% if not inv.frecuente %}
  <label>Fecha de la visita</label><input id=fecha_visita type=date min="{{hoy}}" value="{{hoy}}">
  {% endif %}
 {% else %}
  <label>Tipo de residente</label><select id=idtipo_residente>
   {% for k, v in tipos.items() %}<option value={{k}}>{{v}}</option>{% endfor %}</select>
  <div class=fila><div><label>Teléfono (opcional)</label><input id=telefono type=tel></div>
  <div><label>Nacimiento (opcional)</label><input id=fecha_nacimiento type=date max="{{hoy}}"></div></div>
  <label>Correo (opcional)</label><input id=email type=email>
 {% endif %}
 <h3 style="margin-top:18px">Vehículo (opcional)</h3>
 <div class=fila><div><label>Patente</label><input id=patente placeholder="BCDF12"></div>
 <div><label>Tipo</label><select id=tipo_vehiculo>
  {% for t in tipos_vehiculo %}<option>{{t}}</option>{% endfor %}</select></div></div>
 {% if inv.tipo != 'visita' %}
 <div class=fila><div><label>Marca</label><input id=marca></div><div><label>Color</label><input id=color></div></div>
 <input id=modelo type=hidden>
 {% endif %}
 <div class=err id=err-datos></div>
 <button id=b-datos>{% if rostro %}Continuar{% else %}Enviar{% endif %}</button>
</section>
{% endif %}

{% if rostro %}
<section id=paso-consent class="{{ '' if inv.solo_rostro else 'oculto' }}">
 <h3>{{ '1' if inv.solo_rostro else '2' }}. Consentimiento</h3>
 <div class=consent>{{ consentimiento }}</div>
 <label class=chk><input type=checkbox id=acepto><span>Leí la información y otorgo mi
 consentimiento para el tratamiento de mi dato biométrico con esta finalidad.</span></label>
 <div class=err id=err-consent></div>
 <button id=b-consent>Continuar</button>
</section>

<section id=paso-fotos class=oculto>
 <h3>{{ '2' if inv.solo_rostro else '3' }}. Fotos de su rostro</h3>
 <p class=sub>Sin lentes de sol ni gorro, con buena luz. Entre una foto y otra cambie un poco la pose.</p>
 <div id=poses></div>
 <input id=camara type=file accept="image/*" capture=user class=oculto>
 <div class=err id=err-fotos></div>
 <button id=b-enviar disabled>Enviar registro</button>
</section>
{% endif %}

<section id=paso-fin class=oculto>
 <h3>¡Listo!</h3>
 <p>Su registro llegó al condominio. La administración lo revisará y aprobará;
 {% if inv.tipo == 'visita' and rostro %}después de eso la cámara del acceso lo reconocerá
 {% if inv.frecuente %}en sus visitas{% else %}el día de su visita{% endif %}. Lleve su carnet.
 {% elif inv.tipo == 'visita' %}muestre su carnet al llegar a la portería.{% else %}después de eso
 la cámara del acceso lo reconocerá.{% endif %}</p>
 <p class=sub>Ya puede cerrar esta página.</p>
</section>
</main>
<script>
const TOKEN = {{ token|tojson }}, TIPO = {{ inv.tipo|tojson }}, SOLO_ROSTRO = {{ inv.solo_rostro|int }};
const ROSTRO = {{ rostro|tojson }};
const N = {{ capturas }};
const POSES = ["De frente", "Girando un poco a la izquierda", "Girando un poco a la derecha",
               "Mirando un poco hacia arriba", "Mirando un poco hacia abajo"];
const $ = id => document.getElementById(id);
let datos = {}, fotos = [], actual = 0;

function campos() {
  const d = {};
  document.querySelectorAll("#paso-datos input, #paso-datos select").forEach(e => d[e.id] = e.value);
  return d;
}
async function post(url, body) {
  const r = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"},
                              body: JSON.stringify(body)});
  return [r.ok, await r.json().catch(() => ({error: "Error de conexión"}))];
}
function mostrar(id) {
  ["paso-datos", "paso-consent", "paso-fotos", "paso-fin"].forEach(p => $(p) && $(p).classList.add("oculto"));
  $(id).classList.remove("oculto"); window.scrollTo(0, 0);
}
async function enviar() {
  const [ok, r] = await post(`/r/${TOKEN}/enviar`, {datos, consentimiento: true, fotos});
  if (ok) mostrar("paso-fin");
  return [ok, r];
}

if ($("b-datos")) $("b-datos").onclick = async () => {
  datos = campos(); $("b-datos").disabled = true; $("err-datos").textContent = "";
  const [ok, r] = await post(`/r/${TOKEN}/validar`, datos);
  if (!ok) { $("err-datos").textContent = r.error; $("b-datos").disabled = false; return; }
  if (!ROSTRO) {
    const [ok2, r2] = await enviar();
    if (!ok2) { $("err-datos").textContent = r2.error; $("b-datos").disabled = false; }
  } else mostrar("paso-consent");
};

if ($("b-consent")) $("b-consent").onclick = () => {
  if (!$("acepto").checked) { $("err-consent").textContent = "Debe aceptar para continuar"; return; }
  dibujar(); mostrar("paso-fotos");
};

function dibujar() {
  $("poses").innerHTML = POSES.slice(0, N).map((p, i) => `<div class=pose><b>${i + 1}. ${p}</b>` +
    (i < fotos.length ? `<span class=ok>✓</span>` :
     i === fotos.length ? `<button class=sec style="width:auto;margin:0;padding:10px 14px" onclick="tomar()">📷 Tomar</button>` : "") +
    `</div>`).join("");
  $("b-enviar").disabled = fotos.length < N;
}
function tomar() { $("err-fotos").textContent = ""; $("camara").value = ""; $("camara").click(); }

async function reducir(file) {          // la foto viaja reducida (más rápida y liviana)
  const bmp = await createImageBitmap(file);
  const s = Math.min(1, 1280 / Math.max(bmp.width, bmp.height));
  const c = document.createElement("canvas");
  c.width = Math.round(bmp.width * s); c.height = Math.round(bmp.height * s);
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
  return new Promise(res => c.toBlob(res, "image/jpeg", 0.9));
}

if ($("camara")) $("camara").onchange = async e => {
  const f = e.target.files[0]; if (!f) return;
  $("err-fotos").textContent = "Revisando la foto...";
  let blob; try { blob = await reducir(f); } catch (_) { blob = f; }
  const fd = new FormData(); fd.append("foto", blob, "foto.jpg"); fd.append("previos", JSON.stringify(fotos));
  const r = await fetch(`/r/${TOKEN}/foto`, {method: "POST", body: fd});
  const j = await r.json().catch(() => ({error: "Error de conexión"}));
  if (r.ok) { fotos.push({emb: j.emb, firma: j.firma}); $("err-fotos").textContent = ""; }
  else $("err-fotos").textContent = j.error;
  dibujar();
};

if ($("b-enviar")) $("b-enviar").onclick = async () => {
  $("b-enviar").disabled = true;
  const [ok, r] = await enviar();
  if (!ok) { $("err-fotos").textContent = r.error; $("b-enviar").disabled = false; }
};
</script></body></html>"""
