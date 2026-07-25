import io

from werkzeug.datastructures import FileStorage

from app.models.conteo_inventario import ItemConteoInventario
from app.utils.importar_conteo import importar_qms, importar_defontana


CSV_QMS = """﻿Sucursal;Linea Negocio;Categoria; Columna1 ; Valor Total Stock CLP ;Stock;Stock Critico;Descripción;Unidad;Código Único;ubicacion_bodega
Casa Matriz;GOMAS;CAT-A;0;0;10;0;PRODUCTO UNO;UN;COD-001;RACK A1
Antofagasta;GOMAS;CAT-A;0;0;5;0;PRODUCTO UNO;UN;COD-001;
Casa Matriz;ACEROS;CAT-B;0;0;7;0;PRODUCTO DOS;UN;COD-002;RACK B2
"""

CSV_DEFONTANA = (
    "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad\r\n"
    '"COD-001";"PRODUCTO UNO";"BODEGACENTRAL";"BODEGA CENTRAL";"12";"UN"\r\n'
    '"COD-001";"PRODUCTO UNO";"BODEGAINSUMOS";"BODEGA INSUMOS";"3";"UN"\r\n'
    '"COD-003";"PRODUCTO TRES";"BODEGACENTRAL";"BODEGA CENTRAL";"8";"UN"\r\n'
)


def _fs(contenido_bytes, nombre):
    return FileStorage(stream=io.BytesIO(contenido_bytes), filename=nombre)


def test_importar_qms_agrupa_por_codigo(db, empresa):
    resultado = importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    assert resultado["total_codigos"] == 2

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.cantidad_qms == 15  # 10 + 5 sumado entre sucursales
    assert item.nombre == "PRODUCTO UNO"
    assert item.linea_negocio == "GOMAS"
    assert item.ubicacion == "RACK A1"


def test_importar_defontana_cruza_con_qms(db, empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    resultado = importar_defontana(_fs(CSV_DEFONTANA.encode("cp1252"), "def.csv"), empresa.id)
    assert resultado["total_codigos"] == 2

    cruzado = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert cruzado.cantidad_qms == 15
    assert cruzado.cantidad_defontana == 15  # 12 + 3 entre bodegas
    assert cruzado.diferencia_sistemas == 0

    solo_qms = ItemConteoInventario.query.filter_by(codigo="COD-002").first()
    assert solo_qms.cantidad_defontana == 0
    assert solo_qms.diferencia_sistemas == 7

    solo_def = ItemConteoInventario.query.filter_by(codigo="COD-003").first()
    assert solo_def.cantidad_qms == 0
    assert solo_def.diferencia_sistemas == -8


def test_diferencia_fisica(db, empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    item = ItemConteoInventario.query.filter_by(codigo="COD-002").first()

    assert item.diferencia_fisica is None
    item.cantidad_fisica = 5
    assert item.diferencia_fisica == -2  # 5 contra el mayor de los sistemas (7)
    assert item.tiene_diferencia

    item.cantidad_fisica = 7
    item.cantidad_defontana = 7
    assert not item.tiene_diferencia


def test_reimportar_no_pierde_conteo_fisico(db, empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    item.cantidad_fisica = 14
    db.session.commit()

    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.cantidad_fisica == 14
