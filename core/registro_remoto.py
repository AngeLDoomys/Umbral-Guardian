# -*- coding: utf-8 -*-
"""
core/registro_remoto.py - Registro desde el celular, lado del nodo de la portería.

1. El nodo tiene un par de claves X25519 (la privada nunca sale del equipo) y
   publica la pública en la nube.
2. La administración crea una invitación: se guarda aquí y se publica en la nube
   (solo el hash del token, el tipo y el código de la unidad). El enlace o QR
   apunta a la página de registro de la API.
3. El residente o la visita la completa desde su celular, en cualquier lugar;
   la nube guarda el resultado cifrado para este nodo.
4. descargar() trae esos registros, los descifra y los deja como solicitudes
   pendientes de aprobación; la nube los borra al confirmar la recepción.
"""

import base64
import hashlib
import os
from datetime import datetime

import numpy as np

import config
from core import cifrado, cloud


def _ruta_clave() -> str:
    # junto a la base local, fuera de la carpeta del programa
    return os.path.join(os.path.dirname(config.DB_PATH), "registro_privada.pem")


def _clave_privada() -> str:
    ruta = _ruta_clave()
    if not os.path.exists(ruta):
        privada, _ = cifrado.generar_par()
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(privada)
        try:
            os.chmod(ruta, 0o600)
        except OSError:
            pass
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def publicar_clave():
    """Publica (o vuelve a publicar) la clave pública del nodo en la nube."""
    from cryptography.hazmat.primitives import serialization
    priv = serialization.load_pem_private_key(_clave_privada().encode(), password=None)
    pub = priv.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    cloud._request("POST", "/api/nodo/clave-registro", json={"clave_publica": pub})


def url_registro(token: str) -> str:
    return f"{config.API_URL.rstrip('/')}/r/{token}"


def crear_invitacion(db, tipo, idunidad, unidad_codigo, horas, idcuenta=None,
                     idresidente=None, frecuente=False) -> str:
    """Crea la invitación aquí y en la nube. Retorna la URL para el QR o WhatsApp.
    Lanza cloud.CloudError si no hay conexión (sin nube no hay registro remoto).
    Visitas: si el reglamento lo exige (config.VISITA_ROSTRO_OBLIGATORIO), también
    registran su rostro; las frecuentes no tienen fecha de término."""
    publicar_clave()
    frecuente = bool(frecuente) and tipo == "visita"
    idinv, token = db.crear_invitacion(tipo, idunidad, horas, idcuenta, idresidente, frecuente)
    try:
        cloud._request("POST", "/api/nodo/invitaciones", json={
            "token_hash": hashlib.sha256(token.encode()).hexdigest(), "tipo": tipo,
            "id_local": idinv, "unidad": unidad_codigo, "solo_rostro": idresidente is not None,
            "frecuente": frecuente,
            "rostro": tipo == "residente" or bool(config.VISITA_ROSTRO_OBLIGATORIO),
            "consentimiento_version": config.VERSION_CONSENTIMIENTO, "horas": horas})
    except cloud.CloudError:
        db.anular_invitacion(idinv)
        raise
    return url_registro(token)


def _hora_local(iso_utc):
    if not iso_utc:
        return None
    return datetime.fromisoformat(iso_utc).astimezone().replace(tzinfo=None) \
        .isoformat(" ", timespec="seconds")


def descargar(db) -> int:
    """Trae los registros enviados desde celulares y los deja como solicitudes
    pendientes. Retorna cuántos llegaron. Lanza cloud.CloudError sin conexión."""
    envios = cloud._request("GET", "/api/nodo/registros")
    if not envios:
        return 0
    privada = _clave_privada()
    nuevos = 0
    for e in envios:
        try:
            p = cifrado.descifrar(e["paquete"], privada)
        except Exception as ex:   # cifrado con otra clave (nodo reinstalado): no se puede leer
            print(f"[Registro móvil] Envío {e['idenvio']} ilegible, se descarta: {ex}")
            cloud._request("POST", f"/api/nodo/registros/{e['idenvio']}/recibido", json={})
            continue
        inv = db.get_invitacion(p["id_local"])
        if inv is not None and inv["usada"] is None:
            ids = db.guardar_solicitud(inv["idinvitacion"], p["tipo"], p.get("datos") or {},
                                       p.get("consentimiento_version"),
                                       _hora_local(p.get("consentimiento_fecha")))
            for emb_b64 in p.get("embeddings") or []:
                db.add_solicitud_plantilla(
                    ids, np.frombuffer(base64.b64decode(emb_b64), dtype=np.float32), p["modelo"])
            db.completar_solicitud(ids)
            nuevos += 1
        # guardado (o invitación ya inexistente): la nube puede borrarlo
        cloud._request("POST", f"/api/nodo/registros/{e['idenvio']}/recibido", json={})
    return nuevos
