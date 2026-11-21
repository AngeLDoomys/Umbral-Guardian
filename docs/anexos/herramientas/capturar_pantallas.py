# -*- coding: utf-8 -*-
"""
Capturas de pantalla para los anexos, sobre una COPIA de la base local con datos ficticios.

    $env:UG_ADMIN_PASS="..."; $env:UG_CONSERJE_PASS="..."
    py docs/anexos/herramientas/capturar_pantallas.py

No modifica la base real. Las contraseñas se leen de variables de entorno y no se guardan.
La nube no se contacta: las vistas que la usan reciben respuestas de ejemplo.
"""
import ctypes
import json
import os
import random
import sqlite3
import sys
import tempfile
import time

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(AQUI, "..", "..", ".."))
SALIDA = os.path.join(AQUI, "..", "capturas")
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import config  # noqa: E402

REAL = config.DB_PATH
DEMO = os.path.join(tempfile.mkdtemp(prefix="ug_demo_"), "umbral_demo.db")

NOMBRES = [("Carolina", "Fuentes Rojas"), ("Diego Andrés", "Muñoz Soto"),
           ("Valentina", "Pérez Lagos"), ("Tomás Ignacio", "Silva Contreras"),
           ("Fernanda", "Castro Díaz"), ("Joaquín", "Morales Vera")]
VISITAS = [("Ricardo", "Herrera Paz"), ("Camila", "Ortiz Núñez"), ("Sebastián", "Vargas Leal")]
PATENTES = ["GHJK21", "LPRS34", "BCDF56", "TWXY78", "KLRT90", "PSHD12", "FGBC45", "JKLP67"]


def rut_valido(numero: int) -> str:
    s, m = 0, 2
    for d in reversed(str(numero)):
        s += int(d) * m
        m = 2 if m == 7 else m + 1
    dv = 11 - s % 11
    dv = "0" if dv == 11 else "K" if dv == 10 else str(dv)
    n = f"{numero:,}".replace(",", ".")
    return f"{n}-{dv}"


