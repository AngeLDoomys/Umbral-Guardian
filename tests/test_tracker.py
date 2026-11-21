# -*- coding: utf-8 -*-
"""Tracker IoU de vehículos (core/tracker.py), que reemplaza a SORT, y su uso en el motor."""

import numpy as np
import pytest

import config
from core.tracker import IoUTracker, iou


def _caja(x, y=400, w=200, h=120, score=0.9):
    return [x, y, x + w, y + h, score]


def _calentar(t, pasadas=3):
    """Las primeras min_hits llamadas informan todo de inmediato (regla de SORT)."""
    for _ in range(pasadas):
        t.update(np.array([_caja(2000, 2000)]))


class TestReglas:
    def test_iou_bajo_0_3_no_es_match(self):
        a = _caja(0)[:4]
        b_justo = [130, 400, 330, 520]          # IoU = 70/330 ≈ 0.21
        assert iou(a, b_justo) < 0.3
        t = IoUTracker()
        id1 = t.update(np.array([_caja(0)]))[0][4]
        id2 = t.update(np.array([_caja(130)]))[0][4]
        assert id1 != id2

    def test_iou_de_0_3_o_mas_es_match(self):
        t = IoUTracker()
        id1 = t.update(np.array([_caja(0)]))[0][4]
        id2 = t.update(np.array([_caja(90)]))[0][4]   # IoU ≈ 0.38
        assert id1 == id2

    def test_vehiculo_nuevo_aparece_en_su_cuarta_deteccion(self):
        t = IoUTracker()
        _calentar(t)
        informados = [len([r for r in t.update(np.array([_caja(2000, 2000), _caja(100 + 10 * i)]))
                           if r[1] < 1000]) for i in range(5)]
        assert informados == [0, 0, 0, 1, 1]

    def test_una_pasada_perdida_conserva_el_id_pero_reinicia_la_racha(self):
        t = IoUTracker()
        _calentar(t)
        for i in range(4):
            r = t.update(np.array([_caja(100 + 10 * i)]))
        vid = r[0][4]
        assert len(t.update(np.empty((0, 5)))) == 0       # no se vio: no se informa
        # al reaparecer la racha parte en 1: se informa de nuevo en la 3.ª detección
        for i in range(2):
            assert len(t.update(np.array([_caja(150 + 10 * i)]))) == 0
        assert t.update(np.array([_caja(170)]))[0][4] == vid

    def test_dos_pasadas_perdidas_eliminan_el_track(self):
        t = IoUTracker()
        t.update(np.array([_caja(100)]))
        t.update(np.empty((0, 5)))
        assert len(t.tracks) == 1     # una pasada sin verse: sigue en memoria
        t.update(np.empty((0, 5)))
        assert len(t.tracks) == 0     # dos: se elimina (max_age = 1)

    def test_dos_autos_juntos_no_intercambian_id(self):
        t = IoUTracker()
        ids = None
        for i in range(10):
            r = t.update(np.array([_caja(100 + 20 * i), _caja(330 + 20 * i)]))
            actual = {round(x[0], -2): x[4] for x in r}
            ids = ids or set(actual.values())
            assert set(actual.values()) == ids
        assert len(ids) == 2

    def test_auto_rapido_conserva_id_con_la_prediccion(self):
        # 90 px por pasada: sin predicción la superposición cae bajo 0.3 en curvas
        t = IoUTracker()
        ids = {t.update(np.array([_caja(100 + 90 * i, 400 + 15 * i)]))[0][4] for i in range(3)}
        for i in range(3, 12):
            r = t.update(np.array([_caja(100 + 90 * i, 400 + 15 * i)]))
            ids.add(r[0][4])
        assert len(ids) == 1

    def test_ids_unicos_entre_camaras(self):
        a, b = IoUTracker(), IoUTracker()
        ida = a.update(np.array([_caja(100)]))[0][4]
        idb = b.update(np.array([_caja(100)]))[0][4]
        assert ida != idb

    def test_formato_de_salida(self):
        t = IoUTracker()
        assert t.update(np.empty((0, 5))).shape == (0, 5)
        r = t.update(np.array([_caja(100)]))
        assert r.shape == (1, 5) and r[0][4] >= 1


