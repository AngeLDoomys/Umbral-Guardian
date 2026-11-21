# -*- coding: utf-8 -*-
"""
Pruebas unitarias PU-01 a PU-12 del plan de pruebas (punto XII del informe).
Ejecutar desde la carpeta del proyecto:  py -m pytest -v tests
No requieren cámaras, GPU ni base de datos.
"""

import json
import os

import numpy as np
import pytest

import config
from core import events
from core import security
from core import plate_utils
from engine import security_engine as se


# ── PU-01 Validación y corrección de patentes chilenas ─────────────────────

class TestPU01Patentes:
    @pytest.mark.parametrize("texto", ["BCDF12", "YC4733", "AB1234"])
    def test_formatos_validos(self, texto):
        assert plate_utils._valid_chilean(texto)

    @pytest.mark.parametrize("texto", ["AEIO12", "ABC123", "AB123", "1234AB", ""])
    def test_formatos_invalidos(self, texto):
        assert not plate_utils._valid_chilean(texto)

    def test_formato_nuevo_no_admite_vocales(self):
        assert not plate_utils._valid_chilean("BCAF12")

    @pytest.mark.parametrize("leido, corregido", [
        ("BCDF1Z", "BCDF12"),   # formato nuevo: Z en posición de dígito
        ("0B1234", "OB1234"),   # formato antiguo: 0 en posición de letra
        ("AB12S4", "AB1254"),   # formato antiguo: S en posición de dígito
    ])
    def test_correccion_por_posicion(self, leido, corregido):
        assert plate_utils._correct_chilean(leido) == corregido

    def test_formato_de_salida(self):
        assert plate_utils._format_chilean("YC4733") == "YC-47-33"

    @pytest.mark.parametrize("texto, salida", [
        ("SGL45", "SGL-45"),    # moto actual LLL·NN (2014-)
        ("AB123", "AB-123"),    # moto antigua LL·NNN
        ("BCDF1", "BCDF-1"),    # moto anunciada para 2027, LLLL·N
    ])
    def test_formatos_de_moto(self, texto, salida):
        assert plate_utils._valid_chilean(texto, moto=True)
        assert plate_utils._format_chilean(texto) == salida

    @pytest.mark.parametrize("texto", ["SGL45", "AB123", "BCDF1"])
    def test_formato_de_moto_no_vale_para_autos(self, texto):
        # una lectura incompleta de un auto (AB1234 -> AB123) no debe aceptarse
        assert not plate_utils._valid_chilean(texto)

    @pytest.mark.parametrize("texto", ["SAL45", "S1L45", "SGLA5", "12345", "SGL4"])
    def test_formatos_de_moto_invalidos(self, texto):
        assert not plate_utils._valid_chilean(texto, moto=True)

    def test_patentes_de_auto_siguen_validas_en_motos(self):
        assert plate_utils._valid_chilean("BCDF12", moto=True)


# ── PU-02 RUT ──────────────────────────────────────────────────────────────

class TestPU02Rut:
    @pytest.mark.parametrize("rut", ["12.345.678-5", "12345678-5", "11111111-1", "6-K", "6-k"])
    def test_rut_valido(self, rut):
        assert security.valid_rut(rut)

    @pytest.mark.parametrize("rut", ["12.345.678-4", "6-1", "", "abc", "1"])
    def test_rut_invalido(self, rut):
        assert not security.valid_rut(rut)

    def test_normalizacion(self):
        assert security.clean_rut("12.345.678-k") == "12345678K"
        assert security.format_rut("12.345.678-k") == "12345678-K"

    def test_enmascarado_para_conserjeria(self):
        assert security.mask_rut("12345678-5") == "12.345.***-*"


# ── PU-03 Contraseñas ──────────────────────────────────────────────────────

class TestPU03Contrasenas:
    def test_verifica_solo_la_clave_correcta(self):
        h = security.hash_password("Portero2026")
        assert security.verify_password("Portero2026", h)
        assert not security.verify_password("portero2026", h)

    def test_hash_con_sal_y_sin_texto_plano(self):
        h1 = security.hash_password("Portero2026")
        h2 = security.hash_password("Portero2026")
        assert h1 != h2                       # sal distinta en cada hash
        assert "Portero2026" not in h1
        assert h1.startswith("pbkdf2_sha256$260000$")

    def test_hash_malformado_no_valida(self):
        assert not security.verify_password("x", "texto-cualquiera")


# ── PU-04 Política de contraseñas ──────────────────────────────────────────

class TestPU04PoliticaContrasenas:
    @pytest.mark.parametrize("clave", ["abc12", "solamenteletras", "1234567890"])
    def test_rechaza_claves_debiles(self, clave):
        assert security.password_problem(clave) is not None

    def test_acepta_clave_aceptable(self):
        assert security.password_problem("Conserje2026") is None


