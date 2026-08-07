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


# --- Reabrir una toma cerrada antes de tiempo ---

def _cerrar_con_un_conteo(client, empresa):
    """Deja una toma cerrada donde COD-001 se contó (9) y COD-002 no."""
    _importar(empresa)
    login(client, "admin@test.cl")
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    client.post(f"/inventario/stock/{item.id}/contar", json={"cantidad": "9"})
    client.post("/inventario/toma/cerrar")
    return TomaInventario.query.first()


def test_reabrir_devuelve_el_conteo_al_cruce_vivo(client, empresa, usuario_admin):
    toma = _cerrar_con_un_conteo(client, empresa)

    respuesta = client.post(f"/inventario/historial/{toma.id}/reabrir", follow_redirects=True)
    assert respuesta.status_code == 200

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.cantidad_fisica == 9
    assert item.contado_por_id is not None
    assert item.contado_en is not None
    # La toma deja de ser historial: vuelve a estar en curso.
    assert TomaInventario.query.count() == 0
    assert TomaInventarioDetalle.query.count() == 0


def test_reabrir_restituye_el_stock_del_dia_en_lo_ya_contado(client, empresa, usuario_admin):
    """Sin esto el conteo quedaría comparado contra cifras posteriores."""
    toma = _cerrar_con_un_conteo(client, empresa)

    # Entre el cierre y la reapertura se reimportó stock movido.
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    item.cantidad_qms = 3
    item.cantidad_defontana = 3
    sin_contar = ItemConteoInventario.query.filter_by(codigo="COD-002").first()
    sin_contar.cantidad_qms = 55
    from app.extensions import db as _db
    _db.session.commit()

    client.post(f"/inventario/historial/{toma.id}/reabrir", follow_redirects=True)

    contado = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert contado.cantidad_qms == 10  # la foto del día del conteo
    assert contado.cantidad_defontana == 8
    assert contado.diferencia_fisica_qms == -1  # 9 contados vs 10 del sistema, como era

    # El que no se había contado conserva el stock al día: es lo que falta por contar.
    otro = ItemConteoInventario.query.filter_by(codigo="COD-002").first()
    assert otro.cantidad_qms == 55


def test_reabrir_no_pisa_un_conteo_hecho_despues(client, empresa, usuario_admin):
    """Si bodega ya volvió a contar el artículo, ese conteo es el más reciente y manda."""
    toma = _cerrar_con_un_conteo(client, empresa)

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    client.post(f"/inventario/stock/{item.id}/contar", json={"cantidad": "4"})

    respuesta = client.post(f"/inventario/historial/{toma.id}/reabrir", follow_redirects=True)
    assert "ya se contaron de nuevo" in respuesta.get_data(as_text=True)

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.cantidad_fisica == 4  # se mantiene el conteo nuevo, no el archivado


def test_reabrir_no_falla_si_el_articulo_ya_no_existe(client, empresa, usuario_admin):
    toma = _cerrar_con_un_conteo(client, empresa)

    from app.extensions import db as _db
    _db.session.delete(ItemConteoInventario.query.filter_by(codigo="COD-001").first())
    _db.session.commit()

    respuesta = client.post(f"/inventario/historial/{toma.id}/reabrir", follow_redirects=True)
    assert respuesta.status_code == 200
    assert "ya no existe" in respuesta.get_data(as_text=True)
    assert TomaInventario.query.count() == 0


def test_bodega_no_puede_reabrir_una_toma(client, empresa, usuario_admin, usuario_bodega):
    toma = _cerrar_con_un_conteo(client, empresa)
    client.get("/logout")

    login(client, "bodega@test.cl")
    respuesta = client.post(f"/inventario/historial/{toma.id}/reabrir")
    assert respuesta.status_code == 403
    assert TomaInventario.query.count() == 1  # sigue intacta


def test_el_boton_de_reabrir_pregunta_antes(client, empresa, usuario_admin):
    """El confirm debe quedar bien formado; si el atributo se corta, reabre sin preguntar."""
    toma = _cerrar_con_un_conteo(client, empresa)

    texto = client.get(f"/inventario/historial/{toma.id}").get_data(as_text=True)
    assert "Continuar esta toma" in texto
    assert "onsubmit='return confirm(" in texto
    # El mensaje va entre comillas dobles dentro de un atributo con comillas simples.
    assert 'onsubmit=\'return confirm("' in texto


def test_la_lista_del_historial_ofrece_continuar(client, empresa, usuario_admin):
    """Se debe poder retomar desde la lista, no sólo desde el detalle."""
    _cerrar_con_un_conteo(client, empresa)

    texto = client.get("/inventario/historial").get_data(as_text=True)
    assert "▶ Continuar" in texto
    assert 'onsubmit=\'return confirm("' in texto


def test_al_continuar_vuelve_quien_conto_y_cuando(client, empresa, usuario_admin):
    """Es el dato que evita que vuelvan a contar lo mismo."""
    toma = _cerrar_con_un_conteo(client, empresa)
    detalle = TomaInventarioDetalle.query.filter_by(toma_id=toma.id, codigo="COD-001").first()
    quien, cuando = detalle.contado_por_id, detalle.contado_en

    client.post(f"/inventario/historial/{toma.id}/reabrir", follow_redirects=True)

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.contado_por_id == quien
    assert item.contado_en == cuando
    assert item.contado_por.nombre_completo == "Admin de Prueba"


def test_el_excel_de_stock_muestra_quien_conto_tras_continuar(client, empresa, usuario_admin):
    """Tras retomar, la planilla que se lleva bodega ya trae persona y fecha."""
    toma = _cerrar_con_un_conteo(client, empresa)
    client.post(f"/inventario/historial/{toma.id}/reabrir", follow_redirects=True)

    respuesta = client.get("/inventario/stock.xlsx")
    assert respuesta.status_code == 200

    import openpyxl
    hoja = openpyxl.load_workbook(io.BytesIO(respuesta.data)).active
    filas = [[c.value for c in fila] for fila in hoja.iter_rows()]
    encabezado = next(f for f in filas if f and "Código" in f)
    i_por = encabezado.index("Contado por")
    i_cuando = encabezado.index("Fecha y hora del conteo")
    fila = next(f for f in filas if f and f[0] == "COD-001")
    assert fila[i_por] == "Admin de Prueba"
    assert fila[i_cuando]  # fecha y hora presentes
