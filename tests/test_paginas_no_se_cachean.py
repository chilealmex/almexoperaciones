"""Las páginas no se guardan en el navegador.

Salían sin ninguna directiva de caché: ni Cache-Control, ni Expires, ni ETag.
Sin nada que diga lo contrario, el navegador —o un proxy de la empresa— puede
reusar una copia vieja sin preguntarle al servidor. Dos consecuencias:

- una importación recién hecha no se ve, y cada quien mira la página que le
  quedó guardada;
- después de cerrar sesión, el botón "atrás" muestra las pantallas del que
  estaba antes. En un computador compartido en bodega, eso es el inventario de
  la empresa a la vista de cualquiera.

Los archivos estáticos son otra cosa y se quedan como están: salen con
"no-cache" y su ETag, así que el navegador los revalida contra el servidor y se
ahorra bajarlos de nuevo.
"""

from tests.conftest import login


def test_una_pantalla_no_se_guarda_en_el_navegador(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    respuesta = client.get("/inventario/stock")

    assert respuesta.headers["Cache-Control"] == "no-store"


def test_tampoco_la_de_entrar(client, db, empresa):
    """Es la que queda en el historial al cerrar sesión."""
    respuesta = client.get("/login")

    assert "no-store" in respuesta.headers["Cache-Control"]


def test_los_archivos_estaticos_siguen_revalidando(client, db, empresa):
    """Con "no-store" habría que bajar el CSS y el JavaScript en cada página.
    Con "no-cache" el navegador pregunta si cambiaron y casi siempre se ahorra
    la descarga."""
    for archivo in ("/static/css/custom.css", "/static/js/main.js"):
        respuesta = client.get(archivo)
        assert respuesta.headers["Cache-Control"] == "no-cache", archivo
        assert respuesta.headers.get("ETag"), archivo


def test_una_descarga_que_ya_lo_pedia_no_se_pisa(client, db, empresa, usuario_admin):
    """Hay rutas que ya ponían su propia directiva. La de acá no las reemplaza:
    puesta con setdefault, la que mande es la de la ruta."""
    login(client, "admin@test.cl")

    respuesta = client.get("/inventario/stock.xlsx")

    assert "no-store" in respuesta.headers["Cache-Control"]


def test_las_respuestas_de_datos_tampoco(client, db, empresa, usuario_admin):
    """Las que contestan al escribir el conteo en la fila. Una respuesta vieja
    reusada mostraría una cantidad que no es la que quedó guardada."""
    from app.models.conteo_inventario import ItemConteoInventario

    item = ItemConteoInventario(empresa_id=empresa.id, codigo="COD-001", nombre="X",
                                cantidad_qms=10, cantidad_defontana=10)
    db.session.add(item)
    db.session.commit()
    login(client, "admin@test.cl")

    respuesta = client.post(f"/inventario/stock/{item.id}/conteo", json={"cantidad": "5"})

    assert respuesta.headers["Cache-Control"] == "no-store"
