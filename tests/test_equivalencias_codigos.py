"""Unificar códigos: el mismo artículo con otro código en cada sistema.

El mismo artículo debería existir en QMS y en Defontana. Cuando el código se
creó distinto en cada uno, el cruce por código deja dos filas sueltas que nunca
se encuentran: una dice "Falta en Defontana" y la otra "Falta en QMS".

Lo que se prueba acá es sobre todo lo que NO debe pasar: que se proponga unir
dos artículos distintos. Unirlos suma sus existencias y falsea el inventario,
y eso es peor que no tener la pantalla.
"""

import io

import pytest
from werkzeug.datastructures import FileStorage

from app.models.conteo_inventario import ItemConteoInventario
from app.models.equivalencia_codigo import EquivalenciaCodigo, traducciones
from app.utils.equivalencias_codigos import (
    UMBRAL,
    esqueleto,
    esqueleto_sin_ceros,
    numeros_significativos,
    proponer,
    puntaje,
)
from tests.conftest import login


class _Articulo:
    """Lo mínimo que mira el motor: un id, un código y un nombre."""

    _n = 0

    def __init__(self, codigo, nombre=""):
        _Articulo._n += 1
        self.id = _Articulo._n
        self.codigo = codigo
        self.nombre = nombre


# --- Normalizar el código ---


@pytest.mark.parametrize("codigo, esperado", [
    ("GOL.PRE-5_8", "GOLPRE58"),
    ("gol pre 5 8", "GOLPRE58"),
    ("CÓDIGO-1", "CODIGO1"),
    ("", ""),
])
def test_el_esqueleto_deja_solo_letras_y_numeros(codigo, esperado):
    assert esqueleto(codigo) == esperado


@pytest.mark.parametrize("codigo, esperado", [
    ("00-FSR-SCW-05", "0FSRSCW5"),
    ("0136-1005", "136-1005".replace("-", "")),
    ("FSR-SCW-5", "FSRSCW5"),
])
def test_los_ceros_de_relleno_no_son_parte_del_codigo(codigo, esperado):
    assert esqueleto_sin_ceros(codigo) == esperado


def test_un_tramo_de_puros_ceros_es_un_cero_y_no_nada():
    """Si "0" desapareciera, "A-0-B" y "A-B" se leerían como el mismo código."""
    assert esqueleto_sin_ceros("A-0-B") == "A0B"
    assert esqueleto_sin_ceros("A-B") == "AB"


@pytest.mark.parametrize("codigo, esperado", [
    ("PERNO-10", (10,)),
    ("00-FSR-SCW-05", (5,)),      # el 00 es relleno: no cuenta
    ("0136-1005", (136, 1005)),
    ("SOLO-LETRAS", ()),
])
def test_los_numeros_significativos_ignoran_el_relleno(codigo, esperado):
    assert numeros_significativos(codigo) == esperado


# --- Los que SÍ son el mismo artículo ---


@pytest.mark.parametrize("uno, otro, nombre", [
    ("GOL.PRE-5_8", "GOLPRE-58", "GOLILLA PRESION 5/8"),
    ("CABLE-3MM", "CABLE_3_MM", "Cable de acero 3mm"),
    ("11-CON-OTH-01", "11CONOTH1", "RELAY E-MECH 6A"),
])
def test_el_mismo_codigo_escrito_distinto_se_reconoce(uno, otro, nombre):
    assert puntaje(_Articulo(uno, nombre), _Articulo(otro, nombre)) == 1.0


def test_el_cero_de_relleno_no_hace_otro_articulo():
    a = _Articulo("0136-1005", "PER.BUTTOM INOX 1/4X5/8")
    b = _Articulo("136-1005", "PER BUTTOM INOX 1/4 X 5/8")
    assert puntaje(a, b) == 1.0


def test_codigos_parecidos_con_el_mismo_nombre_se_proponen():
    a = _Articulo("00-FSR-SCW-05", "SCREWS")
    b = _Articulo("FSR-SCW-5", "SCREWS")
    assert puntaje(a, b) >= UMBRAL


# --- Los que NO son el mismo artículo: lo importante ---


@pytest.mark.parametrize("uno, otro, nombre_a, nombre_b", [
    ("PERNO-10", "PERNO-12", "PERNO HEX 10MM", "PERNO HEX 12MM"),
    ("BROCA-5.0", "BROCA-5.5", "BROCA HSS METRICA 5.0", "BROCA HSS METRICA 5.5"),
    ("SCW-100", "SCW-1000", "TORNILLO 100", "TORNILLO 1000"),
])
def test_dos_medidas_del_mismo_producto_no_se_proponen(uno, otro, nombre_a, nombre_b):
    """El caso peligroso: los códigos se parecen muchísimo y son artículos
    distintos. El parecido carácter a carácter no lo ve —"10" y "12" difieren
    en un dígito de siete— así que hay que mirar los números aparte."""
    valor = puntaje(_Articulo(uno, nombre_a), _Articulo(otro, nombre_b))
    assert valor < UMBRAL, f"{uno} vs {otro} se propondría con {valor}"


