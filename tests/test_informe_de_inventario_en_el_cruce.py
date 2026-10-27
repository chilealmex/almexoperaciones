"""Cruzar usando el Informe de Inventario de Defontana.

Defontana da dos planillas de stock y las dos sirven: el export por bodega
("CodArticulo", "Saldo Stock", "Nombre Bodega") y el Informe de Inventario
("Código Artículo", "Saldo", "Bodega", "Valorización"). El segundo es el que ya
se usa en Regularización, así que pedir el otro obligaba a bajar dos veces lo
mismo.

Trae dos complicaciones propias: empieza con tres líneas de título antes de los
nombres de las columnas, y a veces manda las dos columnas de valor con los
títulos cambiados de lugar.
"""

import io

import openpyxl
from werkzeug.datastructures import FileStorage

from app.utils.importar_conteo import leer_defontana
from tests.conftest import login


def _xlsx(filas):
    libro = openpyxl.Workbook()
    hoja = libro.active
    for fila in filas:
        hoja.append(fila)
    buffer = io.BytesIO()
    libro.save(buffer)
    buffer.seek(0)
    return buffer


def _informe(*datos, titulos=("Valor unidad", "Total")):
    """El Informe de Inventario tal como se descarga, con su cabecera arriba."""
    return _xlsx([
        ["Informe de Inventario"],
        ["Empresa: Shaw Almex Chile SpA"],
        ["Fecha de generación: 26-10-2026, 08:03 a. m."],
        [],
        ["Código Artículo", "Descripción", "Bodega", "Saldo", "Unidad", titulos[0], titulos[1]],
        *datos,
    ])


def _leer(buffer, nombre="Informe_Inventario.xlsx"):
    return leer_defontana(FileStorage(stream=buffer, filename=nombre))


def test_se_lee_el_informe_de_inventario():
    datos = _leer(_informe(
        ["00-FSR-OTH-01", "TUERCAS", "BODEGA CENTRAL", 13, "UN", 5596.25, 72751.25],
        ["OTRO", "OTRO ARTICULO", "BODEGA INSUMOS", 4, "UN", 1000, 4000],
    ))

    assert set(datos) == {"00-FSR-OTH-01", "OTRO"}
    uno = datos["00-FSR-OTH-01"]
    assert float(uno["cantidad"]) == 13
    assert uno["costo"] == 5596
    assert uno["bodegas"] == {"BODEGA CENTRAL"}
    assert uno["nombre"] == "TUERCAS"


def test_las_tres_lineas_de_titulo_no_estorban():
    # Antes se tomaba la primera fila como cabecera y el archivo se rechazaba
    # entero: "No se encontraron las columnas de código/stock esperadas".
    datos = _leer(_informe(["AAA", "PROD", "BODEGA CENTRAL", 2, "UN", 500, 1000]))

    assert "AAA" in datos


def test_con_los_titulos_de_valor_cambiados_el_costo_sigue_bien():
    # El informe del 21-10 dice "Valorización | Valor Unidad" y trae el unitario
    # en la primera: leerlo por el título dejaba el costo dividido por el saldo,
    # 5.596,25 entre 13 unidades = 430.
    datos = _leer(_informe(
        ["00-FSR-OTH-01", "TUERCAS", "BODEGA CENTRAL", 13, "UN", 5596.25, 72751.25],
        ["OTRO", "OTRO ARTICULO", "BODEGA CENTRAL", 4, "UN", 1000, 4000],
        titulos=("Valorización", "Valor Unidad"),
    ))

    assert datos["00-FSR-OTH-01"]["costo"] == 5596


def test_con_los_titulos_en_su_orden_no_se_cambia_nada():
    # La misma cabecera, pero con los datos como los títulos dicen.
    datos = _leer(_informe(
        ["00-FSR-OTH-01", "TUERCAS", "BODEGA CENTRAL", 13, "UN", 72751.25, 5596.25],
        ["OTRO", "OTRO ARTICULO", "BODEGA CENTRAL", 4, "UN", 4000, 1000],
        titulos=("Valorización", "Valor Unidad"),
    ))

    assert datos["00-FSR-OTH-01"]["costo"] == 5596


def test_el_valor_unitario_en_cero_no_deja_el_producto_sin_costo():
    # Esa columna llega en 0 para muchos productos valorizados: el costo de
    # verdad es el valorizado dividido por el saldo.
    datos = _leer(_informe(["BRP-003", "BROCHA", "BODEGA CENTRAL", 209, "UN", 0, 943448]))

    assert datos["BRP-003"]["costo"] == 4514  # 943.448 ÷ 209


def test_el_export_de_siempre_sigue_funcionando():
    csv = (
        "CodArticulo;Descripción Artículo;CodBodega;Nombre Bodega;Saldo Stock;Unidad;Costo Unitario\r\n"
        '"COD-001";"PRODUCTO UNO";"BC";"BODEGA CENTRAL";"8";"UN";"9.500"\r\n'
    )
    datos = leer_defontana(FileStorage(
        stream=io.BytesIO(csv.encode("utf-8")), filename="defontana.csv"))

    assert float(datos["COD-001"]["cantidad"]) == 8
    assert datos["COD-001"]["costo"] == 9500
    assert datos["COD-001"]["bodegas"] == {"BODEGA CENTRAL"}


def test_la_pantalla_de_comparar_lo_acepta(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    qms = (
        "Código Único;Descripción;Stock;Unidad; Valor Unitario CLP \n"
        "00-FSR-OTH-01;TUERCAS;13;UN; 5.600 \n"
    )

    r = client.post(
        "/inventario/cruce-datos/prueba",
        data={
            "archivo_qms": (io.BytesIO(qms.encode("utf-8")), "qms.csv"),
            "archivo_defontana": (
                _informe(["00-FSR-OTH-01", "TUERCAS", "BODEGA CENTRAL", 13, "UN", 5596.25, 72751.25]),
                "Informe_Inventario.xlsx",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    cuerpo = r.get_data(as_text=True)
    assert r.status_code == 200
    # Si el archivo se rechazara, la pantalla mostraría el error en vez del cruce.
    assert "No se encontraron las columnas" not in cuerpo
    assert "00-FSR-OTH-01" in cuerpo
