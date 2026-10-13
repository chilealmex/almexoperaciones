"""Juntar dos líneas del maestro que son el mismo artículo.

Era el caso sin salida. "Unificar códigos" cubre dos situaciones:

- el mismo código escrito distinto ("011-CON-OTH-01" y "11-CON-OTH-01"), que se
  agrupa solo porque los códigos se parecen;
- un código suelto en QMS y otro suelto en Defontana, que se cruzan.

Faltaba la tercera: dos códigos que no se parecen en nada y que están los dos en
los dos sistemas. Es el mismo artículo cargado dos veces en cada sistema. No lo
proponía ninguna lista, y "Unir a mano" lo rechazaba diciendo que no había nada
que unir, que es cierto para el cruce entre sistemas y falso para lo que se
estaba preguntando.

El caso real con el que apareció: dos etiquetas de catalizador,
A2000ETQ-CATNOINFLAMABL con 310 en cada sistema y SA2000ETQ-CAT-NO_INFLAMABLE
con 346 en cada uno y 496 contados.
"""

from app.models.codigo_unificado import CodigoUnificado
from app.models.conteo_inventario import ItemConteoInventario
from app.models.equivalencia_codigo import EquivalenciaCodigo
from app.utils.cantidades import a_cantidad
from tests.conftest import login

A = "A2000ETQ-CATNOINFLAMABL"
B = "SA2000ETQ-CAT-NO_INFLAMABLE"


def _item(db, empresa, codigo, **kw):
    datos = dict(empresa_id=empresa.id, codigo=codigo, nombre="PRODUCTO " + codigo,
                 cantidad_qms=0, cantidad_defontana=0, en_qms=True, en_defontana=True)
    datos.update(kw)
    item = ItemConteoInventario(**datos)
    db.session.add(item)
    db.session.commit()
    return item


def _etiquetas(db, empresa):
    """Las dos filas tal como se ven en Stock y conteo: las dos en los DOS sistemas."""
    _item(db, empresa, A, nombre="ETIQUETA PARA CATALIZADOR SA2000NO INFLAMABLE",
          cantidad_qms=310, cantidad_defontana=310)
    _item(db, empresa, B, nombre="ETIQUETA PARA CATALIZADOR SA2000_NO INFLAMABLE",
          cantidad_qms=346, cantidad_defontana=346, cantidad_fisica=a_cantidad(496))


def _unir(client, uno, otro):
    return client.post("/inventario/equivalencias/unir",
                       data={"codigo_qms": uno, "codigo_defontana": otro},
                       follow_redirects=True)


def test_dos_lineas_del_maestro_quedan_en_una(db, empresa, usuario_admin, client):
    _etiquetas(db, empresa)
    login(client, "admin@test.cl")

    _unir(client, B, A)

    quedo = ItemConteoInventario.query.one()
    # Cada línea era stock declarado por separado, así que se suman.
    assert quedo.cantidad_qms == 656
    assert quedo.cantidad_defontana == 656


def test_el_conteo_fisico_no_se_pierde(db, empresa, usuario_admin, client):
    """Es trabajo de bodega: perderlo al unir obligaría a volver a contar."""
    _etiquetas(db, empresa)
    login(client, "admin@test.cl")

    _unir(client, B, A)

    assert ItemConteoInventario.query.one().cantidad_fisica == a_cantidad(496)


def test_la_union_sobrevive_a_la_proxima_importacion(db, empresa, usuario_admin, client):
    """Sin esto la unión duraba hasta la próxima carga: la planilla sigue
    trayendo el código retirado —quien exporta no cambió nada— y el duplicado
    volvía a aparecer solo."""
    _etiquetas(db, empresa)
    login(client, "admin@test.cl")

    _unir(client, B, A)

    quedo = ItemConteoInventario.query.one()
    unificado = CodigoUnificado.query.one()
    assert unificado.codigo_retirado != quedo.codigo
    assert unificado.codigo_vigente == quedo.codigo


def test_lo_dice_con_los_numeros_que_quedaron(db, empresa, usuario_admin, client):
    """Unir suma stock y borra una fila: hay que poder comprobar el resultado
    sin ir a buscarlo.

    Se comprueba la frase entera, con los dos códigos adentro, y no sólo "una
    sola línea": ese trozo también está en el texto fijo de la pantalla, así que
    por sí solo daría por buena una pantalla que no avisa nada.
    """
    _etiquetas(db, empresa)
    login(client, "admin@test.cl")

    html = _unir(client, B, A).get_data(as_text=True)

    assert f"{A} y {B} quedaron en una sola línea" in html
    assert "656 en QMS y 656 en Defontana" in html
    assert "se deshace" in html


def test_no_se_crea_una_equivalencia_entre_sistemas(db, empresa, usuario_admin, client):
    """Son dos mecanismos distintos. Una equivalencia dice "este código de
    Defontana es aquel de QMS", y acá los dos códigos están en los dos
    sistemas: no hay nada que traducir, hay una línea de más."""
    _etiquetas(db, empresa)
    login(client, "admin@test.cl")

    _unir(client, B, A)

    assert EquivalenciaCodigo.query.count() == 0


