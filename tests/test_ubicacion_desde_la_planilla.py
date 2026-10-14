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
from app.utils.importar_conteo import importar_defontana, importar_qms
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


def test_sin_columna_de_ubicacion_queda_en_blanco(db, empresa):
    """La sucursal no es la ubicación: es de dónde salió la planilla. Usarla de
    respaldo dejaba la misma palabra repetida en las tres mil filas, que
    contando es igual a no tener ninguna, y encima con aspecto de dato.
    """
    _subir(SIN_UBICACION, empresa)

    assert _ubicacion() is None


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


def test_la_planilla_manda_tambien_cuando_viene_vacia(db, empresa):
    """Lo que diga la columna de QMS es lo que queda, incluso vacío.

    Conservar lo anterior cuando no viene parece más seguro, pero deja para
    siempre las ubicaciones que escribieron las versiones anteriores —la
    sucursal, el nombre de la bodega de Defontana— sin ninguna forma de
    limpiarlas: no hay pantalla donde borrar una ubicación.
    """
    _subir(CON_UBICACION, empresa)
    assert _ubicacion() == "ESTANTE A3"

    _subir(CON_UBICACION.replace("ESTANTE A3", ""), empresa)

    assert _ubicacion() is None


# --- Defontana no escribe la ubicación ---
#
# Llenaba la ubicación con el nombre de la bodega ("BODEGA CENTRAL") en todo
# artículo que no tuviera una. Con una sola bodega eso es la misma palabra
# repetida en todas las filas: ocupa la columna, parece un dato y no dice dónde
# está nada. La ubicación sale sólo de la planilla de QMS.

CAB_DEFO = "CodArticulo;Descripción Artículo;CodBodega;Nombre Bodega;Saldo Stock;Unidad;Costo Unitario\r\n"


def _subir_defontana(codigo, empresa, bodega="BODEGA CENTRAL"):
    texto = CAB_DEFO + f"{codigo};PRODUCTO;B1;{bodega};10;UN;1000\r\n"
    return importar_defontana(
        FileStorage(stream=io.BytesIO(texto.encode("utf-8")), filename="defontana.csv"), empresa.id
    )


def test_defontana_no_llena_la_ubicacion_de_un_articulo_nuevo(db, empresa):
    _subir_defontana("SOLO-DEFO", empresa)

    assert ItemConteoInventario.query.one().ubicacion is None


def test_defontana_no_toca_la_ubicacion_que_puso_qms(db, empresa):
    """Es el caso que importa: el artículo está en los dos sistemas y la
    ubicación buena vino de QMS."""
    _subir(CON_UBICACION, empresa)

    _subir_defontana("ROP-BCAN-M", empresa)

    assert _ubicacion() == "ESTANTE A3"


def test_importar_defontana_sigue_cargando_lo_suyo(db, empresa):
    """No se le quitó más que la ubicación: las cantidades, la unidad y el costo
    son suyos y tienen que seguir entrando."""
    _subir_defontana("SOLO-DEFO", empresa)

    item = ItemConteoInventario.query.one()
    assert item.cantidad_defontana == 10
    assert item.unidad_defontana == "UN"
    assert item.costo_unitario_defontana == 1000
    assert item.en_defontana is True


def test_defontana_tampoco_la_llena_en_un_articulo_que_ya_existe(db, empresa):
    """El caso que de verdad pasaba: el artículo ya está en el maestro —lo trajo
    QMS— pero sin ubicación, y al importar Defontana aparecía "BODEGA CENTRAL"
    en todas las filas. El artículo nuevo es el camino fácil; este es el otro.
    """
    _subir(SIN_UBICACION, empresa)  # QMS lo crea sin ubicación
    assert _ubicacion() is None

    _subir_defontana("ROP-BCAN-M", empresa)  # ahora pasa por la actualización

    assert _ubicacion() is None


def test_el_cruce_de_prueba_dice_lo_mismo(db, empresa):
    """Esa pantalla compara dos planillas sin cargarlas, para ver qué pasaría.
    Si ahí Defontana llenara la ubicación, mostraría un cruce que no es el que
    se va a guardar.
    """
    from app.utils.cruce_prueba import comparar

    items = comparar(
        {"COD-X": {"cantidad": 5, "nombre": "PROD", "ubicacion": "", "linea_negocio": "",
                   "categoria": "", "unidad": "UN", "costo": 100}},
        {"COD-X": {"cantidad": 5, "nombre": "PROD", "bodegas": {"BODEGA CENTRAL"},
                   "unidad": "UN", "costo": 100}},
    )

    assert items[0].ubicacion is None