class TestPatenteEnElMotor:
    """La patente confirmada queda pegada al vehículo mientras el tracker mantenga su id."""

    @pytest.fixture
    def motor(self):
        from engine.security_engine import SecurityEngine
        eng = SecurityEngine()
        eng.resident_plates = {"BCDF12": {"idvehiculo": 1, "unidad": "Casa 12"}}
        return eng

    def _pasada(self, motor, tracker, fc, x):
        ids = tracker.update(np.array([_caja(x)]))
        motor._update_active_vehicles(ids, fc)
        return ids

    def test_dos_lecturas_confirman_y_la_patente_se_conserva_entre_frames(self, motor):
        t = IoUTracker()
        n = config.PROCESS_EVERY_N_FRAMES
        ids = self._pasada(motor, t, n, 100)
        cid = int(ids[0][4])

        motor._vote_plate("BC-DF-12", 0.97, cid, (10, 10, 50, 30), n)
        assert cid not in motor._vehicle_data            # 1 lectura: todavía no se decide
        ids = self._pasada(motor, t, 2 * n, 120)
        assert int(ids[0][4]) == cid
        motor._vote_plate("BC-DF-12", 0.96, cid, (10, 10, 50, 30), 2 * n)
        assert motor._vehicle_data[cid]["plate"] == "BC-DF-12"
        assert motor._vehicle_data[cid]["status"] == "residente"

        # el auto sigue avanzando: mismo id, la patente sigue asociada y no se vuelve a leer
        for k in range(3, 12):
            ids = self._pasada(motor, t, k * n, 100 + 20 * k)
            assert int(ids[0][4]) == cid
            motor._enqueue_hires_plates(ids, k * n, lambda: None)
            assert motor._ocr_queue.empty()
            assert motor._vehicle_data[cid]["plate"] == "BC-DF-12"

    def test_busca_una_patente_a_la_vez_y_alterna_entre_vehiculos(self, motor):
        filas = np.array([[0, 0, 100, 80, 1], [200, 0, 280, 60, 2], [300, 0, 310, 8, 3]], float)
        motor._active_vehicles = {c: {} for c in (1, 2, 3)}
        vistos = []
        for k in range(1, 4):
            motor._enqueue_hires_plates(filas, k * 5, lambda: None, 352)
            assert motor._ocr_queue.qsize() == 1             # una búsqueda por pasada
            motor._enqueue_hires_plates(filas, k * 5, lambda: None, 352)
            assert motor._ocr_queue.qsize() == 1             # la anterior sigue en curso
            vistos.append(motor._ocr_queue.get_nowait()[1])
            motor._pending_ocr.clear()
        assert vistos == [1, 2, 1]                           # el vehículo 3 es muy pequeño

    def test_el_motor_recuerda_si_el_vehiculo_es_moto(self, motor):
        t = IoUTracker()
        dets = [_caja(100), _caja(600)]
        ids = t.update(np.array(dets))
        motor._remember_vehicle_class(ids, dets, [3, 2])
        por_x = {int(r[0]): int(r[4]) for r in ids}
        assert motor._vehicle_class[por_x[100]] == 3     # moto
        assert motor._vehicle_class[por_x[600]] == 2     # auto

    def test_lecturas_distintas_no_confirman(self, motor):
        t = IoUTracker()
        cid = int(self._pasada(motor, t, 5, 100)[0][4])
        motor._vote_plate("BC-DF-12", 0.97, cid, (0, 0, 1, 1), 5)
        motor._vote_plate("BC-DF-13", 0.97, cid, (0, 0, 1, 1), 10)
        assert cid not in motor._vehicle_data
