"""Agrupar nombres escritos a mano pese a diferencias que no se ven.

En Movimientos por agencia aparecían dos bloques "UNITED PARCEL SERVICE DE
CHILE LIMITADA", cada uno con su propio saldo y ninguno con el saldo real.
"""

from app.utils.nombres import agrupar_por_nombre, clave_de_nombre


def test_las_diferencias_invisibles_dan_la_misma_clave():
    base = "UNITED PARCEL SERVICE DE CHILE LIMITADA"
    variantes = [
        base + " ",                     # espacio al final
        " " + base,                     # espacio al principio
        base.replace(" DE ", "  DE "),  # espacio doble en medio
        base.lower(),                   # minúsculas
        base.replace("SERVICE", "SERVICE​"),  # espacio de ancho cero
        base.replace(" ", " ", 1),  # espacio duro pegado desde Excel
    ]
    claves = {clave_de_nombre(v) for v in variantes} | {clave_de_nombre(base)}
    assert len(claves) == 1, f"quedaron {len(claves)} claves distintas: {claves}"


def test_los_acentos_no_separan():
    assert clave_de_nombre("LOGÍSTICA ANDINA") == clave_de_nombre("LOGISTICA ANDINA")


def test_dos_agencias_de_verdad_distintas_siguen_separadas():
    """La tolerancia no puede llegar a juntar lo que sí es distinto."""
    assert clave_de_nombre("DHL") != clave_de_nombre("DHL EXPRESS")
    assert clave_de_nombre("FEDEX") != clave_de_nombre("FEDX")


def test_un_nombre_vacio_no_revienta():
    assert clave_de_nombre(None) == ""
    assert clave_de_nombre("") == ""
    assert clave_de_nombre("   ") == ""


def test_se_agrupan_en_un_solo_bloque():
    filas = [
        {"agencia": "UNITED PARCEL SERVICE DE CHILE LIMITADA", "monto": 1},
        {"agencia": "UNITED PARCEL SERVICE DE CHILE LIMITADA ", "monto": 2},
        {"agencia": "DHL", "monto": 4},
    ]
    grupos = dict(
        (etiqueta, sum(f["monto"] for f in elementos))
        for etiqueta, elementos in agrupar_por_nombre(filas, lambda f: f["agencia"])
    )
    assert len(grupos) == 2
    assert grupos["UNITED PARCEL SERVICE DE CHILE LIMITADA"] == 3
    assert grupos["DHL"] == 4


def test_la_etiqueta_es_la_forma_mas_repetida():
    """Si el nombre está bien escrito muchas veces y mal una, manda el bueno."""
    filas = [{"a": "DHL"}, {"a": "DHL"}, {"a": "dhl  "}]
    (etiqueta, _), = agrupar_por_nombre(filas, lambda f: f["a"])
    assert etiqueta == "DHL"


def test_la_etiqueta_no_cambia_entre_dos_cargas():
    """Con la misma cantidad de cada variante, el desempate tiene que ser estable."""
    filas = [{"a": "Agencia Uno"}, {"a": "AGENCIA UNO"}]
    primera, = agrupar_por_nombre(filas, lambda f: f["a"])
    segunda, = agrupar_por_nombre(list(reversed(filas)), lambda f: f["a"])
    assert primera[0] == segunda[0]
