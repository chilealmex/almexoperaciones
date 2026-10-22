"""Marcar un artículo del conteo como activo fijo.

Un activo fijo no es stock de bodega —una máquina, una herramienta mayor— pero
aparece igual en las planillas de QMS y de Defontana. Quien cuenta necesita
distinguirlo, y la marca tiene que quedar: es una propiedad del artículo, no de
la toma.
"""

import json
import re

from app.models.conteo_inventario import ItemConteoInventario
from app.models.empresa import Empresa
from tests.conftest import login


def _item(db, empresa, codigo, *, activo_fijo=False, fisica=None):
    item = ItemConteoInventario(
        empresa_id=empresa.id,
        codigo=codigo,
        nombre=f"Artículo {codigo}",
        cantidad_qms=5,
        cantidad_defontana=5,
        cantidad_fisica=fisica,
        activo_fijo=activo_fijo,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _marcar(client, item, valor):
    return client.post(
        f"/inventario/stock/{item.id}/activo-fijo",
        data=json.dumps({"activo_fijo": valor}),
        content_type="application/json",
    )


def test_un_articulo_nuevo_no_es_activo_fijo(db, empresa):
    assert _item(db, empresa, "COD-A").activo_fijo is False


def test_se_marca_y_queda_guardado(client, db, empresa, usuario_admin):
    item = _item(db, empresa, "MAQUINA")
    login(client, "admin@test.cl")

    r = _marcar(client, item, True)

    assert r.status_code == 200
    assert r.get_json()["activo_fijo"] is True
    assert db.session.get(ItemConteoInventario, item.id).activo_fijo is True


def test_se_desmarca(client, db, empresa, usuario_admin):
    item = _item(db, empresa, "MAQUINA", activo_fijo=True)
    login(client, "admin@test.cl")

    r = _marcar(client, item, False)

    assert r.get_json()["activo_fijo"] is False
    assert db.session.get(ItemConteoInventario, item.id).activo_fijo is False


def test_se_manda_el_valor_que_debe_quedar_no_un_alternar(client, db, empresa, usuario_admin):
    # Con dos personas en la misma fila, alternar deja el resultado al azar del
    # orden en que lleguen los clics. Marcar dos veces tiene que dejarlo marcado.
    item = _item(db, empresa, "MAQUINA")
    login(client, "admin@test.cl")

    _marcar(client, item, True)
    _marcar(client, item, True)

    assert db.session.get(ItemConteoInventario, item.id).activo_fijo is True


def test_el_boton_sale_en_la_fila(client, db, empresa, usuario_admin):
    _item(db, empresa, "COD-A")
    login(client, "admin@test.cl")

    body = client.get("/inventario/stock?filtro=todos").get_data(as_text=True)

    assert "boton-activo-fijo" in body
    assert "Activo fijo" in body


def test_el_filtro_muestra_solo_los_marcados(client, db, empresa, usuario_admin):
    _item(db, empresa, "MAQUINA", activo_fijo=True)
    _item(db, empresa, "TORNILLO")
    login(client, "admin@test.cl")

    body = client.get("/inventario/stock?filtro=activos_fijos").get_data(as_text=True)

    assert "MAQUINA" in body
    assert "TORNILLO" not in body


def test_el_contador_del_chip_cuenta_los_marcados(client, db, empresa, usuario_admin):
    _item(db, empresa, "MAQUINA", activo_fijo=True)
    _item(db, empresa, "PRENSA", activo_fijo=True)
    _item(db, empresa, "TORNILLO")
    login(client, "admin@test.cl")

    body = client.get("/inventario/stock?filtro=todos").get_data(as_text=True)

    # El chip trae su número al lado, como los demás: "Activos fijos (2)"
    assert re.search(r"Activos fijos\s*<span class=\"conteo\">\(2\)</span>", body)


def test_sin_permiso_de_edicion_no_se_puede_marcar(client, db, empresa, usuario_bodega):
    # El rol de bodega ve el inventario pero no lo edita.
    item = _item(db, empresa, "MAQUINA")
    login(client, "bodega@test.cl")

    r = _marcar(client, item, True)

    assert r.status_code == 403
    assert db.session.get(ItemConteoInventario, item.id).activo_fijo is False


def test_no_se_puede_marcar_un_articulo_de_otra_empresa(client, db, empresa, usuario_admin):
    otra = Empresa(rut="77.111.111-1", razon_social="Otra Empresa SPA")
    db.session.add(otra)
    db.session.commit()
    ajeno = ItemConteoInventario(
        empresa_id=otra.id, codigo="AJENO", nombre="De otra empresa",
        cantidad_qms=1, cantidad_defontana=1,
    )
    db.session.add(ajeno)
    db.session.commit()
    login(client, "admin@test.cl")

    r = _marcar(client, ajeno, True)

    assert r.status_code == 404
    assert db.session.get(ItemConteoInventario, ajeno.id).activo_fijo is False


def test_la_marca_sobrevive_al_finalizar_la_toma(client, db, empresa, usuario_admin):
    # Finalizar una toma limpia el conteo físico y saca los artículos de la
    # lista, pero que algo sea un activo fijo no cambia de una toma a otra.
    item = _item(db, empresa, "MAQUINA", activo_fijo=True, fisica=3)
    login(client, "admin@test.cl")

    client.post("/inventario/toma/cerrar", follow_redirects=True)

    guardado = db.session.get(ItemConteoInventario, item.id)
    assert guardado.activo_fijo is True
    assert guardado.cantidad_fisica is None


def test_el_excel_trae_la_columna(client, db, empresa, usuario_admin):
    _item(db, empresa, "MAQUINA", activo_fijo=True)
    login(client, "admin@test.cl")

    r = client.get("/inventario/stock.xlsx?filtro=todos")

    assert r.status_code == 200
    assert len(r.data) > 0
