# -*- coding: utf-8 -*-
"""Búsqueda y orden de nombres en español (core/texto.py)."""

from functools import cmp_to_key

from core.texto import clave_busqueda, comparar_es


class TestBusquedaSinTildes:
    def test_jose_encuentra_todas_las_variantes(self):
        nombres = ["José Pérez", "JOSE ROJAS", "jose tapia", "Josefina Díaz", "María Soto"]
        for termino in ("jose", "JOSE", "José", "josé"):
            encontrados = [n for n in nombres if clave_busqueda(termino) in clave_busqueda(n)]
            assert encontrados == nombres[:4], termino

    def test_enie_y_dieresis(self):
        assert clave_busqueda("nunez") in clave_busqueda("Núñez")
        assert clave_busqueda("Muñoz") in clave_busqueda("MUNOZ")
        assert clave_busqueda("guemes") in clave_busqueda("Güemes")

    def test_rut_y_unidad_se_buscan_igual(self):
        assert clave_busqueda("torre a-101") in clave_busqueda("Torre A-101 Ana 12.345.678-5")


class TestOrdenEspanol:
    def test_tildes_junto_a_su_letra_y_enie_despues_de_n(self):
        desordenado = ["Órdenes", "zeta", "Ñandú", "Ávila", "Norte", "Acevedo", "nuñez", "Nunez"]
        orden = sorted(desordenado, key=cmp_to_key(comparar_es))
        assert orden == ["Acevedo", "Ávila", "Norte", "Nunez", "nuñez", "Ñandú", "Órdenes", "zeta"]