def test_dos_articulos_sin_nada_que_ver_no_se_proponen():
    a = _Articulo("TUERCA-8", "TUERCA 8MM")
    b = _Articulo("AMPOLLETA-8", "AMPOLLETA LED 8W")
    assert puntaje(a, b) < UMBRAL


# --- Emparejar ---


def test_cada_articulo_se_propone_una_sola_vez():
    """Ofrecer dos destinos para el mismo artículo garantiza que uno esté mal."""
    qms = [_Articulo("CABLE-3MM", "Cable 3mm")]
    defo = [_Articulo("CABLE_3_MM", "Cable 3 mm"), _Articulo("CABLE-3-MM", "Cable 3mm")]

    propuestas = proponer(qms, defo)

    assert len(propuestas) == 1


def test_las_mas_seguras_van_primero():
    qms = [_Articulo("AAA-1", "Pieza A"), _Articulo("BBB-2", "Pieza B")]
    defo = [_Articulo("BBB2", "Pieza B"), _Articulo("AAA1X", "Pieza A")]

    propuestas = proponer(qms, defo)

    assert propuestas[0]["puntaje"] >= propuestas[-1]["puntaje"]


def test_sin_candidatos_no_inventa_parejas():
    assert proponer([], [_Articulo("X", "X")]) == []
    assert proponer([_Articulo("X", "X")], []) == []


# --- La pantalla ---


def _item(db, empresa, codigo, nombre, en_qms=True, en_defontana=True, **campos):
    item = ItemConteoInventario(
        empresa_id=empresa.id, codigo=codigo, nombre=nombre,
        en_qms=en_qms, en_defontana=en_defontana, **campos,
    )
    db.session.add(item)
    db.session.commit()
    return item


def test_la_pantalla_propone_los_sueltos(client, db, empresa, usuario_admin):
    _item(db, empresa, "GOL.PRE-5_8", "GOLILLA PRESION 5/8", en_defontana=False, cantidad_qms=4)
    _item(db, empresa, "GOLPRE-58", "GOL.PRESION 5-8", en_qms=False, cantidad_defontana=4)
    _item(db, empresa, "EN-LOS-DOS", "Normal")
    login(client, "admin@test.cl")

    cuerpo = client.get("/inventario/equivalencias").get_data(as_text=True)

    assert "GOL.PRE-5_8" in cuerpo and "GOLPRE-58" in cuerpo
    # El que ya cruza no es candidato a nada
    assert "EN-LOS-DOS" not in cuerpo


def test_unir_deja_la_pareja_guardada(client, db, empresa, usuario_admin):
    _item(db, empresa, "GOL.PRE-5_8", "GOLILLA", en_defontana=False)
    _item(db, empresa, "GOLPRE-58", "GOL.PRESION", en_qms=False)
    login(client, "admin@test.cl")

    client.post("/inventario/equivalencias/unir", data={
        "codigo_qms": "GOL.PRE-5_8", "codigo_defontana": "GOLPRE-58",
    }, follow_redirects=True)

    equivalencia = EquivalenciaCodigo.query.one()
    assert equivalencia.codigo_qms == "GOL.PRE-5_8"
    assert equivalencia.codigo_defontana == "GOLPRE-58"
    assert equivalencia.creado_por_id == usuario_admin.id


def test_lo_ya_unido_sale_de_las_propuestas(client, db, empresa, usuario_admin):
    _item(db, empresa, "GOL.PRE-5_8", "GOLILLA", en_defontana=False)
    _item(db, empresa, "GOLPRE-58", "GOL.PRESION", en_qms=False)
    login(client, "admin@test.cl")
    client.post("/inventario/equivalencias/unir", data={
        "codigo_qms": "GOL.PRE-5_8", "codigo_defontana": "GOLPRE-58",
    }, follow_redirects=True)

    cuerpo = client.get("/inventario/equivalencias").get_data(as_text=True)
    propuestas = cuerpo[cuerpo.index("Parejas propuestas"):cuerpo.index("Ya unidos")]

    assert "GOLPRE-58" not in propuestas
    assert "Ya unidos <span class=\"text-muted\">(1)</span>" in cuerpo