# ── PU-05 Normalización de patentes para búsqueda ──────────────────────────

class TestPU05NormalizacionPatentes:
    @pytest.mark.parametrize("entrada", ["yc-47-33", "YC 47 33", "YC4733", "yc-4733"])
    def test_misma_clave_de_busqueda(self, entrada):
        assert security.clean_plate(entrada) == "YC4733"


# ── PU-06 Medidor de latencias ─────────────────────────────────────────────

class TestPU06LatencyMeter:
    def test_estadisticas(self):
        m = se.LatencyMeter()
        for ms in range(1, 101):
            m.add("deteccion", float(ms))
        s = m.summary("deteccion")
        assert s["avg"] == pytest.approx(50.5)
        assert s["p95"] == pytest.approx(95.05)
        assert s["max"] == 100.0

    def test_ventana_movil_de_200_muestras(self):
        m = se.LatencyMeter()
        for ms in range(300):
            m.add("frame_total", float(ms))
        s = m.summary("frame_total")
        assert s["n"] == 200
        assert s["max"] == 299.0

    def test_etapa_sin_muestras(self):
        assert se.LatencyMeter().summary("ocr") is None


# ── PU-07 Asociación placa → vehículo ──────────────────────────────────────

class TestPU07GetCar:
    TRACKS = np.array([[100, 100, 400, 300, 7], [500, 100, 800, 300, 8]], dtype=float)

    def test_placa_dentro_de_un_vehiculo(self):
        *_, cid = plate_utils.get_car((200, 250, 280, 280, 0.9, 0), self.TRACKS)
        assert cid == 7

    def test_placa_fuera_de_todo_vehiculo(self):
        *_, cid = plate_utils.get_car((420, 250, 480, 280, 0.9, 0), self.TRACKS)
        assert cid == -1

    def test_placa_que_sobresale_del_vehiculo(self):
        *_, cid = plate_utils.get_car((350, 250, 450, 280, 0.9, 0), self.TRACKS)
        assert cid == -1


# ── PU-08 Votación de patentes ─────────────────────────────────────────────

class TestPU08VotacionPatentes:
    BOX = (10, 10, 50, 30)

    def test_dos_lecturas_iguales_confirman(self):
        eng = se.SecurityEngine()
        eng._vote_plate("YC-47-33", 0.99, 1, self.BOX, 1)
        assert 1 not in eng._vehicle_data
        eng._vote_plate("YC-47-33", 0.98, 1, self.BOX, 2)
        assert eng._vehicle_data[1]["plate"] == "YC-47-33"
        assert "SIN CONFIRMAR" not in eng._vehicle_data[1]["label"]

    def test_lecturas_en_conflicto_gana_la_mayoria(self):
        eng = se.SecurityEngine()
        for p in ("AB-12-34", "AB-12-84", "AB-12-34"):
            eng._vote_plate(p, 0.9, 2, self.BOX, 1)
        assert eng._vehicle_data[2]["plate"] == "AB-12-34"

    def test_sin_consenso_se_informa_sin_confirmar(self):
        eng = se.SecurityEngine()
        lecturas = ["AB-12-3" + str(i) for i in range(config.PLATE_MAX_READS)]
        for p in lecturas:
            eng._vote_plate(p, 0.9, 3, self.BOX, 1)
        assert "SIN CONFIRMAR" in eng._vehicle_data[3]["label"]
        assert eng._vehicle_data[3]["status"] == "no_registrado"

    def test_patente_sin_confirmar_nunca_es_autorizada(self):
        eng = se.SecurityEngine()
        eng.resident_plates = {"AB1230": {"idvehiculo": 1, "unidad": "101"}}
        lecturas = ["AB-12-3" + str(i) for i in range(config.PLATE_MAX_READS)]
        for p in lecturas:
            eng._vote_plate(p, 0.9, 4, self.BOX, 1)
        assert eng._vehicle_data[4]["status"] == "no_registrado"


# ── PU-09 Votación facial ──────────────────────────────────────────────────

def _persona():
    return {"bbox": (0, 0, 10, 10), "last_seen": 1, "name": None, "id": None,
            "idresidente": None, "is_registered": False, "color": (150, 150, 150),
            "display_name": "Analizando...", "attempts": 0, "votes": {}, "candidates": {}}


def _match(rid, dist=0.30):
    return {"status": "match", "face": np.zeros((80, 80, 3), np.uint8), "name": f"Residente {rid}",
            "unidad": "101", "idresidente": rid, "confidence": 1 - dist, "distance": dist}


