# -*- coding: utf-8 -*-
"""
setup_nodo.py - Instala el nodo de borde en el PC de la portería de un condominio.

ADVERTENCIA: borra y recrea la base local (config.DB_PATH).

Crea la base local (SQLite, aplicando migraciones/), guarda la dirección de la
API y la clave del nodo en nodo.json, migra las cámaras de cameras.json (si
existe) y hace la primera sincronización con la nube (cuentas y licencia).

Uso:
    python setup_nodo.py --clave ugn_xxxxx [--api http://127.0.0.1:5000]
"""

import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import config


def main():
    ap = argparse.ArgumentParser(description="Instala el nodo de Umbral Guardian")
    ap.add_argument("--clave", required=True, help="clave del nodo entregada por el proveedor")
    ap.add_argument("--api", default=config.API_URL, help="dirección de la API central")
    args = ap.parse_args()

    with open(config.NODE_FILE, "w", encoding="utf-8") as f:
        json.dump({"api_url": args.api, "clave_nodo": args.clave}, f, indent=2)
    config.API_URL, config.NODE_KEY = args.api, args.clave
    print(f"[setup] nodo.json guardado (API: {args.api})")

    # base nueva: se borra el archivo y sus anexos del modo WAL
    for sufijo in ("", "-wal", "-shm"):
        if os.path.exists(config.DB_PATH + sufijo):
            os.remove(config.DB_PATH + sufijo)

    from database import DatabaseManager
    db = DatabaseManager()
    if not db.connect():
        sys.exit("[setup] ERROR: no se pudo crear la base local")
    print(f"[setup] Base local creada en {config.DB_PATH}")

    cams_path = os.path.join(BASE_DIR, "cameras.json")
    if os.path.exists(cams_path):
        with open(cams_path, encoding="utf-8") as f:
            cams = json.load(f).get("cameras", [])
        idzona = db.get_or_create_zona("Acceso principal")
        for c in cams:
            w, h = (c.get("resolution") or [1280, 720])[:2]
            db.create_camara(idzona, c.get("location") or c.get("name", "Cámara"),
                             c.get("type", "rtsp"), str(c.get("source", 0)), w, h,
                             c.get("fps", 30), c.get("enabled", True))
        print(f"[setup] {len(cams)} cámaras migradas desde cameras.json")

    # primera sincronización con la nube
    from core import cloud
    try:
        n = cloud.sincronizar(db)
        print(f"[setup] Sincronizado con la nube: {n} cuentas y licencia vigente")
    except cloud.CloudError as e:
        print(f"[setup] ADVERTENCIA: no se pudo sincronizar ({e}). "
              "Se reintentará al iniciar sesión.")
    finally:
        db.disconnect()


if __name__ == "__main__":
    main()
