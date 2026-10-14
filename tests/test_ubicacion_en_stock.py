"""La ubicación, a la vista, contando.

Estaba en la tabla pero al final y marcada "solo-pantalla-ancha": aparecía
recién sobre 1700px de ventana, y con el menú lateral restando, en la pantalla
donde se cuenta quedaba fuera del borde. Para contar, dónde está guardado el
artículo no es un dato de apoyo: es con lo que bodega camina a buscarlo.
"""

from app.models.conteo_inventario import ItemConteoInventario
from tests.conftest import login

UBICACION = "ESTANTE A3 / NIVEL 2"


def _item(db, empresa, codigo, **kw):
    datos = dict(empresa_id=empresa.id, codigo=codigo, nombre="PRODUCTO " + codigo,
                 cantidad_qms=10, cantidad_defontana=10, en_qms=True, en_defontana=True,
                 ubicacion=UBICACION)
    datos.update(kw)
    item = ItemConteoInventario(**datos)
    db.session.add(item)
    db.session.commit()
    return item


def _tabla(client):
    html = client.get("/inventario/stock?filtro=todos&vacios=si").get_data(as_text=True)
    return html[html.index('id="tabla-stock"'):html.index("</table>")]


def test_la_ubicacion_se_ve_en_la_tabla(db, empresa, usuario_admin, client):
    _item(db, empresa, "COD-001")
    login(client, "admin@test.cl")

    tabla = _tabla(client)

    assert UBICACION in tabla


def test_no_queda_escondida_tras_la_clase_de_pantalla_ancha(db, empresa, usuario_admin, client):
    """Verla en el HTML no basta: con esa clase el navegador la oculta igual, y
    la prueba pasaría sobre una columna que nadie ve."""
    _item(db, empresa, "COD-001")
    login(client, "admin@test.cl")

    tabla = _tabla(client)
    celda = tabla[tabla.index(UBICACION) - 200:tabla.index(UBICACION)]

    assert "solo-pantalla-ancha" not in celda


def test_va_junto_al_nombre_y_no_al_final(db, empresa, usuario_admin, client):
    """Al final hay que desplazar la tabla a lo ancho para leerla, con la mano
    ocupada en el conteo. Pegada al nombre se lee sin moverse."""
    _item(db, empresa, "COD-001")
    login(client, "admin@test.cl")

    tabla = _tabla(client)

    assert tabla.index("Ubicación") < tabla.index("Unidad")
    assert tabla.index("Nombre") < tabla.index("Ubicación")


def test_se_puede_filtrar_por_ubicacion(db, empresa, usuario_admin, client):
    """Contar es recorrer una bodega a la vez: el filtro es lo que arma esa lista."""
    _item(db, empresa, "COD-001", ubicacion="ESTANTE A3")
    _item(db, empresa, "COD-002", ubicacion="PATIO")
    login(client, "admin@test.cl")

    html = client.get(
        "/inventario/stock?filtro=todos&vacios=si&f_ubicacion=ESTANTE"
    ).get_data(as_text=True)

    assert "COD-001" in html
    assert "COD-002" not in html


def test_la_casilla_para_filtrar_esta_bajo_la_columna(db, empresa, usuario_admin, client):
    """Que el filtro funcione por la dirección no basta: se escribe en la casilla
    bajo el título, y sin ella no hay dónde pedirlo."""
    _item(db, empresa, "COD-001")
    login(client, "admin@test.cl")

    assert 'name="f_ubicacion"' in _tabla(client)


def test_linea_de_negocio_sigue_siendo_de_pantalla_ancha(db, empresa, usuario_admin, client):
    """Esa sí es un dato de apoyo. Sacarle la clase de paso dejaría la tabla más
    ancha sin que nadie lo haya pedido."""
    _item(db, empresa, "COD-001", linea_negocio="REPUESTOS")
    login(client, "admin@test.cl")

    tabla = _tabla(client)
    celda = tabla[tabla.index("REPUESTOS") - 200:tabla.index("REPUESTOS")]
    titulo = tabla[tabla.index("Línea de negocio") - 300:tabla.index("Línea de negocio")]

    assert "solo-pantalla-ancha" in celda
    # Y el título también: si se escondiera sólo la celda, la columna quedaría
    # con encabezado y sin contenido, descuadrando la tabla entera.
    assert "solo-pantalla-ancha" in titulo


def test_sin_ubicacion_queda_el_guion(db, empresa, usuario_admin, client):
    """Una celda en blanco se lee como un error de carga.

    Se mira la celda de ubicación y no la tabla entera: el guion sale en varias
    columnas, así que buscarlo suelto pasaría con la celda vacía.
    """
    _item(db, empresa, "COD-001", ubicacion=None)
    login(client, "admin@test.cl")

    tabla = _tabla(client)
    celda = tabla[tabla.index('class="celda-ubicacion"'):]

    assert celda[:celda.index("</td>")].endswith("—")