def preparar_demo():
    src, dst = sqlite3.connect(REAL), sqlite3.connect(DEMO)
    src.backup(dst)
    src.close()
    c = dst
    random.seed(4)
    ruts = {}
    for i, (rid,) in enumerate(c.execute("SELECT idresidente FROM residente ORDER BY idresidente").fetchall()):
        n, a = NOMBRES[i % len(NOMBRES)]
        ruts[rid] = rut_valido(15_000_000 + 731_000 * (i + 1) + 17)
        c.execute("UPDATE residente SET nombres=?, apellidos=?, rut=?, telefono=?, email=? "
                  "WHERE idresidente=?", (n, a, ruts[rid], f"+56 9 5{i}12 34{i}8",
                                          f"{n.split()[0].lower()}@correo.cl", rid))
    for rid, rut in ruts.items():
        c.execute("UPDATE solicitud_derecho SET rut_titular=? WHERE idresidente=?", (rut, rid))
    vis = c.execute("SELECT idvisitante FROM visitante ORDER BY idvisitante").fetchall()
    for i, (vid,) in enumerate(vis):
        n, a = VISITAS[i % len(VISITAS)]
        c.execute("UPDATE visitante SET nombres=?, apellidos=?, rut=? WHERE idvisitante=?",
                  (n, a, rut_valido(18_200_000 + 513_000 * i + 9), vid))
    reemplazo = {}
    for i, (vid, pat) in enumerate(c.execute("SELECT idvehiculo, patente FROM vehiculo").fetchall()):
        reemplazo[pat] = PATENTES[i]
        c.execute("UPDATE vehiculo SET patente=? WHERE idvehiculo=?", (PATENTES[i], vid))
    leidas = [r[0] for r in c.execute("SELECT DISTINCT patente_leida FROM deteccion_vehiculo")]
    otras = iter(PATENTES[len(reemplazo):])
    for p in leidas:
        c.execute("UPDATE deteccion_vehiculo SET patente_leida=? WHERE patente_leida=?",
                  (reemplazo.get(p) or next(otras, "ZZXY99"), p))
    c.execute("UPDATE visita SET patente=NULL")
    for i, (cid, nombre) in enumerate(c.execute("SELECT idcamara, nombre FROM camara").fetchall()):
        base = f"rtsp://usuario:****@192.168.1.100:554/cam/realmonitor?channel={i + 1}"
        c.execute("UPDATE camara SET fuente=?, fuente_alta=? WHERE idcamara=?",
                  (base + "&subtype=1", base + "&subtype=0", cid))
    # solicitudes de registro: dos pendientes de ejemplo, el resto se elimina
    c.execute("DELETE FROM solicitud_plantilla")
    c.execute("DELETE FROM solicitud_registro")
    unidad = c.execute("SELECT idunidad FROM unidad ORDER BY idunidad").fetchone()[0]
    ahora = time.strftime("%Y-%m-%d %H:%M:%S")
    for tipo, frecuente, datos, fotos in [
            ("residente", 0, {"nombres": "Ignacia", "apellidos": "Reyes Bravo",
                              "rut": rut_valido(19_456_321), "idtipo_residente": 2,
                              "vehiculo": {"patente": "GBKL34", "tipo": "auto", "marca": "Kia",
                                           "modelo": None, "color": "Gris"}}, 5),
            ("visita", 0, {"nombres": "Pablo", "apellidos": "Gómez Ruiz",
                           "rut": rut_valido(17_654_982), "fecha_visita": time.strftime("%Y-%m-%d")}, 5)]:
        c.execute("INSERT INTO invitacion (token_hash, tipo, idunidad, fecha_creacion, vence, usada, "
                  "frecuente) VALUES (?,?,?,?,datetime('now','localtime','+1 day'),?,?)",
                  (f"demo{tipo}", tipo, unidad, ahora, ahora, frecuente))
        inv = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute("INSERT INTO solicitud_registro (idinvitacion, tipo, estado, datos, "
                  "consentimiento_version, consentimiento_fecha, fecha_envio) "
                  "VALUES (?,?,?,?,?,?,?)", (inv, tipo, "pendiente", json.dumps(datos),
                                             config.VERSION_CONSENTIMIENTO, ahora, ahora))
        sol = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        for _ in range(fotos):
            c.execute("INSERT INTO solicitud_plantilla (idsolicitud, embedding, modelo) VALUES (?,?,?)",
                      (sol, np.random.rand(128).astype(np.float32).tobytes(), config.FACE_MODEL))
    # dos visitas autorizadas: una frecuente y una de hoy
    for (n, a), frec in zip(VISITAS[1:], (1, 0)):
        c.execute("INSERT INTO visitante (rut, nombres, apellidos) VALUES (?,?,?)",
                  (rut_valido(16_100_000 + frec * 977_000), n, a))
        vt = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute("INSERT INTO visita_autorizada (idvisitante, idunidad, frecuente, fecha_desde, "
                  "fecha_hasta, consentimiento_version, consentimiento_fecha, fecha_aprobacion) "
                  "VALUES (?,?,?,date('now','localtime'),?,?,?,?)",
                  (vt, unidad, frec, None if frec else time.strftime("%Y-%m-%d"),
                   config.VERSION_CONSENTIMIENTO, ahora, ahora))
        au = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        for _ in range(5):
            c.execute("INSERT INTO plantilla_visita (idautorizacion, embedding, modelo) VALUES (?,?,?)",
                      (au, np.random.rand(128).astype(np.float32).tobytes(), config.FACE_MODEL))
    c.commit()
    c.close()


