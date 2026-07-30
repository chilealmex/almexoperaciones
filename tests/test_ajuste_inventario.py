import io

from werkzeug.datastructures import FileStorage

from app.models.conteo_inventario import ItemConteoInventario
from app.utils.importar_conteo import importar_qms, importar_defontana, _a_monto
from tests.conftest import login


CSV_QMS = """﻿Sucursal;Linea Negocio;Categoria; Valor Total Stock CLP ;Stock;Stock Critico;Descripción;Unidad;Código Único;ubicacion_bodega; Valor Unitario CLP
Casa Matriz;GOMAS;CAT-A;100000;10;0;PRODUCTO UNO;UN;COD-001;RACK A1; 10,000
Casa Matriz;ACEROS;CAT-B;70000;7;0;PRODUCTO DOS;RL;COD-002;RACK B2; 10,000
"""

CSV_DEFONTANA = (
    "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad;Costo Unitario\r\n"
    '"COD-001";"PRODUCTO UNO";"BODEGACENTRAL";"BODEGA CENTRAL";"8";"UN";"9.500"\r\n'
    '"COD-002";"PRODUCTO DOS";"BODEGACENTRAL";"BODEGA CENTRAL";"7";"UN";"10.000"\r\n'
)


def _fs(contenido, nombre):
    return FileStorage(stream=io.BytesIO(contenido), filename=nombre)


def _importar_todo(empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    importar_defontana(_fs(CSV_DEFONTANA.encode("cp1252"), "def.csv"), empresa.id)


def test_a_monto_entiende_los_formatos_de_planilla():
    assert _a_monto(" 19,563,554 ") == 19563554
    assert _a_monto("1.961.923") == 1961923
    assert _a_monto("1.234,56") == 1235
    assert _a_monto("1,234.56") == 1235
    assert _a_monto("") is None
    assert _a_monto("no es número") is None


def test_qms_carga_costo_unidad_y_categoria(db, empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()

    assert item.costo_unitario_qms == 10000
    assert item.unidad_qms == "UN"
    assert item.categoria == "CAT-A"
    assert item.valor_qms == 100000


def test_defontana_carga_su_propio_costo_y_unidad(db, empresa):
    _importar_todo(empresa)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()

    assert item.costo_unitario_defontana == 9500
    assert item.diferencia_costo_unitario == 500
    assert item.tiene_diferencia_costo
    assert item.valor_defontana == 8 * 9500
    assert item.diferencia_valor_sistemas == 100000 - 76000


def test_diferencia_de_unidad_de_medida_se_detecta(db, empresa):
    _importar_todo(empresa)

    coincide = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    distinta = ItemConteoInventario.query.filter_by(codigo="COD-002").first()

    assert coincide.unidades_coinciden
    assert distinta.unidad_qms == "RL" and distinta.unidad_defontana == "UN"
    assert not distinta.unidades_coinciden


def test_valorizacion_del_conteo_fisico(db, empresa):
    _importar_todo(empresa)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()

    assert item.valor_fisico is None  # todavía sin contar

    item.cantidad_fisica = 9
    assert item.valor_fisico == 9 * 10000
    assert item.diferencia_valor_fisico == -10000  # falta una unidad frente a QMS
    assert item.diferencia_valor_fisico_defontana == 10000  # sobra una frente a Defontana


def test_pagina_de_ajuste_filtra_y_totaliza(client, empresa, usuario_admin):
    _importar_todo(empresa)
    login(client, "admin@test.cl")

    respuesta = client.get("/inventario/ajuste")
    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "Ajuste de inventario" in cuerpo
    assert "$170.000" in cuerpo  # valorización QMS: 100.000 + 70.000

    # COD-001 tiene stock distinto entre QMS (10) y Defontana (8); COD-002 coincide (7 y 7)
    solo_dif_stock = client.get("/inventario/ajuste?filtro=dif_stock")
    assert solo_dif_stock.status_code == 200
    assert "COD-001" in solo_dif_stock.get_data(as_text=True)
    assert "COD-002" not in solo_dif_stock.get_data(as_text=True)


def test_exportacion_csv_respeta_los_filtros(client, empresa, usuario_admin):
    _importar_todo(empresa)
    login(client, "admin@test.cl")

    respuesta = client.get("/inventario/ajuste.csv?filtro=todos")
    assert respuesta.status_code == 200
    assert "text/csv" in respuesta.headers["Content-Type"]

    texto = respuesta.get_data(as_text=True)
    assert "Costo unitario QMS" in texto
    assert "COD-001" in texto and "COD-002" in texto

    respuesta = client.get("/inventario/ajuste.csv?filtro=contados")
    assert "COD-001" not in respuesta.get_data(as_text=True)  # ninguno se ha contado aún


def test_reimportar_no_altera_el_conteo_fisico_ni_su_trazabilidad(db, empresa, usuario_admin):
    """Volver a subir QMS o Defontana no debe pisar lo que contó bodega."""
    from datetime import datetime, timezone

    _importar_todo(empresa)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    momento = datetime(2026, 7, 20, 15, 30, tzinfo=timezone.utc)
    item.cantidad_fisica = 42
    item.contado_por_id = usuario_admin.id
    item.contado_en = momento
    db.session.commit()

    # Se reimportan ambos sistemas con cantidades distintas
    csv_qms_nuevo = CSV_QMS.replace(";10;0;PRODUCTO UNO", ";99;0;PRODUCTO UNO")
    importar_qms(_fs(csv_qms_nuevo.encode("utf-8"), "qms.csv"), empresa.id)
    importar_defontana(_fs(CSV_DEFONTANA.encode("cp1252"), "def.csv"), empresa.id)

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.cantidad_qms == 99  # el sistema sí se actualiza
    assert item.cantidad_fisica == 42  # el conteo físico se mantiene
    assert item.contado_por_id == usuario_admin.id
    assert item.contado_en.replace(tzinfo=timezone.utc) == momento


def test_el_conteo_guarda_quien_y_cuando(client, empresa, usuario_admin):
    """Al registrar el físico se deja constancia del usuario y del momento."""
    _importar_todo(empresa)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    login(client, "admin@test.cl")

    respuesta = client.post(f"/inventario/stock/{item.id}/contar", json={"cantidad": "7"})
    assert respuesta.status_code == 200

    datos = respuesta.get_json()
    assert datos["ok"] is True
    assert datos["registrado_por"] == usuario_admin.nombre_completo
    assert datos["registrado_en"]  # fecha y hora formateadas para la pantalla

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.cantidad_fisica == 7
    assert item.contado_por_id == usuario_admin.id
    assert item.contado_en is not None


def test_stock_muestra_unidades_y_costos_por_sku(client, empresa, usuario_admin):
    """La pantalla de stock avisa cuando unidad o costo no coinciden entre sistemas."""
    _importar_todo(empresa)
    login(client, "admin@test.cl")

    cuerpo = client.get("/inventario/stock").get_data(as_text=True)
    assert "Costo unitario" in cuerpo
    assert "Registrado por" in cuerpo
    assert "RL ≠ UN" in cuerpo  # COD-002 tiene distinta unidad en cada sistema
    assert "$10.000 ≠ $9.500" in cuerpo  # COD-001 tiene distinto costo


def test_ajuste_exige_sesion_iniciada(client, empresa):
    respuesta = client.get("/inventario/ajuste")
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]


def test_usuario_solo_lectura_ve_el_ajuste(client, empresa, usuario_bodega):
    _importar_todo(empresa)
    login(client, "bodega@test.cl")

    respuesta = client.get("/inventario/ajuste")
    assert respuesta.status_code == 200
