import io
import json
import re

from app.models.conteo_inventario import ItemConteoInventario
from tests.conftest import login


def _item(db, empresa, codigo, qms, defontana, fisica=None):
    item = ItemConteoInventario(
        empresa_id=empresa.id,
        codigo=codigo,
        nombre=f"Artículo {codigo}",
        cantidad_qms=qms,
        cantidad_defontana=defontana,
        cantidad_fisica=fisica,
    )
    db.session.add(item)
    db.session.commit()
    return item


def test_stock_muestra_cantidades_y_diferencias(client, db, empresa, usuario_admin):
    _item(db, empresa, "COD-A", 10, 4)
    login(client, "admin@test.cl")

    body = client.get("/inventario/stock").get_data(as_text=True)
    assert "COD-A" in body
    assert "+6" in body  # diferencia entre sistemas visible en la misma fila


def test_filtro_diferencias_coincide_con_el_modelo(client, db, empresa, usuario_admin):
    _item(db, empresa, "IGUALES", 5, 5)  # sin diferencia
    _item(db, empresa, "DESCUADRE", 9, 2)  # sistemas no cuadran
    _item(db, empresa, "FISICO-DISTINTO", 3, 3, fisica=8)  # físico no coincide
    _item(db, empresa, "TODO-OK", 4, 4, fisica=4)  # los tres cuadran
    login(client, "admin@test.cl")

    body = client.get("/inventario/stock?filtro=diferencias").get_data(as_text=True)
    assert "DESCUADRE" in body
    assert "FISICO-DISTINTO" in body
    assert "IGUALES" not in body
    assert "TODO-OK" not in body

    esperados = {i.codigo for i in ItemConteoInventario.query.all() if i.tiene_diferencia}
    assert esperados == {"DESCUADRE", "FISICO-DISTINTO"}


def test_filtros_sin_contar_y_contados(client, db, empresa, usuario_admin):
    _item(db, empresa, "PENDIENTE", 5, 5)
    _item(db, empresa, "YA-CONTADO", 5, 5, fisica=5)
    login(client, "admin@test.cl")

    sin_contar = client.get("/inventario/stock?filtro=sin_contar").get_data(as_text=True)
    assert "PENDIENTE" in sin_contar and "YA-CONTADO" not in sin_contar

    contados = client.get("/inventario/stock?filtro=contados").get_data(as_text=True)
    assert "YA-CONTADO" in contados and "PENDIENTE" not in contados


def test_buscar_por_codigo(client, db, empresa, usuario_admin):
    _item(db, empresa, "TORNILLO-1", 1, 1)
    _item(db, empresa, "TUERCA-9", 2, 2)
    login(client, "admin@test.cl")

    body = client.get("/inventario/stock?q=tornillo").get_data(as_text=True)
    assert "TORNILLO-1" in body and "TUERCA-9" not in body


# --- Esconder los artículos que están en cero en los dos sistemas ---
#
# El maestro trae miles de artículos y la mayoría no tiene existencias en
# ninguno de los dos sistemas: no hay nada que contar en ellos y empujan fuera
# de la pantalla a los que sí importan. Es una decisión aparte de los filtros
# de arriba y se combina con todos ellos.


def _pantalla(client, consulta=""):
    return client.get(f"/inventario/stock{consulta}").get_data(as_text=True)


def _codigos(client, consulta=""):
    """Los códigos que la tabla está mostrando de verdad.

    Buscar "EN-CERO" deja ese texto escrito en dos lugares más —el cuadro de
    búsqueda y el aviso "Sin resultados para ..."— así que mirar la página
    entera, o incluso sólo el cuerpo de la tabla, daba por encontrado un
    artículo que no se estaba mostrando.
    """
    return set(re.findall(
        r'<td class="text-nowrap fw-semibold">([^<]*)</td>', _pantalla(client, consulta)
    ))


def test_al_entrar_no_se_ven_los_que_estan_en_cero_en_los_dos_sistemas(
    client, db, empresa, usuario_admin
):
    _item(db, empresa, "SOLO-QMS", 7, 0)
    _item(db, empresa, "SOLO-DEFO", 0, 3)
    _item(db, empresa, "EN-AMBOS", 5, 5)
    _item(db, empresa, "EN-CERO", 0, 0)
    login(client, "admin@test.cl")

    assert _codigos(client) == {"SOLO-QMS", "SOLO-DEFO", "EN-AMBOS"}


