# -*- coding: utf-8 -*-
"""
core/licencia.py - Licencia de uso firmada con Ed25519.

La API (nube) firma con su clave privada el estado de la suscripción del
condominio; el nodo de la portería la verifica con la clave pública incluida en
el programa. Así puede operar sin internet durante el período de gracia, pero
nadie puede editar la licencia para extender la vigencia.
"""

import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)


def generar_claves(ruta_privada: str, ruta_publica: str):
    privada = Ed25519PrivateKey.generate()
    with open(ruta_privada, "wb") as f:
        f.write(privada.private_bytes(serialization.Encoding.PEM,
                                      serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    with open(ruta_publica, "wb") as f:
        f.write(privada.public_key().public_bytes(serialization.Encoding.PEM,
                                                  serialization.PublicFormat.SubjectPublicKeyInfo))


def firmar(datos: dict, ruta_privada: str) -> dict:
    """Retorna {'contenido': json, 'firma': base64} listo para enviar al nodo."""
    with open(ruta_privada, "rb") as f:
        privada = serialization.load_pem_private_key(f.read(), password=None)
    contenido = json.dumps(datos, sort_keys=True, ensure_ascii=False)
    firma = base64.b64encode(privada.sign(contenido.encode())).decode()
    return {"contenido": contenido, "firma": firma}


def verificar(contenido: str, firma: str, ruta_publica: str):
    """Retorna el dict de la licencia si la firma es válida; None si fue alterada."""
    try:
        with open(ruta_publica, "rb") as f:
            publica: Ed25519PublicKey = serialization.load_pem_public_key(f.read())
        publica.verify(base64.b64decode(firma), contenido.encode())
        return json.loads(contenido)
    except (InvalidSignature, ValueError, OSError):
        return None
