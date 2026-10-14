"""La ubicación se puede cargar y corregir desde la planilla de QMS.

Contando, la ubicación es con lo que bodega camina a buscar el artículo. Pero
la plantilla que se descarga no la pedía: sólo tenía "Sucursal", y el
importador caía en ella, así que todos los artículos de una bodega quedaban con
la misma ubicación —el nombre de la bodega— y eso manda a recorrerla entera.

Y aunque se hubiera agregado la columna, no habría servido: para un artículo
que ya existe el importador conservaba la ubicación que tenía y descartaba la
del archivo. Como no hay ninguna pantalla donde escribirla, no había forma de
corregir una ubicación nunca.
"""

import io

from werkzeug.datastructures import FileStorage

from app.models.conteo_inventario import ItemConteoInventario
from app.utils.importar_conteo import importar_qms
from tests.conftest import login

# La plantilla que se descarga, con su columna nueva.
CON_UBICACION = (
    "Código único;Descripción;Stock;Linea Negocio;Sucursal;Ubicación;Unidad\n"
    "ROP-BCAN-M;Roldana;12;Repuestos;Bodega Central;ESTANTE A3;UN\n"
)
# La misma planilla como estaba antes: sin columna de ubicación.
SIN_UBICACION = (
    "Código único;Descripción;Stock;Linea Negocio;Sucursal;Unidad\n"
    "ROP-BCAN-M;Roldana;12;Repuestos;Bodega Central;UN\n"
)
# El export de verdad de QMS, que la trae con el nombre del sistema.
DEL_SISTEMA = (
    "Código único;Descripción;Stock;Linea Negocio;Sucursal;ubicacion_bodega;Unidad\n"
    "ROP-BCAN-M;Roldana;12;Repuestos;Bodega Central;PASILLO 7;UN\n"
)


def _subir(texto, empresa):
    return importar_qms(
        FileStorage(stream=io.BytesIO(texto.encode("utf-8")), filename="qms.csv"), empresa.id
    )


def _ubicacion():
    return ItemConteoInventario.query.one().ubicacion


def test_la_plantilla_pide_la_ubicacion(db, empresa, usuario_admin, client):
    """Es lo que se descarga para llenar a mano: si no la pide, no llega nunca."""
    import openpyxl

    login(client, "admin@test.cl")

    datos = client.get("/inventario/conteo/importar/plantilla-qms").data
    hoja = openpyxl.load_workbook(io.BytesIO(datos)).active
    textos = [str(c.value) for fila in hoja.iter_rows() for c in fila]

    assert "Ubicación" in textos


def test_se_carga_la_ubicacion_escrita_a_mano(db, empresa):
    """La plantilla la llena una persona, así que la columna no puede llamarse
    "ubicacion_bodega": se reconoce también escrita como "Ubicación"."""
    _subir(CON_UBICACION, empresa)

    assert _ubicacion() == "ESTANTE A3"


def test_sin_columna_de_ubicacion_sigue_quedando_la_sucursal(db, empresa):
    """Es lo que pasaba antes y no se rompe: la sucursal es menos precisa que un
    estante, pero dejar la celda vacía manda a recorrer la bodega entera."""
    _subir(SIN_UBICACION, empresa)

    assert _ubicacion() == "Bodega Central"


def test_el_export_del_sistema_sigue_mandando(db, empresa):
    """QMS la trae como "ubicacion_bodega". Reconocer el nombre amistoso no
    puede costar el del sistema, que es el archivo que se sube siempre."""
    _subir(DEL_SISTEMA, empresa)

    assert _ubicacion() == "PASILLO 7"


def test_si_vienen_las_dos_manda_la_del_sistema(db, empresa):
    """"Ubicación" va primera a propósito: buscando por el texto "ubicaci" gana
    la que aparezca antes, así que con el orden al revés la preferencia no se
    estaría comprobando: las dos formas darían el mismo resultado.
    """
    _subir(
        "Código único;Descripción;Stock;Sucursal;Ubicación;ubicacion_bodega;Unidad\n"
        "ROP-BCAN-M;Roldana;12;Bodega Central;ESTANTE A3;PASILLO 7;UN\n",
        empresa,
    )

    assert _ubicacion() == "PASILLO 7"


def test_se_puede_corregir_la_ubicacion_de_un_articulo_que_ya_existe(db, empresa):
    """Es el punto de todo esto. No hay ninguna pantalla donde escribirla, así
    que si la importación no la actualiza, una ubicación mal puesta queda mal
    para siempre."""
    _subir(CON_UBICACION, empresa)

    _subir(CON_UBICACION.replace("ESTANTE A3", "ESTANTE B1"), empresa)

    assert _ubicacion() == "ESTANTE B1"


def test_la_sucursal_no_pisa_una_ubicacion_que_ya_estaba(db, empresa):
    """La protección que existía, y que hay que conservar: un archivo sin
    columna de ubicación no puede reemplazar un estante por el nombre de la
    bodega de la que salió la planilla."""
    _subir(CON_UBICACION, empresa)

    _subir(SIN_UBICACION, empresa)

    assert _ubicacion() == "ESTANTE A3"
