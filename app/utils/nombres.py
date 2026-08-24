"""Agrupar nombres escritos a mano.

Las agencias, los proveedores y demás nombres se escriben a mano en cada
importación. Dos que se ven idénticos en pantalla pueden diferir en un espacio
de más, un acento, una mayúscula o un carácter invisible pegado desde Excel, y
entonces el sistema los trata como dos cosas distintas: en Movimientos por
agencia aparecían dos grupos "UNITED PARCEL SERVICE DE CHILE LIMITADA", cada
uno con su propio saldo, y ninguno de los dos era el saldo real.

La clave se usa sólo para comparar y agrupar. Lo que se guarda y lo que se
muestra sigue siendo el texto tal como se escribió: corregir el dato es otra
decisión, y no es de este módulo tomarla.
"""

import re
import unicodedata

_ESPACIOS = re.compile(r"\s+")


def clave_de_nombre(texto) -> str:
    """Clave de agrupación de un nombre. Devuelve '' si no hay nada que agrupar.

    Ignora, en este orden: los caracteres invisibles (categoría Cf, como el
    espacio de ancho cero), los acentos, la diferencia entre mayúsculas y
    minúsculas, y los espacios de más —al principio, al final y repetidos en
    medio—.
    """
    if not texto:
        return ""
    # Los invisibles primero: no se ven, así que nadie sospecha de ellos.
    sin_invisibles = "".join(c for c in str(texto) if unicodedata.category(c) != "Cf")
    # El espacio duro (U+00A0) llega pegado desde Excel y no lo toma \s en
    # algunas versiones; se pasa a espacio normal antes de colapsar.
    sin_duros = sin_invisibles.replace(" ", " ")
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", sin_duros)
        if not unicodedata.combining(c)
    )
    return _ESPACIOS.sub(" ", sin_acentos).strip().casefold()


def agrupar_por_nombre(elementos, nombre_de):
    """Agrupa por nombre tolerando esas diferencias.

    Devuelve [(etiqueta, [elementos])]. La etiqueta es la forma más repetida
    entre las variantes del grupo: si el nombre está bien escrito noventa veces
    y con un espacio de más una, manda la de noventa.
    """
    grupos = {}
    for elemento in elementos:
        nombre = nombre_de(elemento)
        clave = clave_de_nombre(nombre)
        grupo = grupos.setdefault(clave, {"elementos": [], "variantes": {}})
        grupo["elementos"].append(elemento)
        etiqueta = (nombre or "").strip()
        grupo["variantes"][etiqueta] = grupo["variantes"].get(etiqueta, 0) + 1

    resultado = []
    for grupo in grupos.values():
        # Más repetida primero; a igual cantidad, la primera en orden alfabético,
        # para que el listado no cambie de etiqueta entre una carga y otra.
        etiqueta = sorted(grupo["variantes"].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        resultado.append((etiqueta, grupo["elementos"]))
    return resultado
