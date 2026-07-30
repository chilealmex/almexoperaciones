"""Cierre e historial de tomas de inventario."""

import io

from werkzeug.datastructures import FileStorage

from app.models.conteo_inventario import ItemConteoInventario, TomaInventario, TomaInventarioDetalle
from app.utils.importar_conteo import importar_qms, importar_defontana
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


def _importar(empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    importar_defontana(_fs(CSV_DEFONTANA.encode("cp1252"), "def.csv"), empresa.id)


def test_bodega_no_puede_cerrar_una_toma(client, empresa, usuario_bodega):
    _importar(empresa)
    login(client, "bodega@test.cl")

    respuesta = client.post("/inventario/toma/cerrar")
    assert respuesta.status_code == 403
    assert TomaInventario.query.count() == 0


def test_admin_puede_cerrar_una_toma_incompleta(client, empresa, usuario_admin):
    """Se permite cerrar aunque no se haya contado el 100%."""
    _importar(empresa)
    login(client, "admin@test.cl")

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    client.post(f"/inventario/stock/{item.id}/contar", json={"cantidad": "9"})

    respuesta = client.post("/inventario/toma/cerrar", follow_redirects=True)
    assert respuesta.status_code == 200

    toma = TomaInventario.query.first()
    assert toma is not None
    assert toma.total_articulos == 2
    assert toma.articulos_contados == 1
    assert not toma.completa
    assert toma.dif_stock == 1  # solo COD-001 (10 vs 8); COD-002 tiene 7 y 7


def test_cerrar_calcula_los_totales_correctos(client, empresa, usuario_admin):
    _importar(empresa)
    login(client, "admin@test.cl")

    for codigo, cantidad in (("COD-001", 9), ("COD-002", 7)):
        item = ItemConteoInventario.query.filter_by(codigo=codigo).first()
        client.post(f"/inventario/stock/{item.id}/contar", json={"cantidad": str(cantidad)})

    client.post("/inventario/toma/cerrar")
    toma = TomaInventario.query.first()

    assert toma.articulos_contados == 2
    assert toma.completa
    assert toma.dif_stock == 1  # solo COD-001 (10 vs 8)
    assert toma.dif_costo == 1  # solo COD-001 (10.000 vs 9.500)
    assert toma.dif_unidad == 1  # solo COD-002 (RL vs UN)
    assert toma.valor_qms_total == 100000 + 70000


def test_cerrar_reinicia_el_conteo_fisico_vivo(client, empresa, usuario_admin):
    _importar(empresa)
    login(client, "admin@test.cl")
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    client.post(f"/inventario/stock/{item.id}/contar", json={"cantidad": "9"})

    client.post("/inventario/toma/cerrar")

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.cantidad_fisica is None
    assert item.contado_por_id is None
    assert item.contado_en is None
    # pero los datos de QMS/Defontana (costo, unidad, stock) se mantienen intactos
    assert item.cantidad_qms == 10
    assert item.costo_unitario_qms == 10000


def test_cerrar_archiva_una_foto_completa_por_articulo(client, empresa, usuario_admin):
    _importar(empresa)
    login(client, "admin@test.cl")
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    client.post(f"/inventario/stock/{item.id}/contar", json={"cantidad": "9"})

    client.post("/inventario/toma/cerrar")
    toma = TomaInventario.query.first()

    detalle = TomaInventarioDetalle.query.filter_by(toma_id=toma.id, codigo="COD-001").first()
    assert detalle is not None
    assert detalle.cantidad_fisica == 9
    assert detalle.cantidad_qms == 10
    assert detalle.costo_unitario_qms == 10000
    assert detalle.contado_por is not None
    # las propiedades calculadas del mixin funcionan igual que en el ítem vivo
    assert detalle.diferencia_fisica_qms == -1
    assert detalle.contado is True

    sin_contar = TomaInventarioDetalle.query.filter_by(toma_id=toma.id, codigo="COD-002").first()
    assert sin_contar.contado is False


def test_se_puede_volver_a_contar_despues_de_cerrar(client, empresa, usuario_admin):
    """El ciclo se puede repetir cuantas veces se quiera."""
    _importar(empresa)
    login(client, "admin@test.cl")
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()

    client.post(f"/inventario/stock/{item.id}/contar", json={"cantidad": "9"})
    client.post("/inventario/toma/cerrar")

    client.post(f"/inventario/stock/{item.id}/contar", json={"cantidad": "10"})
    client.post("/inventario/toma/cerrar")

    assert TomaInventario.query.count() == 2
    ultima = TomaInventario.query.order_by(TomaInventario.id.desc()).first()
    detalle = TomaInventarioDetalle.query.filter_by(toma_id=ultima.id, codigo="COD-001").first()
    assert detalle.cantidad_fisica == 10


def test_pagina_de_historial_lista_las_tomas(client, empresa, usuario_admin):
    _importar(empresa)
    login(client, "admin@test.cl")
    client.post("/inventario/toma/cerrar")

    respuesta = client.get("/inventario/historial")
    assert respuesta.status_code == 200
    assert "Historial de tomas" in respuesta.get_data(as_text=True)


def test_pagina_de_detalle_filtra_por_diferencias(client, empresa, usuario_admin):
    _importar(empresa)
    login(client, "admin@test.cl")
    client.post("/inventario/toma/cerrar")
    toma = TomaInventario.query.first()

    respuesta = client.get(f"/inventario/historial/{toma.id}?filtro=dif_unidad")
    cuerpo = respuesta.get_data(as_text=True)
    assert "COD-002" in cuerpo
    assert "COD-001" not in cuerpo


def test_exportacion_excel_del_historial(client, empresa, usuario_admin):
    _importar(empresa)
    login(client, "admin@test.cl")
    client.post("/inventario/toma/cerrar")
    toma = TomaInventario.query.first()

    respuesta = client.get(f"/inventario/historial/{toma.id}.xlsx")
    assert respuesta.status_code == 200
    assert "spreadsheetml" in respuesta.headers["Content-Type"]


def test_cerrar_sin_articulos_no_crea_toma_vacia(client, empresa, usuario_admin):
    login(client, "admin@test.cl")
    respuesta = client.post("/inventario/toma/cerrar", follow_redirects=True)
    assert respuesta.status_code == 200
    assert TomaInventario.query.count() == 0


def test_historial_exige_sesion(client, empresa):
    respuesta = client.get("/inventario/historial")
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]