def test_se_sigue_entrando_por_lo_que_falta_contar(client, db, empresa, usuario_admin):
    """Esconder lo vacío no reemplaza al filtro de entrada, se suma a él.

    Durante una toma lo que se quiere ver es lo que falta por contar *y* tiene
    existencias; con un solo filtro eso no se puede pedir.
    """
    _item(db, empresa, "FALTA-Y-TIENE", 5, 5)
    _item(db, empresa, "YA-CONTADO-CON-STOCK", 5, 5, fisica=5)
    _item(db, empresa, "FALTA-PERO-VACIO", 0, 0)
    login(client, "admin@test.cl")

    assert _codigos(client) == {"FALTA-Y-TIENE"}


def test_se_combina_con_cualquier_filtro(client, db, empresa, usuario_admin):
    _item(db, empresa, "CONTADO-CON-STOCK", 4, 4, fisica=4)
    _item(db, empresa, "SIN-CONTAR-CON-STOCK", 4, 4)
    login(client, "admin@test.cl")

    assert _codigos(client, "?filtro=contados") == {"CONTADO-CON-STOCK"}


def test_lo_ya_contado_no_se_esconde_aunque_los_sistemas_lo_den_en_cero(
    client, db, empresa, usuario_admin
):
    """Es justamente un hallazgo: no está en ningún sistema y apareció en bodega.

    Esconderlo sería esconder trabajo ya hecho y una diferencia real.
    """
    _item(db, empresa, "APARECIDO", 0, 0, fisica=4)
    _item(db, empresa, "CONTADO-EN-CERO", 0, 0, fisica=0)
    login(client, "admin@test.cl")

    assert _codigos(client, "?filtro=todos") == {"APARECIDO", "CONTADO-EN-CERO"}


def test_un_stock_negativo_no_es_un_articulo_vacio(client, db, empresa, usuario_admin):
    """Es un error que hay que ver, no algo que esconder."""
    _item(db, empresa, "NEGATIVO", -2, 0)
    login(client, "admin@test.cl")

    assert "NEGATIVO" in _codigos(client)


def test_se_pueden_mostrar_los_vacios_cuando_se_quiere(client, db, empresa, usuario_admin):
    _item(db, empresa, "EN-CERO", 0, 0)
    login(client, "admin@test.cl")

    assert "EN-CERO" in _codigos(client, "?vacios=si")


def test_la_busqueda_encuentra_un_articulo_en_cero(client, db, empresa, usuario_admin):
    """Si no, la pantalla diría "no hay resultados" por un artículo que existe,
    sólo porque venía escondido; y buscarlo es justo lo que se hace cuando no
    aparece en la lista."""
    _item(db, empresa, "EN-CERO", 0, 0)
    login(client, "admin@test.cl")

    assert _codigos(client, "?q=EN-CERO") == {"EN-CERO"}


def test_buscar_puede_seguir_escondiendo_los_vacios_si_se_pide(
    client, db, empresa, usuario_admin
):
    _item(db, empresa, "TORNILLO-VACIO", 0, 0)
    _item(db, empresa, "TORNILLO-CON-STOCK", 3, 3)
    login(client, "admin@test.cl")

    assert _codigos(client, "?q=tornillo&vacios=no") == {"TORNILLO-CON-STOCK"}


def test_se_avisa_cuantos_articulos_quedaron_ocultos(client, db, empresa, usuario_admin):
    """Sin el aviso, "no encuentro el artículo" se lee como un dato perdido."""
    _item(db, empresa, "CON-STOCK", 1, 1)
    for n in range(3):
        _item(db, empresa, f"VACIO-{n}", 0, 0)
    login(client, "admin@test.cl")

    body = _pantalla(client)

    assert "Se están ocultando" in body
    assert "<strong>3</strong>" in body
    assert "Mostrarlos" in body


def test_sin_articulos_en_cero_no_se_avisa_nada(client, db, empresa, usuario_admin):
    _item(db, empresa, "CON-STOCK", 1, 1)
    login(client, "admin@test.cl")

    assert "Se están ocultando" not in _pantalla(client)


def test_si_el_excel_recorta_lo_dice_en_el_encabezado(client, db, empresa, usuario_admin):
    """Un informe que dejó fuera parte del maestro no puede leerse como el total."""
    _item(db, empresa, "EN-CERO", 0, 0)
    _item(db, empresa, "CON-STOCK", 1, 1)
    login(client, "admin@test.cl")

    from openpyxl import load_workbook

    respuesta = client.get("/inventario/stock.xlsx?vacios=no")
    hoja = load_workbook(io.BytesIO(respuesta.data)).active
    texto = " ".join(
        str(c.value) for fila in hoja.iter_rows(max_row=6) for c in fila if c.value
    )

    assert "artículos en cero" in texto