NO_MATCH = {"status": "no_match", "face": np.zeros((80, 80, 3), np.uint8), "distance": 0.8}


class TestPU09VotacionFacial:
    def _ejecutar(self, monkeypatch, resultados):
        eng = se.SecurityEngine()
        eng._person_memory[1] = _persona()
        seq = iter(resultados)
        monkeypatch.setattr(se, "recognize_face", lambda img, known: next(seq))
        for _ in resultados:
            eng._do_recognition(None, 1, 1)
        return eng._person_memory[1]

    def test_dos_coincidencias_confirman_al_residente(self, monkeypatch):
        p = self._ejecutar(monkeypatch, [_match(5), _match(5)])
        assert p["is_registered"] and p["idresidente"] == 5

    def test_una_coincidencia_no_basta(self, monkeypatch):
        p = self._ejecutar(monkeypatch, [_match(5)])
        assert p["name"] is None and p["display_name"].startswith("Analizando")

    def test_sin_coincidencias_es_no_reconocido(self, monkeypatch):
        p = self._ejecutar(monkeypatch, [NO_MATCH] * config.FACE_MAX_ATTEMPTS)
        assert p["name"] == "No reconocido" and not p["is_registered"]

    def test_mayoria_de_dos_a_uno_confirma(self, monkeypatch):
        p = self._ejecutar(monkeypatch, [_match(5), _match(6), _match(5)])
        assert p["idresidente"] == 5

    def test_sin_mayoria_clara_no_confirma(self, monkeypatch):
        # 2 votos al residente 5 frente a 2 coincidencias con otros: no hay mayoría de 2 a 1
        res = [_match(5), _match(6), _match(7), _match(5), NO_MATCH]
        p = self._ejecutar(monkeypatch, res)
        assert p["name"] == "No reconocido"

    def test_no_reconocido_se_corrige_con_dos_coincidencias_posteriores(self, monkeypatch):
        # entra de perfil (5 intentos sin coincidencia) y luego se ve de frente
        res = [NO_MATCH] * config.FACE_MAX_ATTEMPTS + [_match(5), _match(5)]
        eng = se.SecurityEngine()
        eng._person_memory[1] = _persona()
        seq = iter(res)
        monkeypatch.setattr(se, "recognize_face", lambda img, known: next(seq))
        for _ in res:
            eng._do_recognition(None, 1, 1)
        p = eng._person_memory[1]
        assert p["is_registered"] and p["idresidente"] == 5
        assert eng._stats["faces_unknown"] == 1 and eng._stats["faces_registered"] == 1

    def test_no_reconocido_no_cambia_con_una_sola_coincidencia(self, monkeypatch):
        p = self._ejecutar(monkeypatch, [NO_MATCH] * config.FACE_MAX_ATTEMPTS + [_match(5)])
        assert p["name"] == "No reconocido"

    def test_revision_sin_coincidencia_no_repite_el_evento(self, monkeypatch):
        res = [NO_MATCH] * (config.FACE_MAX_ATTEMPTS + 3)
        eng = se.SecurityEngine()
        eng._person_memory[1] = _persona()
        seq = iter(res)
        monkeypatch.setattr(se, "recognize_face", lambda img, known: next(seq))
        for _ in res:
            eng._do_recognition(None, 1, 1)
        assert eng._stats["faces_unknown"] == 1

    def test_rostro_de_mala_calidad_no_cuenta_como_intento(self, monkeypatch):
        malo = {"status": "low_quality", "face": None, "reason": "borroso (12)"}
        p = self._ejecutar(monkeypatch, [malo, malo])
        assert p["attempts"] == 0


# ── PU-13 Seguimiento de personas (asignación de identidades) ──────────────

