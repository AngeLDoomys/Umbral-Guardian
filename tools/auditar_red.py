# -*- coding: utf-8 -*-
"""
tools/auditar_red.py - Abre Umbral Guardian registrando qué intenta enviar a la red.

    py tools/auditar_red.py

Usa los eventos de auditoría de Python: destino de cada conexión, módulo que la abrió
y, en las peticiones HTTP, método, ruta, tamaño y NOMBRES de los campos. Nunca guarda
valores, cabeceras, contraseñas, imágenes ni vectores. Las bibliotecas nativas (FFmpeg,
ONNX Runtime) no pasan por aquí: se complementa con la lista de conexiones del proceso.
"""
import atexit
import ipaddress
import json
import os
import runpy
import sys
import threading
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(ROOT, "tests", "evidencias", "rfdetr_sface", "PS-05_auditoria.json")
METODOS = (b"GET ", b"POST ", b"PUT ", b"PATCH ", b"DELETE ", b"HEAD ")
# campos o contenidos que el monitoreo no debe enviar a la nube
PROHIBIDOS = ("embedding", "vector", "plantilla", "rostro", "foto", "imagen", "image",
              "frame", "video", "patente", "placa", "rut", "deteccion")


class Auditor:
    def __init__(self, salida):
        self.salida = salida
        self.inicio = time.strftime("%Y-%m-%d %H:%M:%S")
        self.destinos = Counter()
        self.nombres = Counter()
        self.peticiones = {}
        self.ultima = {}
        self.binarios = 0
        self._lock = threading.Lock()
        self._local = threading.local()

    @staticmethod
    def _origen():
        """Primer archivo del proyecto en la pila: quién pidió la conexión."""
        f = sys._getframe(2)
        while f:
            ruta = os.path.abspath(f.f_code.co_filename)
            if ruta.startswith(ROOT) and not ruta.endswith("auditar_red.py"):
                return os.path.relpath(ruta, ROOT).replace("\\", "/")
            f = f.f_back
        return "(biblioteca)"

    @staticmethod
    def _tipo(host):
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return "nombre"
        if ip.is_loopback:
            return "este equipo"
        return "red local" if ip.is_private else "internet"

    @classmethod
    def _claves(cls, valor, salida):
        if isinstance(valor, dict):
            for k, v in valor.items():
                salida.add(str(k))
                cls._claves(v, salida)
        elif isinstance(valor, list):
            for v in valor[:50]:
                cls._claves(v, salida)

    def _http(self, conn, data):
        if isinstance(data, str):
            data = data.encode("utf-8", "replace")
        if not isinstance(data, (bytes, bytearray)):
            return
        data = bytes(data)
        host = f"{getattr(conn, 'host', '?')}:{getattr(conn, 'port', '?')}"
        if data.startswith(METODOS):
            cabecera, _, cuerpo = data.partition(b"\r\n\r\n")
            metodo, ruta = cabecera.split(b"\r\n", 1)[0].decode("latin-1").split(" ")[:2]
            ruta = ruta.split("?", 1)[0]
            # los tokens de invitación no se guardan
            ruta = "/r/<token>" if ruta.startswith("/r/") else ruta
            self.ultima[id(conn)] = f"{metodo} {host}{ruta}"
            data = cuerpo
        clave = self.ultima.get(id(conn))
        if clave is None:
            return
        p = self.peticiones.setdefault(clave, {"veces": 0, "bytes_max": 0, "campos": set()})
        if not data:
            p["veces"] += 1
            return
        p["veces"] += 1
        p["bytes_max"] = max(p["bytes_max"], len(data))
        if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n":
            self.binarios += 1
        try:
            campos = set()
            self._claves(json.loads(data), campos)
            p["campos"] |= campos
        except ValueError:
            p["campos"].add("(cuerpo no JSON)")

    def __call__(self, evento, args):
        if evento not in ("socket.connect", "socket.getaddrinfo", "socket.sendto",
                          "http.client.send"):
            return
        if getattr(self._local, "dentro", False):
            return
        self._local.dentro = True
        try:
            with self._lock:
                if evento == "http.client.send":
                    self._http(args[0], args[1])
                elif evento == "socket.getaddrinfo":
                    self.nombres[f"{args[0]} <- {self._origen()}"] += 1
                else:
                    dir_ = args[1]
                    if isinstance(dir_, tuple) and len(dir_) >= 2:
                        host = str(dir_[0])
                        self.destinos[f"{self._tipo(host)} | {host}:{dir_[1]} <- {self._origen()}"] += 1
        except Exception:
            pass     # la auditoría nunca debe interrumpir al programa
        finally:
            self._local.dentro = False

    def guardar(self):
        with self._lock:
            peticiones = {k: {"veces": v["veces"], "bytes_max": v["bytes_max"],
                              "campos": sorted(v["campos"])} for k, v in self.peticiones.items()}
            alertas = sorted({f"{k}: {c}" for k, v in peticiones.items() for c in v["campos"]
                              if any(p in c.lower() for p in PROHIBIDOS)})
            datos = {"inicio": self.inicio, "fin": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "conexiones": dict(self.destinos), "nombres_resueltos": dict(self.nombres),
                     "peticiones_http": peticiones, "campos_sensibles": alertas,
                     "cuerpos_con_imagen": self.binarios}
        temporal = self.salida + ".tmp"
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        os.replace(temporal, self.salida)
        return datos


def instalar(salida=SALIDA, cada_s=15):
    auditor = Auditor(salida)
    sys.addaudithook(auditor)
    atexit.register(auditor.guardar)

    def periodico():
        while True:
            time.sleep(cada_s)
            try:
                auditor.guardar()
            except OSError:
                pass
    threading.Thread(target=periodico, daemon=True).start()
    return auditor


if __name__ == "__main__":
    instalar()
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)
    sys.argv = [os.path.join(ROOT, "main.py")]
    runpy.run_path(sys.argv[0], run_name="__main__")
