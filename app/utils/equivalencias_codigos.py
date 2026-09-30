"""Proponer qué artículo de QMS es el mismo que cuál de Defontana.

El mismo artículo debería existir en los dos sistemas: en eso consiste el
cruce. Pero el código no siempre se creó igual en cada uno —"GOL.PRE-5_8"
contra "GOLPRE-58", "00-FSR-SCW-05" contra "FSR-SCW-5"— y entonces el cruce
por código no los encuentra: quedan dos filas, una que dice "Falta en
Defontana" y otra que dice "Falta en QMS", y nunca se juntan.

Las diferencias que sólo son de escritura —espacios, acentos, mayúsculas,
tipos de guion— ya las resuelve codigo_normalizado() al importar. Lo que queda
acá son las de verdad distintas, donde hay que decidir mirando.

Este módulo NO une nada. Propone parejas ordenadas por qué tan probable es que
sean el mismo artículo, y alguien confirma una por una. Unir dos artículos
distintos suma sus existencias y falsea el inventario, así que una propuesta
automática aceptada a ciegas es peor que no tener la pantalla.
"""

import re
import unicodedata
from difflib import SequenceMatcher

# Lo que separa un código de otro son sus letras y números, no los signos con
# que cada sistema los adorna. "GOL.PRE-5_8" y "GOLPRE-58" comparten todo salvo
# el punto, el guion y el guion bajo.
_NO_ALFANUMERICO = re.compile(r"[^0-9A-Z]")


def esqueleto(codigo) -> str:
    """El código sin signos ni acentos, en mayúsculas: "GOL.PRE-5_8" -> "GOLPRE58"."""
    texto = str(codigo or "").strip().upper()
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return _NO_ALFANUMERICO.sub("", sin_acentos)


def esqueleto_sin_ceros(codigo) -> str:
    """Además sin los ceros de relleno de cada tramo: "00-FSR-SCW-05" -> "FSRSCW5".

    Un sistema exporta "00-FSR-SCW-05" y el otro "FSR-SCW-5": el cero de
    relleno es decisión del exportador, no parte del código.
    """
    texto = str(codigo or "").strip().upper()
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    tramos = re.split(r"[^0-9A-Z]+", sin_acentos)
    limpios = []
    for tramo in tramos:
        if tramo.isdigit():
            # Un tramo de puros ceros es un cero, no la cadena vacía.
            limpios.append(tramo.lstrip("0") or "0")
        else:
            limpios.append(tramo)
    return "".join(limpios)


