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


def test_diferencia_fisica_se_compara_contra_cada_sistema(db, empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    item = ItemConteoInventario.query.filter_by(codigo="COD-002").first()
    item.cantidad_defontana = 4  # QMS dice 7, Defontana 4

    assert not item.contado
    assert item.diferencia_fisica_qms is None
    assert item.diferencia_fisica_defontana is None

    item.cantidad_fisica = 5
    assert item.contado
    assert item.diferencia_fisica_qms == -2
    assert item.diferencia_fisica_defontana == 1
    assert item.tiene_diferencia

    # los tres cuadran: deja de aparecer como diferencia
    item.cantidad_fisica = 7
    item.cantidad_defontana = 7
    assert item.diferencia_fisica_qms == 0
    assert item.diferencia_fisica_defontana == 0
    assert not item.tiene_diferencia


def test_importacion_no_escala_en_consultas_por_articulo(db, empresa):
    """Con miles de artículos, una consulta por código agota el tiempo contra la base remota."""
    from sqlalchemy import event

    filas = [
        f"Casa Matriz;GOMAS;CAT;0;0;{i};0;PRODUCTO {i};UN;COD-{i:04d};RACK" for i in range(200)
    ]
    csv_grande = CSV_QMS.splitlines()[0] + "\n" + "\n".join(filas) + "\n"

    consultas = []
    motor = db.engine

    def contar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)

    event.listen(motor, "before_cursor_execute", contar)
    try:
        importar_qms(_fs(csv_grande.encode("utf-8"), "qms.csv"), empresa.id)
    finally:
        event.remove(motor, "before_cursor_execute", contar)

    selects = [c for c in consultas if c.strip().upper().startswith("SELECT")]
    assert len(selects) <= 5, f"{len(selects)} SELECT para 200 artículos: debe ser un número fijo"


def test_textos_mas_largos_que_la_columna_se_recortan(db, empresa):
    nombre_largo = "X" * 400
    csv_largo = (
        CSV_QMS.splitlines()[0]
        + "\n"
        + f"Casa Matriz;{'L' * 200};CAT;0;0;5;0;{nombre_largo};UN;{'C' * 120};{'U' * 400}\n"
    )
    importar_qms(_fs(csv_largo.encode("utf-8"), "qms.csv"), empresa.id)

    item = ItemConteoInventario.query.first()
    assert len(item.codigo) <= 80
    assert len(item.nombre) <= 255
    assert len(item.linea_negocio) <= 120
    assert len(item.ubicacion) <= 255


def test_reimportar_no_pierde_conteo_fisico(db, empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    item.cantidad_fisica = 14
    db.session.commit()

    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.cantidad_fisica == 14
