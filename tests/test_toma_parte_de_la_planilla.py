"""La toma nueva parte de la planilla nueva, no del maestro viejo.

Finalizar una toma archivaba el conteo y lo dejaba en blanco, pero los
artículos seguían todos ahí. La toma siguiente empezaba con el maestro de la
anterior, y entre una y otra pueden haber eliminado un artículo o haberlo
dejado inactivo: bodega terminaba contando cosas que ya no existen, y el avance
("786 / 3111") se medía contra un total que ya no era cierto.

Ahora al finalizar se sacan todos de la lista y cada importación devuelve los
que trae. No se borra nada: el que vuelve reaparece con su conteo en blanco, y
el que no vuelve queda guardado y fuera de la vista.
"""

import io

from werkzeug.datastructures import FileStorage

from app.models.conteo_inventario import ItemConteoInventario
from app.utils.importar_conteo import importar_qms
from tests.conftest import login

# La planilla de QMS, con los encabezados que trae de verdad.
CABECERA = "﻿Sucursal;Linea Negocio;Categoria;Stock;Descripción;Unidad;Código Único;ubicacion_bodega\n"


def _planilla(*codigos):
    filas = "".join(f"SUC;LINEA;CAT;10;PRODUCTO {c};UN;{c};BODEGA\n" for c in codigos)
    return FileStorage(stream=io.BytesIO((CABECERA + filas).encode("utf-8")),
                       filename="qms.csv")


CABECERA_DEFO = "CodArticulo;Descripción Artículo;CodBodega;Nombre Bodega;Saldo Stock;Unidad;Costo Unitario\r\n"


def _planilla_defontana(*codigos):
    filas = "".join(f"{c};PRODUCTO {c};B1;BODEGA;10;UN;1000\r\n" for c in codigos)
    return FileStorage(stream=io.BytesIO((CABECERA_DEFO + filas).encode("utf-8")),
                       filename="defontana.csv")


def _item(db, empresa, codigo, **kw):
    datos = dict(empresa_id=empresa.id, codigo=codigo, nombre="PRODUCTO " + codigo,
                 cantidad_qms=10, cantidad_defontana=10, en_qms=True, en_defontana=True)
    datos.update(kw)
    item = ItemConteoInventario(**datos)
    db.session.add(item)
    db.session.commit()
    return item


def _finalizar(client):
    return client.post("/inventario/toma/cerrar", follow_redirects=True)


def _lista(client):
    """Los códigos que Stock y conteo está mostrando."""
    html = client.get("/inventario/stock?filtro=todos&vacios=si").get_data(as_text=True)
    return [c for c in ("VIVE", "SE-FUE", "NUEVO") if c in html]


def test_al_finalizar_no_queda_nada_en_la_lista(db, empresa, usuario_admin, client):
    _item(db, empresa, "VIVE", cantidad_fisica=5)
    _item(db, empresa, "SE-FUE", cantidad_fisica=3)
    login(client, "admin@test.cl")

    _finalizar(client)

    assert _lista(client) == []
    # Pero siguen guardados: finalizar no borra el maestro.
    assert ItemConteoInventario.query.count() == 2


def test_vuelve_solo_lo_que_trae_la_planilla(db, empresa, usuario_admin, client):
    """El que ya no viene pudo haberse eliminado o desactivado. Contarlo igual
    sería contar algo que no existe."""
    _item(db, empresa, "VIVE")
    _item(db, empresa, "SE-FUE")
    login(client, "admin@test.cl")
    _finalizar(client)

    importar_qms(_planilla("VIVE"), empresa.id)

    assert _lista(client) == ["VIVE"]


def test_un_articulo_nuevo_de_la_planilla_tambien_entra(db, empresa, usuario_admin, client):
    _item(db, empresa, "VIVE")
    login(client, "admin@test.cl")
    _finalizar(client)

    importar_qms(_planilla("VIVE", "NUEVO"), empresa.id)

    assert _lista(client) == ["VIVE", "NUEVO"]