def _parecido(a: str, b: str) -> float:
    """0 a 1. Cuánto se parecen dos textos, carácter a carácter."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _clave_nombre(texto) -> str:
    texto = str(texto or "").strip().upper()
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(_NO_ALFANUMERICO.sub(" ", sin_acentos).split())


# Cuánto pesa cada señal. El código manda porque es lo que identifica al
# artículo; el nombre acompaña, porque cada sistema lo escribe a su manera y
# muchas veces viene truncado.
_PESO_CODIGO = 0.7
_PESO_NOMBRE = 0.3

# Debajo de esto la pareja es ruido: llenar la pantalla de candidatos malos
# hace que se revisen todos con menos atención, incluidos los buenos.
UMBRAL = 0.55


def _solo_letras(codigo) -> str:
    return "".join(c for c in esqueleto(codigo) if not c.isdigit())


def numeros_significativos(codigo) -> tuple:
    """Los números que lleva el código, sin los ceros de relleno.

    Un "00-" delante es relleno del exportador y no dice nada, así que los
    tramos que valen cero se descartan. Lo que queda es lo que de verdad
    distingue: el 10 de un perno de 10 mm frente al 12 de uno de 12.
    """
    tramos = re.split(r"[^0-9]+", str(codigo or ""))
    return tuple(int(t) for t in tramos if t and int(t) != 0)


# Cuando dos códigos tienen las mismas letras pero distintos números, casi
# siempre son dos medidas del mismo producto —PERNO-10 y PERNO-12— y unirlos
# sumaría el stock de dos artículos que no son el mismo. El parecido carácter a
# carácter no lo ve: "10" y "12" difieren en un dígito de siete. Por eso la
# propuesta se hunde hasta quedar bajo el umbral, en vez de encabezar la lista.
_CASTIGO_MEDIDA_DISTINTA = 0.35


def puntaje(qms, defontana) -> float:
    """Qué tan probable es que estos dos sean el mismo artículo, de 0 a 1.

    Un esqueleto idéntico es certeza: el código es el mismo una vez que se le
    quitan los signos, o los ceros de relleno. Si no, se mide el parecido del
    código y el del nombre, y el código pesa más.
    """
    e_qms, e_defo = esqueleto(qms.codigo), esqueleto(defontana.codigo)
    if e_qms and e_qms == e_defo:
        return 1.0
    z_qms, z_defo = esqueleto_sin_ceros(qms.codigo), esqueleto_sin_ceros(defontana.codigo)
    if z_qms and z_qms == z_defo:
        return 1.0

    por_codigo = _parecido(z_qms, z_defo)
    por_nombre = _parecido(_clave_nombre(qms.nombre), _clave_nombre(defontana.nombre))
    valor = _PESO_CODIGO * por_codigo + _PESO_NOMBRE * por_nombre

    if _mismas_letras_otra_medida(qms.codigo, defontana.codigo):
        valor *= _CASTIGO_MEDIDA_DISTINTA
    return round(valor, 4)


def _mismas_letras_otra_medida(uno, otro) -> bool:
    """Mismas letras y distintos números: dos medidas, no el mismo artículo."""
    letras = _solo_letras(uno)
    if not letras or letras != _solo_letras(otro):
        return False
    return numeros_significativos(uno) != numeros_significativos(otro)


def motivo(qms, defontana) -> str:
    """Por qué se propone esta pareja, para poder decidir sin adivinar."""
    if esqueleto(qms.codigo) and esqueleto(qms.codigo) == esqueleto(defontana.codigo):
        return "Mismo código sin los signos"
    if esqueleto_sin_ceros(qms.codigo) == esqueleto_sin_ceros(defontana.codigo):
        return "Mismo código sin los ceros de relleno"
    if _mismas_letras_otra_medida(qms.codigo, defontana.codigo):
        return "Ojo: mismas letras pero distinto número — puede ser otra medida"
    partes = []
    codigo = _parecido(esqueleto_sin_ceros(qms.codigo), esqueleto_sin_ceros(defontana.codigo))
    nombre = _parecido(_clave_nombre(qms.nombre), _clave_nombre(defontana.nombre))
    if codigo >= 0.6:
        partes.append(f"código parecido ({codigo:.0%})")
    if nombre >= 0.6:
        partes.append(f"nombre parecido ({nombre:.0%})")
    return " y ".join(partes).capitalize() if partes else "Parecido general"


def proponer(solo_qms, solo_defontana, umbral: float = UMBRAL, tope: int = 200) -> list:
    """Empareja los que quedaron solos en cada sistema.

    Devuelve [{'qms', 'defontana', 'puntaje', 'motivo'}] de mayor a menor
    puntaje. Cada artículo aparece en una sola propuesta: se resuelven primero
    las parejas más seguras y los ya emparejados salen del juego, para no
    ofrecer dos destinos para el mismo artículo y que uno de los dos esté mal.
    """
    candidatos = []
    for uno in solo_qms:
        for otro in solo_defontana:
            valor = puntaje(uno, otro)
            if valor >= umbral:
                candidatos.append((valor, uno, otro))

    # Desempate estable por código, para que dos ejecuciones den lo mismo.
    candidatos.sort(key=lambda c: (-c[0], c[1].codigo, c[2].codigo))

    tomados_qms, tomados_defo, propuestas = set(), set(), []
    for valor, uno, otro in candidatos:
        if uno.id in tomados_qms or otro.id in tomados_defo:
            continue
        tomados_qms.add(uno.id)
        tomados_defo.add(otro.id)
        propuestas.append({
            "qms": uno,
            "defontana": otro,
            "puntaje": valor,
            "motivo": motivo(uno, otro),
        })
        if len(propuestas) >= tope:
            break
    return propuestas
