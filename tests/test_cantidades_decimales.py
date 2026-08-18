"""Cantidades de inventario con decimales.

No todo el stock se cuenta de a uno: hay artículos que se miden en metros,
kilos o litros. Estas pruebas cubren el camino completo de un "12,5": que se
pueda escribir en la pantalla de conteo, que se guarde sin redondear, que
llegue así desde una planilla y que salga bien escrito en pantalla y en Excel.
"""

import json
from decimal import Decimal

import pytest
from sqlalchemy import Numeric

from app.models.conteo_inventario import ItemConteoInventario, TomaInventarioDetalle
from app.utils.cantidades import (
    a_cantidad,
    a_entero_clp,
    format_cantidad,
    format_cantidad_signo,
)
from tests.conftest import login


# --- El tipo de las columnas ---
#
# Se comprueba el TIPO y no sólo el valor: SQLite guarda cualquier cosa en
# cualquier columna, así que un modelo declarado en entero pasaría igual estas
# pruebas mientras en PostgreSQL —el motor real— los decimales se truncan.


@pytest.mark.parametrize("modelo", [ItemConteoInventario, TomaInventarioDetalle])
@pytest.mark.parametrize("columna", ["cantidad_qms", "cantidad_defontana", "cantidad_fisica"])
def test_las_cantidades_son_columnas_con_decimales(modelo, columna):
    tipo = modelo.__table__.c[columna].type
    assert isinstance(tipo, Numeric), f"{modelo.__tablename__}.{columna} no admite decimales"
    assert tipo.scale == 3
    # 19 dígitos enteros: el mismo rango que el BigInteger anterior. Achicarlo
    # traería de vuelta el error 500 al importar una celda con una cifra enorme.
    assert tipo.precision - tipo.scale >= 19


# --- Interpretar lo que se escribe o llega de una planilla ---


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("12,5", "12.5"),      # coma decimal, como se escribe en Chile
        ("12.5", "12.5"),      # punto decimal, como sale de una calculadora
        ("12", "12"),
        ("1.234", "1234"),     # punto de miles: no son 1,234 metros
        ("1.234,5", "1234.5"),
        ("1,234.5", "1234.5"),
        ("0,25", "0.25"),
        ("-3,5", "-3.5"),
        (12.5, "12.5"),        # número nativo de Excel
        (Decimal("7.125"), "7.125"),
        (7, "7"),
    ],
)
def test_a_cantidad_interpreta_los_formatos_de_planilla(entrada, esperado):
    assert a_cantidad(entrada) == Decimal(esperado)


@pytest.mark.parametrize("entrada", ["", None, "  ", "abc", "12,5 metros"])
def test_a_cantidad_devuelve_el_valor_por_defecto_si_no_hay_numero(entrada):
    assert a_cantidad(entrada) is None


def test_una_cifra_gigante_sigue_entrando():
    """El rango es el mismo que tenía el BigInteger de antes.

    Si al agregar decimales se hubiera achicado el rango, una planilla con una
    celda enorme volvería a tumbar la importación completa con un error 500.
    """
    assert a_cantidad("9000000000000000000") == Decimal("9000000000000000000")


def test_una_celda_con_una_cifra_sin_sentido_no_tumba_la_importacion():
    # 30 dígitos no caben en ninguna columna; vale más dejarla en 0 que perder
    # el archivo entero.
    assert a_cantidad("9" * 30, por_defecto=Decimal(0)) == 0


def test_a_cantidad_no_arrastra_el_ruido_binario_del_float():
    # Decimal(12.5) directo del float traería la cola de la representación
    # binaria; el conteo mostraría cifras que nadie escribió.
    assert str(a_cantidad(0.1)) == "0.100"


# --- Cómo se muestran ---


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (Decimal("1234.000"), "1.234"),   # sin decimales de relleno
        (Decimal("12.500"), "12,5"),
        (Decimal("0.250"), "0,25"),
        (Decimal("7.125"), "7,125"),
        (Decimal("-3.500"), "-3,5"),
        (Decimal("0"), "0"),
        (None, ""),
    ],
)
def test_format_cantidad_escribe_a_la_chilena(valor, esperado):
    assert format_cantidad(valor) == esperado