def capturar(ventana, nombre):
    """Captura solo esa ventana (aunque esté detrás de otras)."""
    import win32gui
    import win32ui
    from PIL import Image
    ventana.update()
    time.sleep(0.6)
    ventana.update()
    hwnd = int(ventana.wm_frame(), 16)
    x1, y1, x2, y2 = win32gui.GetWindowRect(hwnd)
    w, h = x2 - x1, y2 - y1
    dc = win32gui.GetWindowDC(hwnd)
    m = win32ui.CreateDCFromHandle(dc)
    s = m.CreateCompatibleDC()
    b = win32ui.CreateBitmap()
    b.CreateCompatibleBitmap(m, w, h)
    s.SelectObject(b)
    ctypes.windll.user32.PrintWindow(hwnd, s.GetSafeHdc(), 2)
    info = b.GetInfo()
    im = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), b.GetBitmapBits(True),
                          "raw", "BGRX", 0, 1)
    win32gui.DeleteObject(b.GetHandle())
    s.DeleteDC()
    m.DeleteDC()
    win32gui.ReleaseDC(hwnd, dc)
    ruta = os.path.join(SALIDA, f"{nombre}.png")
    im.save(ruta)
    print("captura", nombre, im.size)


def main():
    ctypes.windll.user32.SetProcessDPIAware()
    os.makedirs(SALIDA, exist_ok=True)
    preparar_demo()
    config.DB_PATH = DEMO
    config.API_URL = "http://127.0.0.1:9"        # sin nube: ningún dato sale del equipo

    import database
    database.DatabaseManager._schema_checked = False
    from tkinter import messagebox
    for f in ("showinfo", "showwarning", "showerror"):
        setattr(messagebox, f, lambda *a, **k: None)
    from core import cloud, registro_remoto, session
    registro_remoto.descargar = lambda db: 0

    def cuentas(path, token):
        db = database.DatabaseManager()
        db.connect()
        filas = db._query("SELECT idcuenta, nombres, apellidos, email, rol, activa FROM cuenta_local")
        db.disconnect()
        return [dict(f, ultimo_acceso=time.strftime("%Y-%m-%dT%H:%M:%S"),
                     debe_cambiar_password=0) for f in filas]
    cloud.get = cuentas

    from gui.login import LoginWindow
    login = LoginWindow()
    login._email.insert(0, "admin@frayjorge.cl")
    login._password.insert(0, "x" * 12)
    capturar(login, "00_inicio_sesion")
    login.destroy()

    from gui.app import UmbralGuardianApp
    for rol, email, var in (("admin", "admin@frayjorge.cl", "UG_ADMIN_PASS"),
                            ("conserje", "conserje@frayjorge.cl", "UG_CONSERJE_PASS")):
        db = database.DatabaseManager()
        db.connect()
        s = session.login(db, email, os.environ[var])
        db.disconnect()
        s.token = "demo"                         # la vista muestra el estado normal en línea
        app = UmbralGuardianApp()
        app.geometry("1860x960+0+0")
        for i, (key, *_r) in enumerate(app._items):
            app.navigate(key)
            capturar(app, f"{rol}_{i + 1:02d}_{key}")
        if rol == "admin":
            vista = app._views["registro"]
            app.navigate("registro")
            vista._mostrar_qr("https://umbralguardian-mt.duckdns.org/r/EJEMPLO-DE-INVITACION",
                              "Residente nuevo · Avellano 14", "24 horas")
            qr = [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"]
            for w in vista.winfo_children():
                if w.winfo_class() == "Toplevel":
                    qr.append(w)
            capturar(qr[-1], "admin_registro_qr")
            qr[-1].destroy()
            from gui.view_registros import AutorizadasDialog
            dlg = AutorizadasDialog(vista, vista.db)
            capturar(dlg._w, "admin_registro_autorizadas")
            dlg._w.destroy()
            from gui.view_residents import ConsentDialog
            res = app._views["residents"]
            app.navigate("residents")
            filas = res.db.list_residentes()
            cd = ConsentDialog(res, filas[0], filas, res.db, lambda *a: None)
            capturar(cd, "admin_residentes_consentimiento")
            cd.destroy()
        app.destroy()
    print("base de demostración:", DEMO)


if __name__ == "__main__":
    main()
