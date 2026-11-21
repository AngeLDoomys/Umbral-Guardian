# -*- coding: utf-8 -*-
"""
servidor/restablecer_clave.py - Recuperación de contraseñas (se ejecuta EN EL SERVIDOR).

Solo quien tiene acceso al servidor y a la base central puede usarlo; por eso
sirve para recuperar la cuenta del proveedor o del único administrador de un
condominio. Genera una contraseña temporal (que debe cambiarse al iniciar sesión)
y reactiva la cuenta. Para el resto de los casos, el proveedor y el administrador
la restablecen desde el programa.

Uso:
    python -m servidor.restablecer_clave --listar
    python -m servidor.restablecer_clave admin@frayjorge.cl
    python -m servidor.restablecer_clave admin@frayjorge.cl --password NuevaClave123
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.security import password_problem, temporary_password
from servidor.central_db import CentralDB


def main():
    ap = argparse.ArgumentParser(description="Restablece la contraseña de una cuenta")
    ap.add_argument("email", nargs="?", help="correo de la cuenta")
    ap.add_argument("--password", help="nueva contraseña (si se omite, se genera una)")
    ap.add_argument("--listar", action="store_true", help="listar cuentas existentes")
    args = ap.parse_args()

    with CentralDB() as db:
        db.asegurar_esquema()
        if args.listar or not args.email:
            for c in db._q("""
                SELECT c.email, r.nombre AS rol, c.activa, co.nombre AS condominio
                FROM cuenta c JOIN rol r ON r.idrol = c.idrol
                LEFT JOIN condominio co ON co.idcondominio = c.idcondominio
                ORDER BY co.nombre, r.idrol
            """):
                estado = "activa" if c["activa"] else "INACTIVA"
                print(f"  {c['email']:<34} {c['rol']:<14} {estado:<9} "
                      f"{c['condominio'] or '(proveedor)'}")
            return

        cuenta = db.cuenta_por_email(args.email.strip().lower())
        if not cuenta:
            sys.exit(f"No existe una cuenta con el correo {args.email}")
        pwd = args.password or temporary_password()
        problema = password_problem(pwd)
        if problema:
            sys.exit(problema)
        db.cambiar_password(cuenta["idcuenta"], pwd, temporal=True)
        db.activar_cuenta(cuenta["idcuenta"], True)

    print(f"Contraseña temporal para {cuenta['email']} ({cuenta['rol']}): {pwd}")
    print("Deberá cambiarla al iniciar sesión.")
    if cuenta["rol"] != "superadmin":
        print("En la portería, inicie sesión con internet para que el equipo reciba la "
              "clave nueva (hasta entonces, sin conexión sigue valiendo la anterior).")


if __name__ == "__main__":
    main()
