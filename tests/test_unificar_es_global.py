"""Unificar un código vale en todos los submódulos de Inventario.

El maestro de artículos es uno solo: Stock y conteo, Ajuste inventario, Cruce
de datos, Regularización y Unificar códigos leen la misma tabla. Unir dos
líneas tiene que dejar una sola, y esa sola es la que ven todos. Si alguna vía
sólo guardara la decisión sin juntar las filas, el código viejo seguiría
apareciendo en las otras pantallas hasta la próxima importación.
"""

from app.models.conteo_inventario import ItemConteoInventario
from app.models.equivalencia_codigo import EquivalenciaCodigo
from app.models.codigo_unificado import CodigoUnificado
from app.utils.importar_conteo import clave_sin_ceros
from tests.conftest import login

# Las pantallas que listan artículos del maestro. Si el código viejo sobrevive
# en alguna, es que la unión no fue completa.
#
# Unificar códigos no está acá a propósito: ahí el código retirado sí se sigue
# viendo, en la lista de lo ya unido, que es lo que permite deshacerlo. Son dos
# cosas distintas: aparecer como artículo vivo y aparecer en el historial.
PANTALLAS = {
    "Stock y conteo": "/inventario/stock?vacios=si",
    "Ajuste inventario": "/inventario/ajuste?vacios=si",
    "Cruce de datos": "/inventario/cruce-datos?vacios=si",
    "Resumen": "/inventario/",
}


def _item(db, empresa, codigo, **campos):
    item = ItemConteoInventario(empresa_id=empresa.id, codigo=codigo, **campos)
    db.session.add(item)
    db.session.commit()
    return item


def _donde_aparece(client, codigo):
    return [
        nombre for nombre, url in PANTALLAS.items()
        if codigo in client.get(url).get_data(as_text=True)
    ]


def test_unir_dos_lineas_del_mismo_codigo_vale_en_todas_las_pantallas(
    client, db, empresa, usuario_admin
):
    """La primera vía: el mismo código escrito distinto."""
    _item(db, empresa, "011-CON-OTH-01", nombre="RELAY", en_qms=False, en_defontana=False)
    _item(db, empresa, "11-CON-OTH-01", nombre="RELAY", en_qms=True, en_defontana=True,
          cantidad_qms=5, cantidad_defontana=5)
    login(client, "admin@test.cl")
    assert _donde_aparece(client, "011-CON-OTH-01"), "sin unir, el viejo se ve en alguna parte"

    client.post("/inventario/conteo/duplicados/unificar",
                data={"clave": clave_sin_ceros("011-CON-OTH-01")}, follow_redirects=True)

    assert ItemConteoInventario.query.count() == 1
    assert _donde_aparece(client, "011-CON-OTH-01") == []
    # Pero sí queda registrado, para poder deshacerlo
    assert "011-CON-OTH-01" in client.get("/inventario/equivalencias").get_data(as_text=True)


def test_unir_dos_codigos_distintos_vale_en_todas_las_pantallas(
    client, db, empresa, usuario_admin
):
    """La segunda vía: códigos distintos en cada sistema. Acá la unión no sólo
    se guarda: las dos filas se juntan en el acto. Si sólo se guardara, el
    código de Defontana seguiría siendo una fila aparte en las otras pantallas
    hasta la próxima importación."""
    _item(db, empresa, "GOL.PRE-5_8", nombre="GOLILLA", en_qms=True, en_defontana=False,
          cantidad_qms=4)
    _item(db, empresa, "GOLPRE-58", nombre="GOL.PRESION", en_qms=False, en_defontana=True,
          cantidad_defontana=4, costo_unitario_defontana=900)
    login(client, "admin@test.cl")

    client.post("/inventario/equivalencias/unir",
                data={"codigo_qms": "GOL.PRE-5_8", "codigo_defontana": "GOLPRE-58"},
                follow_redirects=True)

    assert ItemConteoInventario.query.count() == 1
    assert _donde_aparece(client, "GOLPRE-58") == []
    assert "GOLPRE-58" in client.get("/inventario/equivalencias").get_data(as_text=True)
    # Y la que queda trae los dos lados: ya no "falta en" ninguno
    queda = ItemConteoInventario.query.one()
    assert queda.en_qms and queda.en_defontana
    assert queda.falta_en == ""
    assert queda.cantidad_defontana == 4
    assert queda.costo_unitario_defontana == 900


