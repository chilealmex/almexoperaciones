"""Cómo se compara un código de artículo entre QMS y Defontana.

Texto puro: no sabe de modelos ni de base de datos. Vive aparte justamente por
eso — lo usan el importador, el modelo de equivalencias y las pantallas, y
tenerlo dentro del importador obligaba a que el modelo importara de él,
cerrando un ciclo entre modelos y utilidades.
"""

import re
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


def clave_sin_ceros(codigo) -> str:
    """Como codigo_normalizado(), pero sin los ceros de relleno de cada tramo.

    "011-CON-OTH-01" y "11-CON-OTH-01" son el mismo artículo: el cero de
    adelante lo pone quien exporta, no distingue nada. Lo mismo con
    "0136-1005" y "136-1005".

    El cero se saca aunque el tramo siga con letras. "0870AP2" y "870AP2" son
    el mismo artículo igual que "052075" y "52075", pero antes sólo se limpiaba
    el tramo que era todo dígitos: el cero de "0870AP2" quedaba puesto, los dos
    códigos no caían en el mismo grupo y la pantalla de Unificar códigos no
    llegaba a proponerlos nunca.

    No reemplaza a codigo_normalizado(): esa es la llave con que el importador
    reconoce al artículo, y cambiarla movería la identidad de todo el maestro.
    Ésta sirve para *sospechar* que dos códigos son el mismo y proponérselo a
    alguien, que decide.
    """
    normalizado = codigo_normalizado(codigo)
    if not normalizado:
        return ""
    # Se parten los tramos conservando los separadores: lo que cambia es sólo
    # el relleno con que empieza cada tramo.
    partes = re.split(r"([^0-9A-Z])", normalizado)
    return "".join(sin_cero_de_relleno(p) for p in partes)


def sin_cero_de_relleno(tramo: str) -> str:
    """Un tramo del código sin los ceros con que empieza.

    Un tramo de puros ceros es un cero, no la cadena vacía: si no, "A-00" y
    "A" quedarían en el mismo grupo.
    """
    if not tramo.startswith("0"):
        return tramo
    return tramo.lstrip("0") or "0"
