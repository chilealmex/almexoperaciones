"""La bodega del artículo, en su propia columna.

La bodega es el recinto y la ubicación el lugar dentro de él ("Estante A3 /
Nivel 2"): contando, son dos datos distintos. Defontana ya mandaba la bodega en
sus planillas y se leía sin guardarla; QMS puede traerla en su propia columna.
"""

import io

from werkzeug.datastructures import FileStorage

from app.models.conteo_inventario import ItemConteoInventario
from app.utils.importar_conteo import importar_defontana, importar_qms
from tests.conftest import login


def _fs(texto, nombre):
    return FileStorage(stream=io.BytesIO(texto.encode("utf-8")), filename=nombre)


DEFONTANA = (
    "CodArticulo;Descripción Artículo;CodBodega;Nombre Bodega;Saldo Stock;Unidad\r\n"
    '"COD-001";"PRODUCTO UNO";"BC";"BODEGA CENTRAL";"12";"UN"\r\n'
    '"COD-001";"PRODUCTO UNO";"BI";"BODEGA INSUMOS";"3";"UN"\r\n'
    '"COD-003";"PRODUCTO TRES";"BC";"BODEGA CENTRAL";"8";"UN"\r\n'
)

# QMS con las dos columnas separadas: la bodega y, aparte, dónde está dentro.
QMS_CON_BODEGA = (
    "Código Único;Descripción;Stock;Unidad;Bodega;Ubicación\n"
    "COD-100;PRODUCTO CIEN;4;UN;BODEGA CENTRAL;ESTANTE A3\n"
)

# El export del sistema: trae "ubicacion_bodega", que es la ubicación.
QMS_EXPORT = (
    "Código Único;Descripción;Stock;Unidad;ubicacion_bodega\n"
    "COD-200;PRODUCTO DOSCIENTOS;6;UN;RACK B2\n"
)


def test_defontana_guarda_la_bodega(db, empresa):
    importar_defontana(_fs(DEFONTANA, "defontana.csv"), empresa.id)

    uno = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    tres = ItemConteoInventario.query.filter_by(codigo="COD-003").first()
    # Un artículo puede estar en varias: quedarse con la primera mandaría a
    # buscarlo a la bodega equivocada.
    assert uno.bodega == "BODEGA CENTRAL, BODEGA INSUMOS"
    assert tres.bodega == "BODEGA CENTRAL"


def test_qms_lee_su_columna_de_bodega(db, empresa):
    importar_qms(_fs(QMS_CON_BODEGA, "qms.csv"), empresa.id)

    item = ItemConteoInventario.query.filter_by(codigo="COD-100").first()
    assert item.bodega == "BODEGA CENTRAL"
    assert item.ubicacion == "ESTANTE A3"


def test_ubicacion_bodega_del_export_no_se_toma_como_bodega(db, empresa):
    # "ubicacion_bodega" es la ubicación. Si se leyera también como bodega, la
    # columna nueva repetiría el estante y no diría en qué recinto está.
    importar_qms(_fs(QMS_EXPORT, "qms.csv"), empresa.id)

    item = ItemConteoInventario.query.filter_by(codigo="COD-200").first()
    assert item.ubicacion == "RACK B2"
    assert item.bodega is None


def test_una_planilla_sin_la_columna_no_borra_la_bodega(db, empresa):
    importar_qms(_fs(QMS_CON_BODEGA, "qms.csv"), empresa.id)
    sin_bodega = "Código Único;Descripción;Stock;Unidad\nCOD-100;PRODUCTO CIEN;9;UN\n"

    importar_qms(_fs(sin_bodega, "qms2.csv"), empresa.id)

    item = ItemConteoInventario.query.filter_by(codigo="COD-100").first()
    assert item.cantidad_qms == 9  # la cantidad sí se actualiza
    assert item.bodega == "BODEGA CENTRAL"  # y lo escrito una vez no se pierde


def test_la_bodega_se_ve_y_se_filtra_en_la_pantalla(client, db, empresa, usuario_admin):
    importar_defontana(_fs(DEFONTANA, "defontana.csv"), empresa.id)
    login(client, "admin@test.cl")

    body = client.get("/inventario/stock?filtro=todos").get_data(as_text=True)
    assert "BODEGA INSUMOS" in body
    assert "f_bodega" in body  # el filtro bajo el título de la columna
    # En la tabla y en la tarjeta del celular: la tarjeta sola no basta, en el
    # computador la columna es donde se mira.
    assert 'class="celda-bodega"' in body
    assert body.count("BODEGA INSUMOS") >= 2

    solo_insumos = client.get(
        "/inventario/stock?filtro=todos&f_bodega=INSUMOS"
    ).get_data(as_text=True)
    assert "COD-001" in solo_insumos
    assert "COD-003" not in solo_insumos


def test_la_plantilla_de_qms_pide_la_bodega(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    r = client.get("/inventario/conteo/importar/plantilla-qms")

    assert r.status_code == 200
    import openpyxl

    hoja = openpyxl.load_workbook(io.BytesIO(r.data)).active
    titulos = [c.value for c in hoja[1]]
    assert "Bodega" in titulos
    assert "Ubicación" in titulos
