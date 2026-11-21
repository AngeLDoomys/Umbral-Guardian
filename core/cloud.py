# -*- coding: utf-8 -*-
"""
core/cloud.py - Cliente de la API central (nube).

El nodo solo envía a la nube: credenciales de inicio de sesión y operaciones
sobre cuentas. Recibe: licencia firmada y cuentas del condominio (con el hash de
su contraseña, para permitir el inicio de sesión sin conexión).
Nunca envía datos de residentes, rostros ni historial de accesos.
"""

import requests

import config


class CloudError(Exception):
    """La nube respondió con un error (credenciales, permisos, suscripción)."""


class CloudUnavailable(CloudError):
    """No hay conexión con la nube."""


def _request(method: str, path: str, token: str = None, json=None):
    headers = {"X-Nodo-Clave": config.NODE_KEY}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.request(method, config.API_URL.rstrip("/") + path, json=json,
                             headers=headers, timeout=config.API_TIMEOUT_S)
    except requests.RequestException as e:
        raise CloudUnavailable(f"Sin conexión con la nube ({config.API_URL})") from e
    try:
        data = r.json()
    except ValueError:
        raise CloudError(f"Respuesta inválida de la nube (HTTP {r.status_code})")
    if r.status_code >= 400:
        raise CloudError(data.get("error", f"Error HTTP {r.status_code}"))
    return data


def login(email: str, password: str) -> dict:
    return _request("POST", "/api/login", json={"email": email, "password": password})


def sincronizar(db) -> int:
    """Descarga licencia y cuentas del condominio y las guarda en la base local."""
    data = _request("GET", "/api/nodo/sincronizar")
    db.guardar_licencia(data["licencia"]["contenido"], data["licencia"]["firma"])
    db.sincronizar_cuentas(data["cuentas"])
    return len(data["cuentas"])


# ── operaciones con sesión (token) ────────────────────────────────────────

def get(path: str, token: str):
    return _request("GET", path, token)


def post(path: str, token: str, body: dict = None):
    return _request("POST", path, token, body or {})
