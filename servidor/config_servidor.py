# -*- coding: utf-8 -*-
"""
servidor/config_servidor.py - Configuración de la API central (se ejecuta en la nube).

En producción (EC2) los valores se entregan por variables de entorno; los de
abajo son los de desarrollo local. Estas credenciales NUNCA van en el programa
que se instala en los condominios.
"""

import os

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))

CENTRAL_DB = {
    "host":     os.getenv("UG_CENTRAL_HOST", "localhost"),
    "port":     int(os.getenv("UG_CENTRAL_PORT", "3306")),
    "user":     os.getenv("UG_CENTRAL_USER", "root"),
    "password": os.getenv("UG_CENTRAL_PASSWORD", ""),
    "database": os.getenv("UG_CENTRAL_DATABASE", "umbral_central"),
}

# secreto para firmar los tokens de sesión (lo genera setup_central.py)
SECRET_FILE = os.path.join(SERVER_DIR, "secreto.key")
# clave privada Ed25519 con la que se firman las licencias de los nodos
PRIVATE_KEY_FILE = os.path.join(SERVER_DIR, "licencia_privada.pem")

TOKEN_HORAS = 12                  # vigencia del token de sesión
DIAS_GRACIA_SUSCRIPCION = 7       # operación permitida tras el vencimiento
DIAS_PRUEBA = 30                  # vigencia inicial al crear un condominio

HOST = os.getenv("UG_API_HOST", "127.0.0.1")
PORT = int(os.getenv("UG_API_PORT", "5000"))