def test_la_planilla_de_defontana_tambien_los_devuelve(db, empresa, usuario_admin, client):
    """Los dos importadores alimentan la misma lista. Si sólo uno devolviera los
    artículos, quien empieza subiendo Defontana vería la pantalla vacía y
    pensaría que el archivo no entró."""
    from app.utils.importar_conteo import importar_defontana

    _item(db, empresa, "VIVE")
    _item(db, empresa, "SE-FUE")
    login(client, "admin@test.cl")
    _finalizar(client)

    importar_defontana(_planilla_defontana("VIVE"), empresa.id)

    assert _lista(client) == ["VIVE"]


def test_el_que_vuelve_llega_con_el_conteo_en_blanco(db, empresa, usuario_admin, client):
    """Es una toma nueva: el conteo de la anterior quedó en el historial."""
    _item(db, empresa, "VIVE", cantidad_fisica=5)
    login(client, "admin@test.cl")
    _finalizar(client)

    importar_qms(_planilla("VIVE"), empresa.id)

    assert ItemConteoInventario.query.filter_by(codigo="VIVE").one().cantidad_fisica is None


def test_el_avance_se_mide_contra_lo_que_hay_ahora(db, empresa, usuario_admin, client):
    """Si los contadores dijeran 3.111 sobre una lista de uno, no habría forma
    de saber cuál de los dos números creer."""
    _item(db, empresa, "VIVE")
    _item(db, empresa, "SE-FUE")
    login(client, "admin@test.cl")
    _finalizar(client)
    importar_qms(_planilla("VIVE"), empresa.id)

    html = client.get("/inventario/stock?filtro=todos&vacios=si").get_data(as_text=True)

    # La barra de avance, que es donde se lee el total de la toma.
    assert "0 / 1 (0.0%)" in html
    assert "SE-FUE" not in html


def test_la_pantalla_vacia_explica_que_se_finalizo(db, empresa, usuario_admin, client):
    """Vacía y sin explicación se parece a una pantalla rota, y "aún no hay
    stock cargado" haría pensar que finalizar borró todo."""
    _item(db, empresa, "VIVE")
    login(client, "admin@test.cl")

    _finalizar(client)
    html = client.get("/inventario/stock").get_data(as_text=True)

    assert "La toma anterior se finalizó" in html
    assert "No se borró nada" in html
    assert "Aún no hay stock cargado" not in html


def test_sin_nada_cargado_nunca_el_aviso_es_el_otro(db, empresa, usuario_admin, client):
    """Dos pantallas vacías que se ven igual y significan cosas distintas."""
    login(client, "admin@test.cl")

    html = client.get("/inventario/stock").get_data(as_text=True)

    assert "Aún no hay stock cargado" in html
    assert "La toma anterior se finalizó" not in html


def test_continuar_una_toma_la_devuelve_entera(db, empresa, usuario_admin, client):
    """Continuar es deshacer el cierre. Sin esto, retomarla mostraba la pantalla
    vacía con los conteos restituidos y escondidos."""
    from app.models.conteo_inventario import TomaInventario

    _item(db, empresa, "VIVE", cantidad_fisica=5)
    login(client, "admin@test.cl")
    _finalizar(client)
    toma = TomaInventario.query.one()

    client.post(f"/inventario/historial/{toma.id}/reabrir", follow_redirects=True)

    assert _lista(client) == ["VIVE"]
    assert ItemConteoInventario.query.one().cantidad_fisica == 5


def test_el_excel_muestra_lo_mismo_que_la_pantalla(db, empresa, usuario_admin, client):
    """El archivo descargado es el registro de lo que se está viendo."""
    import openpyxl

    _item(db, empresa, "VIVE")
    _item(db, empresa, "SE-FUE")
    login(client, "admin@test.cl")
    _finalizar(client)
    importar_qms(_planilla("VIVE"), empresa.id)

    datos = client.get("/inventario/stock.xlsx").data
    hoja = openpyxl.load_workbook(io.BytesIO(datos)).active
    textos = [str(c.value) for fila in hoja.iter_rows() for c in fila]

    assert "VIVE" in textos
    assert "SE-FUE" not in textos