def test_el_excel_baja_tambien_los_vacios(client, db, empresa, usuario_admin):
    """La pantalla recorta para poder trabajar; el archivo descargado se
    entiende como el registro completo y no puede recortar en silencio."""
    _item(db, empresa, "EN-CERO", 0, 0)
    _item(db, empresa, "CON-STOCK", 1, 1)
    login(client, "admin@test.cl")

    from openpyxl import load_workbook

    respuesta = client.get("/inventario/stock.xlsx")
    hoja = load_workbook(io.BytesIO(respuesta.data)).active
    codigos = {fila[0] for fila in hoja.iter_rows(values_only=True) if fila[0]}

    assert "EN-CERO" in codigos
    assert "CON-STOCK" in codigos


def test_contar_en_la_misma_fila_guarda_y_devuelve_diferencias(client, db, empresa, usuario_admin):
    item = _item(db, empresa, "COD-B", 10, 8)
    login(client, "admin@test.cl")

    r = client.post(
        f"/inventario/stock/{item.id}/contar",
        data=json.dumps({"cantidad": "9"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    datos = r.get_json()
    assert datos["ok"] is True
    assert datos["dif_qms"] == -1
    assert datos["dif_defontana"] == 1

    db.session.refresh(item)
    assert item.cantidad_fisica == 9
    assert item.contado_por_id == usuario_admin.id
    assert item.contado_en is not None


def test_vaciar_el_campo_borra_el_conteo(client, db, empresa, usuario_admin):
    item = _item(db, empresa, "COD-C", 5, 5, fisica=3)
    login(client, "admin@test.cl")

    r = client.post(
        f"/inventario/stock/{item.id}/contar",
        data=json.dumps({"cantidad": ""}),
        content_type="application/json",
    )
    assert r.status_code == 200

    db.session.refresh(item)
    assert item.cantidad_fisica is None
    assert not item.contado


def test_cantidad_invalida_es_rechazada(client, db, empresa, usuario_admin):
    item = _item(db, empresa, "COD-D", 5, 5)
    login(client, "admin@test.cl")

    for valor in ["abc", "-3"]:
        r = client.post(
            f"/inventario/stock/{item.id}/contar",
            data=json.dumps({"cantidad": valor}),
            content_type="application/json",
        )
        assert r.status_code == 400
        assert r.get_json()["ok"] is False

    db.session.refresh(item)
    assert item.cantidad_fisica is None


def test_usuario_sin_permiso_editar_no_puede_contar(client, db, empresa, usuario_bodega):
    item = _item(db, empresa, "COD-E", 5, 5)
    login(client, "bodega@test.cl")

    r = client.post(
        f"/inventario/stock/{item.id}/contar",
        data=json.dumps({"cantidad": "4"}),
        content_type="application/json",
    )
    assert r.status_code == 403

    db.session.refresh(item)
    assert item.cantidad_fisica is None


# --- Al entrar se muestra lo que falta por contar ---

def _dos_articulos(empresa, db):
    db.session.add_all([
        ItemConteoInventario(empresa_id=empresa.id, codigo="POR-CONTAR", nombre="Pendiente",
                             cantidad_qms=5, cantidad_defontana=5),
        ItemConteoInventario(empresa_id=empresa.id, codigo="YA-CONTADO", nombre="Listo",
                             cantidad_qms=5, cantidad_defontana=5, cantidad_fisica=5),
    ])
    db.session.commit()


def test_al_entrar_se_ven_solo_los_que_faltan_por_contar(client, usuario_admin, empresa, db):
    """Durante la toma, lo ya contado sólo estorba: había que filtrar en cada recarga."""
    _dos_articulos(empresa, db)
    login(client, "admin@test.cl")

    texto = client.get("/inventario/stock").get_data(as_text=True)
    assert "POR-CONTAR" in texto
    assert "YA-CONTADO" not in texto


def test_se_pueden_ver_todos_a_proposito(client, usuario_admin, empresa, db):
    _dos_articulos(empresa, db)
    login(client, "admin@test.cl")

    texto = client.get("/inventario/stock?filtro=todos").get_data(as_text=True)
    assert "POR-CONTAR" in texto
    assert "YA-CONTADO" in texto


def test_el_filtro_de_contados_sigue_funcionando(client, usuario_admin, empresa, db):
    _dos_articulos(empresa, db)
    login(client, "admin@test.cl")

    texto = client.get("/inventario/stock?filtro=contados").get_data(as_text=True)
    assert "YA-CONTADO" in texto
    assert "POR-CONTAR" not in texto


def test_un_filtro_inventado_cae_en_lo_pendiente_y_no_revienta(client, usuario_admin, empresa, db):
    _dos_articulos(empresa, db)
    login(client, "admin@test.cl")

    respuesta = client.get("/inventario/stock?filtro=cualquier-cosa")
    assert respuesta.status_code == 200
    assert "POR-CONTAR" in respuesta.get_data(as_text=True)


def test_la_tabla_deja_las_filas_todas_del_mismo_alto(client, usuario_admin, empresa, db):
    """Nombre, ubicación y línea en una sola línea; el texto completo va en title."""
    db.session.add(ItemConteoInventario(
        empresa_id=empresa.id, codigo="LARGO-01",
        nombre="TUERCAS DE ANCLAJE DE ACERO INOXIDABLE 3/8 CON ARANDELA",
        cantidad_qms=1, cantidad_defontana=1,
        ubicacion="RACK PRINCIPAL PASILLO 3 NIVEL 2", linea_negocio="REPUESTOS INDUSTRIALES"))
    db.session.commit()

    login(client, "admin@test.cl")
    texto = client.get("/inventario/stock").get_data(as_text=True)

    assert "tabla-stock" in texto
    assert 'title="TUERCAS DE ANCLAJE DE ACERO INOXIDABLE 3/8 CON ARANDELA"' in texto
    assert "celda-ubicacion" in texto and "celda-linea" in texto


def test_el_excel_descarga_todo_aunque_la_pantalla_muestre_solo_lo_pendiente(client, usuario_admin, empresa, db):
    """Un archivo descargado se entiende como el registro completo.

    La pantalla parte mostrando lo que falta por contar, pero entregar un Excel
    recortado sin avisar se presta a confusión: quien lo abre cree que ese es
    todo el inventario.
    """
    from openpyxl import load_workbook
    import io

    _dos_articulos(empresa, db)
    login(client, "admin@test.cl")

    hoja = load_workbook(io.BytesIO(client.get("/inventario/stock.xlsx").data)).active
    codigos = {fila[0] for fila in hoja.iter_rows(min_row=2, values_only=True) if fila and fila[0]}
    assert {"POR-CONTAR", "YA-CONTADO"} <= codigos


def test_si_se_elige_un_filtro_el_excel_lo_respeta(client, usuario_admin, empresa, db):
    from openpyxl import load_workbook
    import io

    _dos_articulos(empresa, db)
    login(client, "admin@test.cl")

    hoja = load_workbook(io.BytesIO(client.get("/inventario/stock.xlsx?filtro=sin_contar").data)).active
    codigos = {fila[0] for fila in hoja.iter_rows(min_row=2, values_only=True) if fila and fila[0]}
    assert "POR-CONTAR" in codigos
    assert "YA-CONTADO" not in codigos


def test_el_boton_de_excel_avisa_que_filtro_va_a_bajar(client, db, empresa, usuario_admin):
    """La descarga trae lo mismo que la pantalla, filtro incluido.

    Con "Sin contar" puesto, el archivo salía sin ningún conteo físico y
    parecía que la descarga estuviera perdiendo los datos. El botón lo dice
    antes de bajarlo.
    """
    from app.models.conteo_inventario import ItemConteoInventario
    from app.utils.cantidades import a_cantidad

    db.session.add(ItemConteoInventario(
        empresa_id=empresa.id, codigo="C-1", nombre="Cable",
        cantidad_qms=a_cantidad("100"), cantidad_defontana=a_cantidad("100"),
        cantidad_fisica=a_cantidad("12,5")))
    db.session.commit()
    login(client, "admin@test.cl")

    sin_filtro = client.get("/inventario/stock").get_data(as_text=True)
    filtrado = client.get("/inventario/stock?filtro=sin_contar").get_data(as_text=True)

    cabecera_sin = sin_filtro[:sin_filtro.index("</div>", sin_filtro.index("⬇ Excel"))]
    cabecera_con = filtrado[:filtrado.index("</div>", filtrado.index("⬇ Excel"))]
    assert "Solo sin contar" not in cabecera_sin, "sin filtro no debe decir nada"
    assert "Solo sin contar" in cabecera_con


def test_lo_contado_con_decimales_llega_entero_al_excel(client, db, empresa, usuario_admin):
    """De punta a punta: se escribe 12,5 en la pantalla y eso sale en el archivo."""
    import io
    from openpyxl import load_workbook
    from app.models.conteo_inventario import ItemConteoInventario
    from app.utils.cantidades import a_cantidad

    item = ItemConteoInventario(
        empresa_id=empresa.id, codigo="MET-1", nombre="Cable por metro",
        cantidad_qms=a_cantidad("100"), cantidad_defontana=a_cantidad("100"))
    db.session.add(item)
    db.session.commit()

    login(client, "admin@test.cl")
    respuesta = client.post(f"/inventario/stock/{item.id}/contar", json={"cantidad": "12,5"})
    assert respuesta.status_code == 200

    hoja = load_workbook(io.BytesIO(
        client.get("/inventario/stock.xlsx").get_data())).active
    valores = [c.value for fila in hoja.iter_rows() for c in fila]
    assert 12.5 in valores, "el conteo con decimales no llegó al archivo"