class TestPU13SeguimientoPersonas:
    @staticmethod
    def _mem(**personas):
        return {pid: {"bbox": b, "last_seen": 1} for pid, b in personas.items()}

    def test_dos_personas_juntas_conservan_su_identidad(self):
        from core.face_utils import assign_person_ids
        # A y B a menos de 80 px: con la función anterior, ambas detecciones podían
        # quedar asignadas a la primera persona de la memoria
        mem = self._mem(A=(100, 100, 200, 400), B=(170, 100, 270, 400))
        dets = [(175, 102, 275, 402), (102, 101, 202, 401)]   # B y A, en otro orden
        assert assign_person_ids(dets, mem, [10]) == ["B", "A"]

    def test_una_persona_no_recibe_dos_detecciones(self):
        from core.face_utils import assign_person_ids
        mem = self._mem(A=(100, 100, 200, 400))
        ids = assign_person_ids([(100, 100, 200, 400), (130, 100, 230, 400)], mem, [5])
        assert ids[0] == "A" and ids[1] == "P5"

    def test_persona_nueva_recibe_identificador_nuevo(self):
        from core.face_utils import assign_person_ids
        mem = self._mem(A=(100, 100, 200, 400))
        assert assign_person_ids([(600, 100, 700, 400)], mem, [7]) == ["P7"]

    def test_movimiento_brusco_sin_superposicion_usa_cercania(self):
        from core.face_utils import assign_person_ids
        mem = self._mem(A=(100, 100, 150, 200))
        assert assign_person_ids([(160, 120, 210, 220)], mem, [1]) == ["A"]

    def test_al_cruzarse_no_intercambian_identidad(self):
        from core.face_utils import assign_person_ids
        # A camina a la derecha y B a la izquierda, 20 px por cuadro. 5 cuadros
        # después A está donde estaba el borde de B y viceversa: comparando con la
        # última posición vista se intercambiarían; con la predicha, no
        mem = {"A": {"bbox": (100, 100, 200, 400), "last_seen": 1, "vel": (20, 0, 20, 0)},
               "B": {"bbox": (260, 100, 360, 400), "last_seen": 1, "vel": (-20, 0, -20, 0)}}
        dets = [(200, 100, 300, 400), (160, 100, 260, 400)]
        assert assign_person_ids(dets, mem, [9]) == ["B", "A"]            # sin predicción: cruzados
        assert assign_person_ids(dets, mem, [9], current_frame=6) == ["A", "B"]

    def test_etiqueta_larga_cabe_en_la_imagen_y_sin_acentos(self):
        from core.face_utils import draw_persons, texto_video
        assert texto_video("Analizando: rostro pequeño") == "Analizando: rostro pequeno"
        frame = np.zeros((288, 352, 3), np.uint8)
        mem = {"A": {"bbox": (280, 80, 350, 280), "last_seen": 1, "color": (0, 255, 0),
                     "display_name": "Matías Ignacio Tejada Carrizo (Avellano 14)"}}
        draw_persons(frame, mem, current_frame=1, max_age=10)
        fondo = frame[50, :, 1] > 0          # franja verde de la etiqueta
        assert fondo[2] and fondo[349]       # de borde a borde, sin salirse

    def test_no_se_dibujan_recuadros_de_personas_que_ya_no_se_ven(self):
        from core.face_utils import draw_persons
        frame = np.zeros((300, 300, 3), np.uint8)
        mem = {"A": {"bbox": (10, 50, 100, 200), "last_seen": 1, "color": (0, 255, 0),
                     "display_name": "Fantasma"}}
        draw_persons(frame, mem, current_frame=100, max_age=10)
        assert frame.sum() == 0


# ── PU-10 Escalado de recuadros entre canales (doble stream) ───────────────

class TestPU10ScaleBox:
    def test_escala_con_margen(self):
        assert se._scale_box((10, 10, 20, 20), 2.0, 2.0, 0.10, 100, 100) == (18, 18, 42, 42)

    def test_no_sale_de_la_imagen(self):
        assert se._scale_box((0, 0, 10, 10), 1.0, 1.0, 0.50, 8, 8) == (0, 0, 8, 8)


# ── PU-11 Aviso de cambios de datos a los motores ──────────────────────────

class TestPU11AvisoDeCambios:
    def test_escrituras_avisan_a_los_motores(self):
        from database import DatabaseManager
        db = DatabaseManager()
        db._exec = lambda *a, **k: 1      # sin base de datos real
        v0 = events.data_version()
        db.create_vehiculo(1, "YC-47-33")
        db.set_bloqueo(1, True)
        db.marcar_salida(1)
        assert events.data_version() == v0 + 3

    def test_lecturas_no_avisan(self):
        from database import DatabaseManager
        db = DatabaseManager()
        db._query = lambda *a, **k: []
        v0 = events.data_version()
        db.list_vehiculos()
        assert events.data_version() == v0


# ── PU-12 Recarga de la configuración en caliente ──────────────────────────

class TestPU12RecargaConfiguracion:
    def test_reload_restablece_y_aplica_settings(self):
        original = config.PROCESS_EVERY_N_FRAMES
        config.PROCESS_EVERY_N_FRAMES = 999
        config.reload()
        assert config.PROCESS_EVERY_N_FRAMES == original

    def test_rutas_de_modelos_resueltas_en_la_carpeta_modelos(self):
        config.reload()
        for ruta in (config.DETECTOR_MODEL, config.PLATE_DETECTOR_MODEL):
            assert os.path.dirname(ruta) == config.MODELS_DIR
            assert ruta.endswith(".onnx")
