"""Cómo se compara un código de artículo entre QMS y Defontana.

Texto puro: no sabe de modelos ni de base de datos. Vive aparte justamente por
eso — lo usan el importador, el modelo de equivalencias y las pantallas, y
tenerlo dentro del importador obligaba a que el modelo importara de él,
cerrando un ciclo entre modelos y utilidades.
"""

import unicodedata

_GUIONES = {
    "‐": "-",  # HYPHEN
    "‑": "-",  # NON-BREAKING HYPHEN
    "‒": "-",  # FIGURE DASH
    "–": "-",  # EN DASH
    "—": "-",  # EM DASH
    "―": "-",  # HORIZONTAL BAR
    "−": "-",  # MINUS SIGN
}


def codigo_normalizado(codigo) -> str:
    """Clave para comparar códigos que son el mismo escrito distinto.

    QMS y Defontana no siempre escriben igual el código del mismo artículo:
    "EM-R-Pantalla BG3" y "EM-R-PantallaBG3" son el mismo producto. Para
    compararlos se saca todo lo que no cambia de qué artículo se trata:

    - espacios de cualquier tipo, incluido el espacio duro que pega Excel;
    - caracteres invisibles (categoría Cf): espacio de ancho cero, guion suave,
      la marca BOM... No se ven en pantalla, así que dos códigos que sólo se
      diferencian en eso parecen idénticos y aun así no cruzaban;
    - los distintos guiones tipográficos, que se unifican al '-';
    - el apóstrofe con que Excel marca "esto es texto";
    - acentos y mayúsculas.
    """
    texto = str(codigo or "").strip().lstrip("'").strip()
    # Los Cf hay que sacarlos antes de comparar nada: son invisibles.
    sin_invisibles = "".join(c for c in texto if unicodedata.category(c) != "Cf")
    sin_guiones = "".join(_GUIONES.get(c, c) for c in sin_invisibles)
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", sin_guiones) if unicodedata.category(c) != "Mn"
    )
    return "".join(sin_acentos.split()).upper()



# Nombre corto para los caracteres que no se ven pero separan dos códigos.
_INVISIBLES = {
    " ": "espacio duro",
    "​": "espacio de ancho cero",
    "‌": "separador de ancho cero",
    "‍": "unión de ancho cero",
    "⁠": "unión invisible",
    "﻿": "marca BOM",
    "­": "guion suave",
    "\t": "tabulador",
}


def rarezas_del_codigo(codigo) -> list:
    """Qué tiene este código que no se ve en pantalla.

    Dos códigos que sólo se diferencian en un carácter invisible se ven
    idénticos, así que en la pantalla de depuración no habría forma de saber
    por qué aparecen repetidos. Esto lo explica en palabras.
    """
    texto = str(codigo or "")
    encontradas = []
    if texto != texto.strip():
        encontradas.append("espacios al principio o al final")
    if texto.startswith("'"):
        encontradas.append("apóstrofe de Excel")
    if " " in texto.strip():
        encontradas.append("espacios en medio")
    for caracter, nombre in _INVISIBLES.items():
        if caracter in texto:
            encontradas.append(nombre)
    for caracter in _GUIONES:
        if caracter in texto:
            encontradas.append("guion tipográfico")
            break
    return encontradas
