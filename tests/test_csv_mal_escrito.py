"""Planillas .csv con las comillas mal escritas.

Un campo que lleva comillas dentro —un código como 'LAX Bar Set 96"'— se
exporta mal cada tanto: la comilla no viene duplicada y el lector se come el
separador siguiente. El código se traga la descripción, todas las columnas se
corren una, y no falla nada: queda un artículo fantasma con un código imposible
y se pierde el de verdad, sin que nadie lo note.
"""

import io

import pytest
from werkzeug.datastructures import FileStorage

from app.models.conteo_inventario import ItemConteoInventario
from app.utils.importar_conteo import _filas_del_csv, importar_defontana, importar_qms

CABECERA = "CodArticulo;Descripción;Saldo Stock;Nombre Bodega;Unidad\r\n"
BIEN = CABECERA + '"LAX Bar Set 96""";"SET DE BARRAS LAX L96";"1";"BODEGA";"UN"\r\n'
MAL = CABECERA + '"LAX Bar Set 96"";"SET DE BARRAS LAX L96";"1";"BODEGA";"UN"\r\n'


def _fs(texto, nombre="d.csv", codificacion="cp1252"):
    return FileStorage(stream=io.BytesIO(texto.encode(codificacion)), filename=nombre)


def test_la_fila_mal_escrita_queda_igual_que_la_bien_escrita():
    """Es la prueba que importa: si no quedaran iguales, el mismo artículo
    entraría con dos códigos distintos según cómo lo exportó el sistema."""
    _cab, bien, rotas_bien = _filas_del_csv(BIEN)
    _cab, mal, rotas_mal = _filas_del_csv(MAL)

    assert bien == mal
    assert rotas_bien == 0 and rotas_mal == 1


def test_el_codigo_conserva_la_comilla_que_es_parte_del_dato():
    """Sacarla de más lo convierte en otro código, que no cruza con el de la
    planilla que vino bien escrita."""
    _cab, filas, _rotas = _filas_del_csv(MAL)

    assert filas[0]["CodArticulo"] == 'LAX Bar Set 96"'


def test_el_codigo_no_se_traga_la_descripcion(db, empresa):
    """Lo que ella vio: el código con la descripción pegada y el nombre vacío."""
    importar_defontana(_fs(MAL), empresa.id)

    item = ItemConteoInventario.query.one()
    assert ";" not in item.codigo
    assert item.nombre == "SET DE BARRAS LAX L96"


def test_las_columnas_no_se_corren(db, empresa):
    """Al tragarse un separador, todo lo de la derecha se corre un lugar: el
    stock queda con el nombre de la bodega y la unidad con el stock."""
    importar_defontana(_fs(MAL), empresa.id)

    item = ItemConteoInventario.query.one()
    assert item.cantidad_defontana == 1
    assert item.unidad_defontana == "UN"


# --- Y lo que ya funcionaba tiene que seguir igual ---


@pytest.mark.parametrize("descripcion, esperado", [
    ('"TUERCA 1/2; GRADO 8"', "TUERCA 1/2; GRADO 8"),   # punto y coma dentro del campo
    ('"COMILLAS ""DOBLES"" ADENTRO"', 'COMILLAS "DOBLES" ADENTRO'),
    ("SIN COMILLAS", "SIN COMILLAS"),
])
def test_los_casos_normales_se_siguen_leyendo_igual(db, empresa, descripcion, esperado):
    texto = CABECERA + f'"COD-001";{descripcion};"5";"BODEGA";"UN"\r\n'
    importar_defontana(_fs(texto), empresa.id)

    assert ItemConteoInventario.query.one().nombre == esperado


def test_una_descripcion_partida_en_dos_lineas_se_junta(db, empresa):
    """Comillas sin cerrar al final de la línea es el caso legítimo, y se ve
    igual que el roto: la diferencia es si quedaron balanceadas."""
    texto = CABECERA + '"COD-003";"PRIMERA LINEA\r\nSEGUNDA LINEA";"3";"BODEGA";"UN"\r\n'

    importar_defontana(_fs(texto), empresa.id)

    item = ItemConteoInventario.query.one()
    assert "PRIMERA LINEA" in item.nombre and "SEGUNDA LINEA" in item.nombre
    assert item.cantidad_defontana == 3


def test_un_archivo_bien_escrito_no_se_declara_roto():
    """Si una planilla sana entrara por el camino de recuperación, un punto y
    coma dentro de una descripción partiría la fila en dos."""
    texto = CABECERA + '"COD-002";"TUERCA 1/2; GRADO 8";"7";"BODEGA";"UN"\r\n'

    _cab, filas, rotas = _filas_del_csv(texto)

    assert rotas == 0
    assert filas[0]["Descripción"] == "TUERCA 1/2; GRADO 8"


def test_tambien_vale_para_la_planilla_de_qms(db, empresa):
    texto = (
        "﻿Sucursal;Linea Negocio;Categoria;Stock;Descripción;Unidad;Código Único;ubicacion_bodega\r\n"
        '"Casa Matriz";"GOMAS";"CAT";"5";"SET DE BARRAS";"UN";"LAX Bar Set 96"";"RACK"\r\n'
    )

    importar_qms(_fs(texto, "q.csv", "utf-8-sig"), empresa.id)

    item = ItemConteoInventario.query.one()
    assert ";" not in item.codigo
    assert item.cantidad_qms == 5


def test_un_archivo_vacio_no_revienta():
    assert _filas_del_csv("") == ([], [], 0)
    assert _filas_del_csv("\r\n\r\n") == ([], [], 0)
