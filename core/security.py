# -*- coding: utf-8 -*-
"""
core/security.py - Hash de contraseñas (PBKDF2-SHA256) y validación de RUT chileno.
Solo usa la biblioteca estándar.
"""

import hashlib
import hmac
import re
import secrets

_ITERATIONS = 260_000


# ─────────────────────────────────────────────────────────────────────────────
# Contraseñas
# ─────────────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Retorna 'pbkdf2_sha256$iteraciones$sal$hash' (nunca la clave en texto plano)."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(calc.hex(), digest)
    except (ValueError, AttributeError):
        return False


def password_problem(password: str):
    """Retorna un mensaje si la contraseña es débil, o None si es aceptable."""
    if len(password) < 8:
        return "La contraseña debe tener al menos 8 caracteres"
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "La contraseña debe combinar letras y números"
    return None


# sin 0/O, 1/l/I: la contraseña temporal suele dictarse por teléfono o anotarse
_TEMP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def temporary_password(length: int = 10) -> str:
    """Contraseña temporal aleatoria que cumple password_problem. Quien la recibe
    debe cambiarla al iniciar sesión."""
    while True:
        pwd = "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(length))
        if password_problem(pwd) is None:
            return pwd


# ─────────────────────────────────────────────────────────────────────────────
# RUT
# ─────────────────────────────────────────────────────────────────────────────

def clean_rut(rut: str) -> str:
    """'12.345.678-k' -> '12345678K'."""
    return re.sub(r"[^0-9Kk]", "", rut or "").upper()


def _dv(cuerpo: str) -> str:
    total, factor = 0, 2
    for d in reversed(cuerpo):
        total += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    r = 11 - total % 11
    return "0" if r == 11 else "K" if r == 10 else str(r)


def valid_rut(rut: str) -> bool:
    r = clean_rut(rut)
    if len(r) < 2 or not r[:-1].isdigit():
        return False
    return _dv(r[:-1]) == r[-1]


def format_rut(rut: str) -> str:
    """'12345678K' -> '12345678-K' (formato de almacenamiento, sin puntos)."""
    r = clean_rut(rut)
    return f"{r[:-1]}-{r[-1]}" if len(r) >= 2 else r


def mask_rut(rut: str) -> str:
    """'12345678-K' -> '12.345.***-*' para pantallas y reportes generales."""
    r = clean_rut(rut)
    if len(r) < 5:
        return "***"
    cuerpo = r[:-1]
    visible = f"{int(cuerpo[:-3]):,}".replace(",", ".") if cuerpo[:-3] else ""
    return f"{visible}.***-*"


# ─────────────────────────────────────────────────────────────────────────────
# Patentes
# ─────────────────────────────────────────────────────────────────────────────

def clean_plate(plate: str) -> str:
    """'AB-CD-12' -> 'ABCD12'."""
    return re.sub(r"[^A-Z0-9]", "", (plate or "").upper())
