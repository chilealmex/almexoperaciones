"""Equivalencias entre las unidades de medida de QMS y las de Defontana.

Los dos sistemas escriben la misma unidad de forma distinta: QMS pone "M" donde
Defontana pone "MT", "RL" donde el otro pone "ROLLO". Comparándolas como texto
aparecían como diferencia de unidad cientos de artículos que en realidad están
bien, y eso tapaba las diferencias de verdad.

PARA AGREGAR UNA EQUIVALENCIA NUEVA: añade la forma a la fila que corresponda
en EQUIVALENCIAS (o crea una fila nueva). No hay que tocar nada más: todas las
pantallas comparan a través de unidad_normalizada().
"""

import unicodedata

# Cada fila junta todas las formas de escribir la misma unidad. La primera es
# sólo el nombre interno del grupo; no se muestra en pantalla.
EQUIVALENCIAS = {
    "metro": ("M", "MT", "MTS", "METRO", "METROS"),
    "pack": ("PK", "PACK", "PACKS"),
    "litro": ("L", "LT", "LTS", "LITRO", "LITROS"),
    "pie": ("FT", "PIE", "PIES", "FEET"),
    "rollo": ("RL", "ROLLO", "ROLLOS"),
    "unidad": ("UN", "UND", "UNI", "UD", "UNIDAD", "UNIDADES", "CU"),
    "kilo": ("KG", "KGS", "KILO", "KILOS", "KILOGRAMO", "KILOGRAMOS"),
    "caja": ("CJ", "CAJA", "CAJAS"),
    "galon": ("GL", "GAL", "GALON", "GALONES"),
}

# Se arma al revés una sola vez: forma escrita -> grupo al que pertenece.
_GRUPO_POR_FORMA = {
    forma: grupo for grupo, formas in EQUIVALENCIAS.items() for forma in formas
}


def _limpiar(unidad) -> str:
    """Mayúsculas, sin acentos, sin espacios ni puntuación: 'Mt.' y ' mt ' son 'MT'."""
    texto = str(unidad or "").strip()
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return "".join(c for c in sin_acentos.upper() if c.isalnum())


def unidad_normalizada(unidad) -> str:
    """Forma con la que comparar dos unidades.

    Si la unidad está en la tabla devuelve el nombre del grupo, así "M" y "MT"
    dan lo mismo. Si no está, devuelve la unidad limpia: las que no conocemos se
    siguen comparando como antes, sin inventar equivalencias.
    """
    limpia = _limpiar(unidad)
    return _GRUPO_POR_FORMA.get(limpia, limpia)


def son_equivalentes(una, otra) -> bool:
    """True si ambas unidades significan lo mismo (o si falta alguna de las dos).

    Cuando un sistema no declara unidad no hay nada que contradecir, así que no
    se cuenta como diferencia.
    """
    if not una or not otra:
        return True
    return unidad_normalizada(una) == unidad_normalizada(otra)
