# -*- coding: utf-8 -*-
"""
core/texto.py - Comparación de nombres en español, sin depender del motor de base.

- clave_busqueda: ignora mayúsculas, tildes y diéresis, y trata la ñ como n,
  para que buscar «jose» o «nunez» encuentre a «José» y a «Núñez».
- clave_orden: ignora mayúsculas y tildes, pero ordena la ñ después de la n,
  como el diccionario (y como la intercalación utf8mb4_spanish_ci de MySQL).
"""

import unicodedata


def _sin_marcas(texto: str, conservar_enie: bool) -> str:
    texto = (texto or "").casefold()
    if conservar_enie:
        texto = texto.replace("ñ", "\0")   # se protege antes de quitar la virgulilla
    sin = "".join(c for c in unicodedata.normalize("NFD", texto)
                  if unicodedata.category(c) != "Mn")
    return sin.replace("\0", "ñ") if conservar_enie else sin


def clave_busqueda(texto: str) -> str:
    return _sin_marcas(texto, conservar_enie=False)


def clave_orden(texto: str) -> str:
    # '~' va después de todas las letras: «nu» < «ñ» (n~) < «o»
    return _sin_marcas(texto, conservar_enie=True).replace("ñ", "n~")


def comparar_es(a: str, b: str) -> int:
    """Función de intercalación para sqlite3.Connection.create_collation."""
    ka, kb = clave_orden(a), clave_orden(b)
    if ka != kb:
        return -1 if ka < kb else 1
    return -1 if a < b else (1 if a > b else 0)   # desempate estable entre «Jose» y «José»