@pytest.mark.parametrize(
    "valor, esperado",
    [(Decimal("2.500"), "+2,5"), (Decimal("-2.500"), "-2,5"), (Decimal("0"), "0")],
)
def test_format_cantidad_signo_muestra_hacia_donde_va_el_descuadre(valor, esperado):
    assert format_cantidad_signo(valor) == esperado


@pytest.mark.parametrize(
    "valor",
    ["0", "1", "12.5", "3.125", "1234", "1234.5", "0.25", "0.125", "1234567.5", "999.999", "100"],
)
def test_lo_que_se_muestra_se_vuelve_a_leer_igual(valor):
    """El formato de pantalla es el mismo que queda escrito en el campo de conteo.

    Si mostrar y leer no fueran la misma cosa, guardar sin tocar nada cambiaría
    el número: un campo con '3.125' —tres coma ciento veinticinco— se leería
    como tres mil ciento veinticinco y el conteo se corrompería al recargar.
    """
    numero = Decimal(valor)
    assert a_cantidad(format_cantidad(numero)) == numero


def test_a_entero_clp_redondea_la_plata_a_pesos():
    assert a_entero_clp(Decimal("1250.5")) == 1251
    assert a_entero_clp(Decimal("1250.4")) == 1250
    assert a_entero_clp(None) == 0


# --- Guardar el conteo desde la pantalla ---