def test_el_conteo_fisico_sobrevive_a_las_dos_vias(client, db, empresa, usuario_admin):
    """Contar es trabajo de bodega: no se pierde por unir."""
    _item(db, empresa, "GOL.PRE-5_8", en_qms=True, en_defontana=False)
    _item(db, empresa, "GOLPRE-58", en_qms=False, en_defontana=True, cantidad_fisica=7)
    login(client, "admin@test.cl")

    client.post("/inventario/equivalencias/unir",
                data={"codigo_qms": "GOL.PRE-5_8", "codigo_defontana": "GOLPRE-58"},
                follow_redirects=True)

    assert ItemConteoInventario.query.one().cantidad_fisica == 7


def test_la_union_sobrevive_a_la_siguiente_importacion(client, db, empresa, usuario_admin):
    """Lo que vale es que la decisión quede guardada: si no, la planilla
    —que sigue trayendo los dos códigos— volvería a crear la fila que se
    retiró, y habría que rehacer la unión en cada carga."""
    import io

    from werkzeug.datastructures import FileStorage

    from app.utils.importar_conteo import importar_defontana

    _item(db, empresa, "GOL.PRE-5_8", en_qms=True, en_defontana=False)
    _item(db, empresa, "GOLPRE-58", en_qms=False, en_defontana=True)
    login(client, "admin@test.cl")
    client.post("/inventario/equivalencias/unir",
                data={"codigo_qms": "GOL.PRE-5_8", "codigo_defontana": "GOLPRE-58"},
                follow_redirects=True)
    assert EquivalenciaCodigo.query.count() == 1

    planilla = (
        "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad\r\n"
        '"GOLPRE-58";"GOL.PRESION";"BODEGACENTRAL";"BODEGA CENTRAL";"9";"UN"\r\n'
    )
    importar_defontana(
        FileStorage(stream=io.BytesIO(planilla.encode("cp1252")), filename="d.csv"), empresa.id
    )

    assert ItemConteoInventario.query.count() == 1, "la planilla no puede recrear la fila retirada"
    queda = ItemConteoInventario.query.one()
    assert queda.codigo == "GOL.PRE-5_8"
    assert queda.cantidad_defontana == 9   # el stock fue a la fila que quedó


def test_unificar_duplicados_tambien_sobrevive_a_la_importacion(
    client, db, empresa, usuario_admin
):
    import io

    from werkzeug.datastructures import FileStorage

    from app.utils.importar_conteo import importar_defontana

    _item(db, empresa, "011-AAA-01", en_qms=False, en_defontana=False)
    _item(db, empresa, "11-AAA-01", en_qms=True, en_defontana=True)
    login(client, "admin@test.cl")
    client.post("/inventario/conteo/duplicados/unificar",
                data={"clave": clave_sin_ceros("011-AAA-01")}, follow_redirects=True)
    assert CodigoUnificado.query.count() == 1

    planilla = (
        "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad\r\n"
        '"011-AAA-01";"X";"BODEGACENTRAL";"BODEGA CENTRAL";"3";"UN"\r\n'
    )
    importar_defontana(
        FileStorage(stream=io.BytesIO(planilla.encode("cp1252")), filename="d.csv"), empresa.id
    )

    assert ItemConteoInventario.query.count() == 1
    assert ItemConteoInventario.query.one().codigo == "11-AAA-01"