def test_una_pareja_entre_sistemas_sigue_cruzandose(db, empresa, usuario_admin, client):
    """El caso de siempre no cambia: cada código en un sistema distinto queda
    cruzado, con los dos códigos vivos, no fundido en una línea."""
    _item(db, empresa, "GOL.PRE-5_8", cantidad_qms=5, en_qms=True, en_defontana=False)
    _item(db, empresa, "GOLPRE-58", cantidad_defontana=7, en_qms=False, en_defontana=True)
    login(client, "admin@test.cl")

    _unir(client, "GOL.PRE-5_8", "GOLPRE-58")

    equivalencia = EquivalenciaCodigo.query.one()
    assert equivalencia.codigo_qms == "GOL.PRE-5_8"
    assert equivalencia.codigo_defontana == "GOLPRE-58"
    # Y no se registró como código retirado: los dos siguen existiendo.
    assert CodigoUnificado.query.count() == 0


def test_un_codigo_que_no_existe_sigue_avisando(db, empresa, usuario_admin, client):
    """Los códigos se escriben a mano. Un dedazo no puede terminar uniendo nada,
    y el aviso tiene que decir cuál de los dos está mal."""
    _etiquetas(db, empresa)
    login(client, "admin@test.cl")

    html = _unir(client, B, "NO-EXISTE").get_data(as_text=True)

    assert "No existe ningún artículo" in html
    assert ItemConteoInventario.query.count() == 2


def test_un_codigo_en_la_casilla_equivocada_avisa_y_no_une(db, empresa, usuario_admin, client):
    """Cambiarse de casilla es el error más fácil de cometer acá. Las dos líneas
    existen, así que sin esto se fundirían en una sumando el stock por un dedazo,
    en vez de avisar.
    """
    _item(db, empresa, "SOLO-DEFO", cantidad_defontana=9, en_qms=False, en_defontana=True)
    _item(db, empresa, "OTRO-DEFO", cantidad_defontana=4, en_qms=False, en_defontana=True)
    login(client, "admin@test.cl")

    html = _unir(client, "SOLO-DEFO", "OTRO-DEFO").get_data(as_text=True)

    assert "no existe en QMS" in html
    assert "sólo en Defontana" in html
    assert ItemConteoInventario.query.count() == 2
    assert CodigoUnificado.query.count() == 0


def test_tampoco_une_si_a_uno_le_falta_un_sistema(db, empresa, usuario_admin, client):
    """Uno en los dos sistemas y el otro en uno solo no es "la misma línea
    duplicada": es una pareja entre sistemas a medio escribir. Se avisa, no se
    funden las líneas sumando stock.
    """
    _etiquetas(db, empresa)
    _item(db, empresa, "SOLO-QMS", cantidad_qms=3, en_qms=True, en_defontana=False)
    login(client, "admin@test.cl")

    html = _unir(client, "SOLO-QMS", B).get_data(as_text=True)

    assert "ya existe en los dos sistemas" in html
    assert ItemConteoInventario.query.count() == 3
    assert CodigoUnificado.query.count() == 0


def test_el_mismo_codigo_dos_veces_no_une_nada(db, empresa, usuario_admin, client):
    """Un artículo consigo mismo no es una pareja: unirlo borraría la línea."""
    _etiquetas(db, empresa)
    login(client, "admin@test.cl")

    _unir(client, A, A)

    assert ItemConteoInventario.query.count() == 2
    assert CodigoUnificado.query.count() == 0


def test_la_caja_de_unir_a_mano_se_ve_sin_codigos_sueltos(db, empresa, usuario_admin, client):
    """Antes sólo aparecía si había sueltos en los dos sistemas. Juntar dos
    líneas del maestro es posible aunque no quede ni un suelto, y sin la caja no
    había dónde pedirlo."""
    _etiquetas(db, empresa)  # las dos están en los dos sistemas: ningún suelto
    login(client, "admin@test.cl")

    html = client.get("/inventario/equivalencias").get_data(as_text=True)

    assert "Unir a mano" in html


# --- Las dos columnas de código en Stock y conteo ---
#
# La línea del maestro es una sola, pero los dos sistemas pueden llamarla
# distinto: es justo lo que se confirma en "Unificar códigos". Hasta ahora eso
# sólo se veía en esa pantalla, así que mirando Stock y conteo no había forma de
# saber qué código buscar en Defontana para ir a revisar allá.
#
# Las columnas salen del registro de parejas confirmadas y no de una copia
# aparte: así dicen lo mismo que la pantalla donde se confirmaron.


def _pareja(db, empresa, codigo_qms, codigo_defo):
    from app.models.equivalencia_codigo import crear_equivalencia

    crear_equivalencia(empresa.id, codigo_qms, codigo_defo, None)
    db.session.commit()


