# -*- coding: utf-8 -*-
"""
core/session.py - Inicio de sesión híbrido y verificación de la licencia.

1. Con internet: la API central valida la cuenta y la suscripción, y entrega una
   licencia firmada que se guarda en la base local junto con las cuentas.
2. Sin internet: se valida contra la copia local de las cuentas y la última
   licencia firmada, siempre que la última sincronización tenga menos de
   DIAS_SIN_CONEXION días.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

import config
from core import cloud, licencia
from core.security import verify_password

ROL_SUPERADMIN = "superadmin"
ROL_ADMIN = "administrador"
ROL_CONSERJE = "conserje"


@dataclass
class Session:
    idcuenta: int
    nombre: str
    email: str
    rol: str
    idcondominio: Optional[int]
    token: Optional[str] = None        # None cuando se inició sin conexión
    condominio: str = ""
    plan: str = ""
    max_camaras: int = 0
    vence: Optional[date] = None
    en_gracia: bool = False
    debe_cambiar_password: bool = False   # contraseña temporal: cambiarla antes de seguir

    @property
    def is_superadmin(self) -> bool:
        return self.rol == ROL_SUPERADMIN

    @property
    def is_admin(self) -> bool:
        return self.rol == ROL_ADMIN

    @property
    def offline(self) -> bool:
        return self.token is None

    @property
    def dias_restantes(self) -> Optional[int]:
        return (self.vence - date.today()).days if self.vence else None


# sesión activa (una por ejecución del programa)
current: Optional[Session] = None


class LoginError(Exception):
    pass


def _aplicar_licencia(s: Session, db):
    """Verifica firma, condominio y vigencia de la licencia guardada en la base local."""
    row = db.get_licencia()
    if not row:
        raise LoginError("Este equipo aún no se sincroniza con la nube.\n"
                         "Conéctelo a internet para el primer inicio de sesión.")
    lic = licencia.verificar(row["contenido"], row["firma"], config.LICENSE_PUBLIC_KEY)
    if lic is None:
        raise LoginError("La licencia del equipo es inválida o fue alterada.")
    if s.idcondominio is not None and lic["idcondominio"] != s.idcondominio:
        raise LoginError("La licencia no corresponde al condominio de la cuenta.")
    if lic["estado"] != "activa" or not lic["fecha_fin"]:
        raise LoginError("El condominio no tiene una suscripción activa.\n"
                         "Contacte al proveedor de Umbral Guardian.")
    vence = date.fromisoformat(lic["fecha_fin"])
    if date.today() > vence + timedelta(days=lic["dias_gracia"]):
        raise LoginError(f"La suscripción venció el {vence:%d/%m/%Y}.\n"
                         "Regularice el pago para seguir usando el sistema.")
    s.idcondominio = lic["idcondominio"]
    s.condominio, s.plan, s.max_camaras = lic["condominio"], lic["plan"], lic["max_camaras"]
    s.vence, s.en_gracia = vence, date.today() > vence


def login(db, email: str, password: str) -> Session:
    """db: base local (puede ser None para la cuenta del proveedor)."""
    global current
    email = email.strip().lower()
    try:
        data = cloud.login(email, password)
    except cloud.CloudUnavailable:
        current = _login_sin_conexion(db, email, password)
        return current
    except cloud.CloudError as e:
        raise LoginError(str(e))

    c = data["cuenta"]
    s = Session(idcuenta=c["idcuenta"], nombre=c["nombre"], email=c["email"], rol=c["rol"],
                idcondominio=c["idcondominio"], token=data["token"],
                debe_cambiar_password=bool(c.get("debe_cambiar_password")))
    if not s.is_superadmin:
        if db is None:
            raise LoginError("No hay conexión con la base de datos local del equipo.")
        db.guardar_licencia(data["licencia"]["contenido"], data["licencia"]["firma"])
        try:
            cloud.sincronizar(db)
        except cloud.CloudError as e:
            print(f"[Sesión] No se pudieron sincronizar las cuentas: {e}")
        _aplicar_licencia(s, db)
    current = s
    return s


def _login_sin_conexion(db, email: str, password: str) -> Session:
    if db is None:
        raise LoginError("Sin conexión con la nube ni con la base local.")
    cuenta = db.get_cuenta_local(email)
    if not cuenta or not verify_password(password, cuenta["password_hash"]):
        raise LoginError("Sin conexión con la nube: solo pueden ingresar las cuentas de este "
                         "condominio.\nCorreo o contraseña incorrectos.")
    if not cuenta["activa"]:
        raise LoginError("La cuenta está desactivada.")
    if cuenta["debe_cambiar_password"]:
        raise LoginError("Su contraseña es temporal y debe cambiarla, lo que requiere "
                         "conexión con la nube.\nIntente de nuevo cuando haya internet.")
    row = db.get_licencia()
    if row and datetime.now() - row["verificada_en"] > timedelta(days=config.DIAS_SIN_CONEXION):
        raise LoginError(f"El equipo lleva más de {config.DIAS_SIN_CONEXION} días sin "
                         "conectarse a la nube.\nRestablezca la conexión a internet.")
    s = Session(idcuenta=cuenta["idcuenta"], nombre=f"{cuenta['nombres']} {cuenta['apellidos']}",
                email=cuenta["email"], rol=cuenta["rol"], idcondominio=None)
    _aplicar_licencia(s, db)
    return s


def cambiar_password(actual: str, nueva: str, db=None):
    """Cambia la contraseña de la sesión activa en la nube y actualiza la copia
    local (para que sin conexión valga la nueva). Lanza LoginError si falla."""
    if current is None or current.offline:
        raise LoginError("Cambiar la contraseña requiere conexión con la nube.")
    try:
        cloud.post("/api/cuenta/password", current.token, {"actual": actual, "nueva": nueva})
    except cloud.CloudError as e:
        raise LoginError(str(e))
    current.debe_cambiar_password = False
    if db is not None and not current.is_superadmin:
        try:
            cloud.sincronizar(db)
        except cloud.CloudError as e:
            print(f"[Sesión] Copia local de cuentas pendiente: {e}")


def resincronizar(db) -> Optional[str]:
    """Sincronización periódica. Retorna un mensaje si la licencia dejó de ser válida."""
    if current is None or current.is_superadmin:
        return None
    try:
        cloud.sincronizar(db)
    except cloud.CloudError as e:
        print(f"[Sesión] Sincronización pendiente: {e}")
    try:
        _aplicar_licencia(current, db)
    except LoginError as e:
        return str(e)
    return None
