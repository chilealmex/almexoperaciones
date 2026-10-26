"""La bodega y la marca de activo fijo, en el informe de una toma cerrada.

Al cerrar una toma se guarda una foto de cada artículo. Esa foto no llevaba las
dos columnas, así que el Excel del historial no las podía mostrar — justo
donde se va a mirar lo que se contó.

Las dos son propiedades del artículo y no del conteo: no cambian de una toma a
otra. Por eso, en una toma cerrada antes de que existieran, se completan con lo
que el artículo tiene hoy.
"""

import io

import openpyxl

from app.models.conteo_inventario import (
    ItemConteoInventario,
    TomaInventario,
    TomaInventarioDetalle,
)
from tests.conftest import login


def _item(db, empresa, codigo, *, activo_fijo=False, bodega=None, fisica=3):
    item = ItemConteoInventario(
        empresa_id=empresa.id, codigo=codigo, nombre=f"Artículo {codigo}",
        cantidad_qms=5, cantidad_defontana=5, cantidad_fisica=fisica,
        activo_fijo=activo_fijo, bodega=bodega,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _cerrar(client):
    return client.post("/inventario/toma/cerrar", follow_redirects=True)


def _hoja(client, toma_id):
    r = client.get(f"/inventario/historial/{toma_id}.xlsx")
    assert r.status_code == 200
    return openpyxl.load_workbook(io.BytesIO(r.data)).active


def _fila_de(hoja, codigo):
    titulos = None
    for fila in hoja.iter_rows(values_only=True):
        if fila and fila[0] == "Código":
            titulos = list(fila)
            continue
        if titulos and fila and fila[0] == codigo:
            return dict(zip(titulos, fila))
    raise AssertionError(f"no encontré {codigo} en la hoja")


def test_la_foto_de_la_toma_guarda_las_dos_columnas(client, db, empresa, usuario_admin):
    _item(db, empresa, "MAQUINA", activo_fijo=True, bodega="BODEGA CENTRAL")
    login(client, "admin@test.cl")

    _cerrar(client)

    d = TomaInventarioDetalle.query.filter_by(codigo="MAQUINA").first()
    assert d.activo_fijo is True
    assert d.bodega == "BODEGA CENTRAL"


def test_el_excel_de_la_toma_las_muestra(client, db, empresa, usuario_admin):
    _item(db, empresa, "MAQUINA", activo_fijo=True, bodega="BODEGA CENTRAL")
    _item(db, empresa, "TORNILLO", bodega="BODEGA INSUMOS")
    login(client, "admin@test.cl")
    _cerrar(client)
    toma = TomaInventario.query.first()

    hoja = _hoja(client, toma.id)

    maquina = _fila_de(hoja, "MAQUINA")
    tornillo = _fila_de(hoja, "TORNILLO")
    assert maquina["Activo fijo"] == "Sí"
    assert maquina["Bodega"] == "BODEGA CENTRAL"
    # Lo que no es activo fijo queda vacío, no "No": la columna se filtra por
    # lo que sí lo es.
    assert tornillo["Activo fijo"] in (None, "")
    assert tornillo["Bodega"] == "BODEGA INSUMOS"


def test_una_toma_vieja_se_completa_con_lo_que_el_articulo_tiene_hoy(
    client, db, empresa, usuario_admin
):
    # Es el caso de la toma del 26-10, cerrada antes de que la foto guardara
    # estas columnas: el detalle quedó sin el dato y el artículo sí lo tiene.
    item = _item(db, empresa, "MAQUINA", activo_fijo=True, bodega="BODEGA CENTRAL")
    toma = TomaInventario(empresa_id=empresa.id, cerrado_por_id=usuario_admin.id,
                          total_articulos=1, articulos_contados=1)
    db.session.add(toma)
    db.session.flush()
    db.session.add(TomaInventarioDetalle(
        toma_id=toma.id, codigo=item.codigo, nombre=item.nombre,
        cantidad_qms=5, cantidad_defontana=5, cantidad_fisica=3,
        bodega=None, activo_fijo=None,
    ))
    db.session.commit()
    login(client, "admin@test.cl")

    fila = _fila_de(_hoja(client, toma.id), "MAQUINA")

    assert fila["Activo fijo"] == "Sí"
    assert fila["Bodega"] == "BODEGA CENTRAL"


def test_lo_guardado_en_la_toma_manda_sobre_lo_de_hoy(client, db, empresa, usuario_admin):
    # Si después de cerrar la toma el artículo se desmarca, el informe de esa
    # toma tiene que seguir diciendo lo que era cuando se contó.
    item = _item(db, empresa, "MAQUINA", activo_fijo=True, bodega="BODEGA CENTRAL")
    login(client, "admin@test.cl")
    _cerrar(client)
    toma = TomaInventario.query.first()
    item.activo_fijo = False
    item.bodega = "OTRA BODEGA"
    db.session.commit()

    fila = _fila_de(_hoja(client, toma.id), "MAQUINA")

    assert fila["Activo fijo"] == "Sí"
    assert fila["Bodega"] == "BODEGA CENTRAL"


def test_un_articulo_que_ya_no_existe_no_rompe_el_informe(client, db, empresa, usuario_admin):
    # El detalle de una toma vieja puede nombrar un código que ya no está en el
    # cruce vivo: ahí no hay con qué completar, y la columna queda vacía.
    toma = TomaInventario(empresa_id=empresa.id, cerrado_por_id=usuario_admin.id,
                          total_articulos=1, articulos_contados=0)
    db.session.add(toma)
    db.session.flush()
    db.session.add(TomaInventarioDetalle(
        toma_id=toma.id, codigo="BORRADO", nombre="Ya no está",
        cantidad_qms=0, cantidad_defontana=0, cantidad_fisica=None,
        bodega=None, activo_fijo=None,
    ))
    db.session.commit()
    login(client, "admin@test.cl")

    fila = _fila_de(_hoja(client, toma.id), "BORRADO")

    assert fila["Activo fijo"] in (None, "")
    assert fila["Bodega"] in (None, "")
