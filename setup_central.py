# -*- coding: utf-8 -*-
"""
setup_central.py - Instala la base CENTRAL de la nube (servidor del proveedor).

ADVERTENCIA: borra y recrea la base 'umbral_central'.

Crea: la base central, el secreto de sesiones, el par de claves de licencias
(la privada queda en servidor/, la pública se copia junto al programa) y la
cuenta del proveedor. Con --demo crea además el condominio de validación con
su administrador, su conserje y la clave de su nodo.

Uso:
    python setup_central.py --demo
    python setup_central.py --email yo@proveedor.cl --password Clave1234
"""

import argparse
import hashlib
import os
import secrets
import string
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import mysql.connector

import config
from core import licencia
from core.security import hash_password, password_problem
from servidor import config_servidor as cfg


def _random_password() -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(12))
        if password_problem(pwd) is None:
            return pwd


def run_sql_file(cur, path):
    with open(path, encoding="utf-8") as f:
        lines = [l for l in f if not l.lstrip().startswith("--")]
    for stmt in "".join(lines).split(";"):
        if stmt.strip():
            cur.execute(stmt)


def _cuenta(cur, idcondominio, rol, rut, nombres, apellidos, email, password):
    cur.execute("""
        INSERT INTO cuenta (idcondominio, idrol, rut, nombres, apellidos, email, password_hash)
        VALUES (%s, (SELECT idrol FROM rol WHERE nombre = %s), %s, %s, %s, %s, %s)
    """, (idcondominio, rol, rut, nombres, apellidos, email, hash_password(password)))


def main():
    ap = argparse.ArgumentParser(description="Instala la base central de Umbral Guardian")
    ap.add_argument("--email", default="proveedor@umbralguardian.cl")
    ap.add_argument("--password", default=None)
    ap.add_argument("--demo", action="store_true", help="crear condominio de demostración")
    args = ap.parse_args()

    pwd = args.password or _random_password()
    if password_problem(pwd):
        sys.exit(f"[setup] {password_problem(pwd)}")

    # secreto de sesiones y claves de licencia
    with open(cfg.SECRET_FILE, "w", encoding="utf-8") as f:
        f.write(secrets.token_urlsafe(48))
    licencia.generar_claves(cfg.PRIVATE_KEY_FILE, config.LICENSE_PUBLIC_KEY)
    print(f"[setup] Claves de licencia generadas (pública: {config.LICENSE_PUBLIC_KEY})")

    db = cfg.CENTRAL_DB
    conn = mysql.connector.connect(host=db["host"], port=db["port"], user=db["user"],
                                   password=db["password"])
    cur = conn.cursor()
    creds, clave_nodo = [], None
    try:
        run_sql_file(cur, os.path.join(BASE_DIR, "sql", "central.sql"))
        _cuenta(cur, None, "superadmin", "11111111-1", "Proveedor", "Umbral Guardian",
                args.email.lower(), pwd)
        creds.append(("superadmin", args.email.lower(), pwd))

        if args.demo:
            cur.execute("""
                INSERT INTO condominio (rut, nombre, direccion, comuna, email_contacto)
                VALUES ('53321807-5', 'Condominio Parque Fray Jorge', 'La Serena',
                        'La Serena', 'condominiofrayjorge.ad@gmail.com')
            """)
            idc = cur.lastrowid
            cur.execute("""
                INSERT INTO suscripcion (idcondominio, idplan, fecha_inicio, fecha_fin)
                VALUES (%s, (SELECT idplan FROM plan WHERE nombre = 'Básico'),
                        CURDATE(), DATE_ADD(CURDATE(), INTERVAL %s DAY))
            """, (idc, cfg.DIAS_PRUEBA))
            for rol, email, nombre in [("administrador", "admin@frayjorge.cl", "Administrador"),
                                       ("conserje", "conserje@frayjorge.cl", "Conserje")]:
                p = _random_password()
                _cuenta(cur, idc, rol, "11111111-1", nombre, "Demo", email, p)
                creds.append((rol, email, p))
            clave_nodo = "ugn_" + secrets.token_urlsafe(32)
            cur.execute("INSERT INTO nodo (idcondominio, nombre, clave_hash) VALUES (%s, %s, %s)",
                        (idc, "Portería", hashlib.sha256(clave_nodo.encode()).hexdigest()))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    print(f"\n[setup] Base central '{db['database']}' creada en {db['host']}:{db['port']}")
    print("[setup] Cuentas (guarde estas contraseñas, no se vuelven a mostrar):")
    for rol, email, p in creds:
        print(f"    {rol:<14} {email:<32} {p}")
    if clave_nodo:
        print("\n[setup] Clave del nodo de la portería (se usa en setup_nodo.py):")
        print(f"    {clave_nodo}")


if __name__ == "__main__":
    main()
