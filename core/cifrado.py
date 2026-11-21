# -*- coding: utf-8 -*-
"""
core/cifrado.py - Cifrado de los registros hechos desde el celular.

El nodo de la portería tiene un par de claves X25519 y entrega a la nube solo la
pública. La nube cifra cada registro (datos del formulario y vectores del rostro)
para ese nodo: X25519 efímero + HKDF-SHA256 + AES-256-GCM. Sin la clave privada,
que nunca sale del equipo del condominio, la nube no puede leer lo que guarda.
"""

import base64
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_INFO = b"umbral-guardian/registro-movil/v1"


def generar_par() -> tuple:
    """(privada_pem, publica_pem) como texto."""
    priv = X25519PrivateKey.generate()
    priv_pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()).decode()
    pub_pem = priv.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv_pem, pub_pem


def _clave(compartido: bytes, efimera: bytes, destino: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=efimera + destino,
                info=_INFO).derive(compartido)


def cifrar(datos: dict, publica_pem: str) -> str:
    """Cifra un dict para el dueño de `publica_pem`. Retorna texto base64."""
    destino = serialization.load_pem_public_key(publica_pem.encode())
    if not isinstance(destino, X25519PublicKey):
        raise ValueError("La clave pública no es X25519")
    efimera = X25519PrivateKey.generate()
    ef_pub = efimera.public_key().public_bytes(serialization.Encoding.Raw,
                                               serialization.PublicFormat.Raw)
    dst_raw = destino.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    clave = _clave(efimera.exchange(destino), ef_pub, dst_raw)
    nonce = os.urandom(12)
    texto = json.dumps(datos, ensure_ascii=False).encode()
    return base64.b64encode(ef_pub + nonce + AESGCM(clave).encrypt(nonce, texto, _INFO)).decode()


def descifrar(paquete_b64: str, privada_pem: str) -> dict:
    """Inverso de cifrar(). Lanza una excepción si el paquete fue alterado."""
    priv = serialization.load_pem_private_key(privada_pem.encode(), password=None)
    raw = base64.b64decode(paquete_b64)
    ef_pub, nonce, cuerpo = raw[:32], raw[32:44], raw[44:]
    dst_raw = priv.public_key().public_bytes(serialization.Encoding.Raw,
                                             serialization.PublicFormat.Raw)
    clave = _clave(priv.exchange(X25519PublicKey.from_public_bytes(ef_pub)), ef_pub, dst_raw)
    return json.loads(AESGCM(clave).decrypt(nonce, cuerpo, _INFO).decode())