def _item(db, empresa, codigo, qms, defontana, unidad="MT"):
    item = ItemConteoInventario(
        empresa_id=empresa.id,
        codigo=codigo,
        nombre=f"Artículo {codigo}",
        cantidad_qms=qms,
        cantidad_defontana=defontana,
        unidad_qms=unidad,
        unidad_defontana=unidad,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _contar(client, item, valor):
    return client.post(
        f"/inventario/stock/{item.id}/contar",
        data=json.dumps({"cantidad": valor}),
        content_type="application/json",
    )


@pytest.mark.parametrize("escrito, guardado", [("12,5", "12.5"), ("12.5", "12.5"), ("0,25", "0.25")])
def test_se_puede_contar_con_decimales(client, db, empresa, usuario_admin, escrito, guardado):
    item = _item(db, empresa, "ROLLO-CABLE", 10, 10)
    login(client, "admin@test.cl")

    respuesta = _contar(client, item, escrito)

    assert respuesta.status_code == 200
    assert respuesta.get_json()["ok"] is True
    assert db.session.get(ItemConteoInventario, item.id).cantidad_fisica == Decimal(guardado)


def test_la_diferencia_conserva_los_decimales(client, db, empresa, usuario_admin):
    item = _item(db, empresa, "CABLE-MT", 10, 10)
    login(client, "admin@test.cl")

    datos = _contar(client, item, "12,5").get_json()

    # +2,5 metros, no +2: redondear aquí es justamente lo que había que arreglar.
    assert datos["dif_qms"] == 2.5
    assert datos["dif_defontana"] == 2.5
    assert datos["tiene_diferencia"] is True


def test_contar_algo_que_no_es_numero_avisa_y_no_guarda(client, db, empresa, usuario_admin):
    item = _item(db, empresa, "CABLE-MT", 10, 10)
    login(client, "admin@test.cl")

    respuesta = _contar(client, item, "doce metros")

    assert respuesta.status_code == 400
    assert db.session.get(ItemConteoInventario, item.id).cantidad_fisica is None


def test_no_se_acepta_una_cantidad_negativa(client, db, empresa, usuario_admin):
    item = _item(db, empresa, "CABLE-MT", 10, 10)
    login(client, "admin@test.cl")

    assert _contar(client, item, "-3,5").status_code == 400
    assert db.session.get(ItemConteoInventario, item.id).cantidad_fisica is None


def test_borrar_el_conteo_sigue_funcionando(client, db, empresa, usuario_admin):
    item = _item(db, empresa, "CABLE-MT", 10, 10)
    login(client, "admin@test.cl")
    _contar(client, item, "12,5")

    _contar(client, item, "")

    assert db.session.get(ItemConteoInventario, item.id).cantidad_fisica is None


def test_la_pantalla_muestra_la_cantidad_a_la_chilena(client, db, empresa, usuario_admin):
    item = _item(db, empresa, "CABLE-MT", 10, 10)
    login(client, "admin@test.cl")
    _contar(client, item, "12,5")

    body = client.get("/inventario/stock?filtro=todos").get_data(as_text=True)

    assert "+2,5" in body           # la diferencia, con coma decimal
    assert 'value="12,5"' in body   # el campo, con el mismo formato que se vuelve a leer


# --- Lo que llega de las planillas ---


def _archivo(contenido, nombre, codificacion="utf-8"):
    import io

    from werkzeug.datastructures import FileStorage

    return FileStorage(stream=io.BytesIO(contenido.encode(codificacion)), filename=nombre)


def test_qms_puede_traer_stock_con_decimales(db, empresa):
    from app.utils.importar_conteo import importar_qms

    planilla = (
        "﻿Sucursal;Linea Negocio;Categoria;Stock;Descripción;Unidad;Código Único;ubicacion_bodega\n"
        "Casa Matriz;GOMAS;CAT;12,5;CABLE POR METRO;MT;CABLE-01;RACK\n"
    )
    importar_qms(_archivo(planilla, "qms.csv"), empresa.id)

    assert ItemConteoInventario.query.filter_by(codigo="CABLE-01").one().cantidad_qms == Decimal("12.5")


def test_defontana_puede_traer_stock_con_decimales(db, empresa):
    from app.utils.importar_conteo import importar_defontana

    planilla = (
        "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad\r\n"
        '"CABLE-01";"CABLE POR METRO";"BC";"BODEGA";"12,5";"MT"\r\n'
    )
    importar_defontana(_archivo(planilla, "def.csv", "cp1252"), empresa.id)

    item = ItemConteoInventario.query.filter_by(codigo="CABLE-01").one()
    assert item.cantidad_defontana == Decimal("12.5")


def test_el_stock_repetido_en_varias_bodegas_se_suma_con_decimales(db, empresa):
    from app.utils.importar_conteo import importar_defontana

    planilla = (
        "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad\r\n"
        '"CABLE-01";"CABLE";"BC";"BODEGA 1";"12,5";"MT"\r\n'
        '"CABLE-01";"CABLE";"BD";"BODEGA 2";"0,25";"MT"\r\n'
    )
    importar_defontana(_archivo(planilla, "def.csv", "cp1252"), empresa.id)

    assert ItemConteoInventario.query.filter_by(codigo="CABLE-01").one().cantidad_defontana == Decimal("12.75")


def test_al_cerrar_la_toma_los_decimales_quedan_en_el_archivo(client, db, empresa, usuario_admin):
    from app.models.conteo_inventario import TomaInventario

    item = _item(db, empresa, "CABLE-MT", Decimal("12.5"), Decimal("12.5"))
    item.costo_unitario_qms = 1000
    item.costo_unitario_defontana = 1000
    db.session.commit()
    login(client, "admin@test.cl")
    _contar(client, item, "10,25")

    client.post("/inventario/toma/cerrar", data={}, follow_redirects=True)

    detalle = TomaInventarioDetalle.query.one()
    assert detalle.cantidad_qms == Decimal("12.5")
    assert detalle.cantidad_fisica == Decimal("10.25")
    # La valorización archivada va en pesos enteros: 10,25 x 1.000 = 10.250
    assert TomaInventario.query.one().valor_fisico_total == 10250


# --- Valorización: la cantidad lleva decimales, la plata no ---


def test_la_valorizacion_de_una_cantidad_decimal_queda_en_pesos_enteros(db, empresa):
    item = _item(db, empresa, "CABLE-MT", Decimal("12.5"), Decimal("12.5"))
    item.costo_unitario_qms = 1001
    item.costo_unitario_defontana = 1001
    db.session.commit()

    # 12,5 x 1.001 = 12.512,5 -> se guarda y se muestra como 12.513 pesos
    assert item.valor_qms == 12513
    assert isinstance(item.valor_qms, int)
    assert item.valor_defontana == 12513