def test_no_se_puede_unir_un_codigo_a_dos_articulos(client, db, empresa, usuario_admin):
    """Si un código de Defontana apuntara a dos de QMS, su stock se duplicaría."""
    _item(db, empresa, "QMS-A", "A", en_defontana=False)
    _item(db, empresa, "QMS-B", "B", en_defontana=False)
    _item(db, empresa, "DEFO-X", "X", en_qms=False)
    login(client, "admin@test.cl")
    client.post("/inventario/equivalencias/unir", data={
        "codigo_qms": "QMS-A", "codigo_defontana": "DEFO-X"}, follow_redirects=True)

    cuerpo = client.post("/inventario/equivalencias/unir", data={
        "codigo_qms": "QMS-B", "codigo_defontana": "DEFO-X"},
        follow_redirects=True).get_data(as_text=True)

    assert "ya está unido" in cuerpo
    assert EquivalenciaCodigo.query.count() == 1


def test_unir_un_codigo_consigo_mismo_se_rechaza(client, db, empresa, usuario_admin):
    """Con distinto espaciado y mayúsculas ya cruzan solos desde la importación:
    guardar una equivalencia ahí sería ruido que después confunde."""
    _item(db, empresa, "MISMO-1", "X", en_defontana=False)
    login(client, "admin@test.cl")

    cuerpo = client.post("/inventario/equivalencias/unir", data={
        "codigo_qms": "MISMO-1", "codigo_defontana": " mismo-1 "},
        follow_redirects=True).get_data(as_text=True)

    assert "ya cruzan solos" in cuerpo
    assert EquivalenciaCodigo.query.count() == 0


def test_separar_deshace_la_union(client, db, empresa, usuario_admin):
    _item(db, empresa, "QMS-A", "A", en_defontana=False)
    _item(db, empresa, "DEFO-X", "X", en_qms=False)
    login(client, "admin@test.cl")
    client.post("/inventario/equivalencias/unir", data={
        "codigo_qms": "QMS-A", "codigo_defontana": "DEFO-X"}, follow_redirects=True)
    equivalencia = EquivalenciaCodigo.query.one()

    client.post(f"/inventario/equivalencias/{equivalencia.id}/deshacer",
                data={}, follow_redirects=True)

    assert EquivalenciaCodigo.query.count() == 0


def test_la_pantalla_la_ve_quien_puede_editar(client, db, empresa, usuario_bodega):
    login(client, "bodega@test.cl")
    assert client.get("/inventario/equivalencias").status_code == 403


def test_el_enlace_esta_en_el_menu(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    assert "/inventario/equivalencias" in client.get("/inventario/").get_data(as_text=True)


# --- Lo que hace que valga la pena: el importador la respeta ---


CSV_DEFONTANA = (
    "CodArticulo;Descripción;CodBodega;Nombre Bodega;Saldo Stock\r\n"
    "GOLPRE-58;GOL.PRESION 5-8;01;Casa Matriz;7\r\n"
)


def test_la_union_se_respeta_en_la_siguiente_importacion(
    client, db, empresa, usuario_admin
):
    """Lo que la hace una tabla de traducción y no una fusión de una sola vez.

    Si sólo se fusionaran las filas, la próxima carga volvería a crear los dos
    artículos separados y habría que rehacer el trabajo todos los meses.
    """
    from app.utils.importar_conteo import importar_defontana

    _item(db, empresa, "GOL.PRE-5_8", "GOLILLA PRESION 5/8",
          en_defontana=False, cantidad_qms=4)
    login(client, "admin@test.cl")
    client.post("/inventario/equivalencias/unir", data={
        "codigo_qms": "GOL.PRE-5_8", "codigo_defontana": "GOLPRE-58",
    }, follow_redirects=True)

    importar_defontana(
        FileStorage(stream=io.BytesIO(CSV_DEFONTANA.encode("utf-8")), filename="d.csv"),
        empresa.id,
    )

    # Un solo artículo, con el stock de los dos sistemas en la misma fila
    assert ItemConteoInventario.query.count() == 1
    item = ItemConteoInventario.query.one()
    assert item.codigo == "GOL.PRE-5_8"
    assert item.cantidad_qms == 4
    assert item.cantidad_defontana == 7
    assert item.falta_en == ""


def test_sin_union_la_importacion_los_deja_separados(client, db, empresa, usuario_admin):
    """El contraste: es exactamente el problema que se viene a resolver."""
    from app.utils.importar_conteo import importar_defontana

    _item(db, empresa, "GOL.PRE-5_8", "GOLILLA PRESION 5/8",
          en_defontana=False, cantidad_qms=4)

    importar_defontana(
        FileStorage(stream=io.BytesIO(CSV_DEFONTANA.encode("utf-8")), filename="d.csv"),
        empresa.id,
    )

    assert ItemConteoInventario.query.count() == 2


def test_las_traducciones_son_de_cada_empresa(db, empresa):
    assert traducciones(empresa.id) == {}