def test_se_ve_el_codigo_de_cada_sistema(db, empresa, usuario_admin, client):
    _item(db, empresa, "0136-1005", cantidad_qms=5, cantidad_defontana=5)
    _pareja(db, empresa, "0136-1005", "A2000ETQ-CATNOINFLAMABL")
    login(client, "admin@test.cl")

    html = client.get("/inventario/stock?filtro=todos").get_data(as_text=True)

    assert "Código QMS" in html
    assert "Código Defontana" in html
    # Dentro de la tabla, y no en cualquier parte de la página: el mismo código
    # sale también en la tarjeta de pantalla angosta, así que buscarlo suelto
    # daría por buena una tabla que muestra otra cosa.
    tabla = html[html.index('id="tabla-stock"'):html.index("</table>")]
    assert "A2000ETQ-CATNOINFLAMABL" in tabla
    assert "0136-1005" in tabla


def test_si_los_dos_sistemas_usan_el_mismo_codigo_sale_en_las_dos(db, empresa, usuario_admin, client):
    """Sin pareja confirmada no hay nada que traducir: el código es uno solo."""
    from app.inventario.routes import codigos_por_sistema

    item = _item(db, empresa, "COD-001", cantidad_qms=5, cantidad_defontana=5)

    assert codigos_por_sistema([item], empresa.id)[item.id] == ("COD-001", "COD-001")


def test_la_columna_del_sistema_que_no_lo_tiene_queda_vacia(db, empresa, usuario_admin):
    """Repetir el código ahí haría creer que el artículo está en ese sistema."""
    from app.inventario.routes import codigos_por_sistema

    solo_qms = _item(db, empresa, "SOLO-QMS", cantidad_qms=5, en_defontana=False)
    solo_defo = _item(db, empresa, "SOLO-DEFO", cantidad_defontana=5, en_qms=False)

    codigos = codigos_por_sistema([solo_qms, solo_defo], empresa.id)
    assert codigos[solo_qms.id] == ("SOLO-QMS", "")
    assert codigos[solo_defo.id] == ("", "SOLO-DEFO")


def test_se_muestran_todos_los_codigos_de_defontana_del_articulo(db, empresa, usuario_admin):
    """Un mismo artículo de QMS puede tener varias parejas de Defontana.
    Esconder las demás haría buscar un código que sí existe."""
    from app.inventario.routes import codigos_por_sistema

    item = _item(db, empresa, "0136-1005", cantidad_qms=5, cantidad_defontana=5)
    _pareja(db, empresa, "0136-1005", "DEFO-A")
    _pareja(db, empresa, "0136-1005", "DEFO-B")

    assert codigos_por_sistema([item], empresa.id)[item.id][1] == "DEFO-A, DEFO-B"


def test_buscar_por_el_codigo_de_defontana_lo_encuentra(db, empresa, usuario_admin, client):
    """Ahora que esa columna se ve, buscar lo que se está mirando tiene que
    encontrarlo: la línea lleva el código de QMS, así que sin esto la pantalla
    contesta "no hay resultados" por un artículo que está ahí."""
    _item(db, empresa, "0136-1005", nombre="ETIQUETA", cantidad_qms=5, cantidad_defontana=5)
    _item(db, empresa, "OTRO-COD", nombre="OTRA COSA", cantidad_qms=1, cantidad_defontana=1)
    _pareja(db, empresa, "0136-1005", "A2000ETQ-CATNOINFLAMABL")
    login(client, "admin@test.cl")

    html = client.get("/inventario/stock?q=A2000ETQ").get_data(as_text=True)

    assert "0136-1005" in html
    assert "OTRO-COD" not in html


def test_el_excel_trae_las_dos_columnas(db, empresa, usuario_admin, client):
    """El archivo descargado tiene que ser lo que se está viendo."""
    import io

    import openpyxl

    _item(db, empresa, "0136-1005", cantidad_qms=5, cantidad_defontana=5)
    _pareja(db, empresa, "0136-1005", "A2000ETQ-CATNOINFLAMABL")
    login(client, "admin@test.cl")

    datos = client.get("/inventario/stock.xlsx").data
    hoja = openpyxl.load_workbook(io.BytesIO(datos)).active
    textos = [str(c.value) for fila in hoja.iter_rows() for c in fila]

    assert "Código QMS" in textos
    assert "Código Defontana" in textos
    assert "A2000ETQ-CATNOINFLAMABL" in textos


def test_queda_la_linea_que_tiene_el_conteo(db, empresa, usuario_admin, client):
    """Entre dos líneas vivas manda la contada: es la que bodega ya trabajó, y
    es el código con el que se registró ese trabajo."""
    _etiquetas(db, empresa)
    login(client, "admin@test.cl")

    _unir(client, A, B)  # escritos al revés: el orden no decide

    assert ItemConteoInventario.query.one().codigo == B
