"""La aplicación no debe caerse: cualquier error termina en una página controlada."""

import pytest

from app import create_app
from app.extensions import db as _db
from tests.conftest import login


@pytest.fixture()
def app_produccion():
    """App de prueba que NO propaga excepciones, igual que en producción."""
    app = create_app("testing")
    app.config["PROPAGAR_ERRORES"] = False

    @app.route("/_explota")
    def _explota():
        raise RuntimeError("fallo simulado")

    @app.route("/_explota_bd")
    def _explota_bd():
        _db.session.execute(_db.text("SELECT 1"))
        raise ValueError("fallo después de tocar la base de datos")

    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


def test_una_excepcion_no_controlada_devuelve_la_pagina_500(app_produccion):
    respuesta = app_produccion.test_client().get("/_explota")
    assert respuesta.status_code == 500
    assert "error inesperado" in respuesta.get_data(as_text=True)


def test_la_sesion_de_base_de_datos_queda_limpia_tras_un_error(app_produccion):
    cliente = app_produccion.test_client()
    assert cliente.get("/_explota_bd").status_code == 500
    # La petición siguiente debe funcionar con normalidad
    assert cliente.get("/healthz").status_code == 200


def test_una_peticion_json_recibe_json_y_no_html(app_produccion):
    respuesta = app_produccion.test_client().get("/_explota", headers={"Accept": "application/json"})
    assert respuesta.status_code == 500
    assert respuesta.is_json
    assert respuesta.get_json()["ok"] is False


def test_pagina_inexistente_devuelve_404_con_plantilla(client):
    respuesta = client.get("/ruta-que-no-existe")
    assert respuesta.status_code == 404
    assert "404" in respuesta.get_data(as_text=True)


def test_metodo_no_permitido_no_rompe(client, usuario_admin):
    login(client, "admin@test.cl")
    respuesta = client.post("/inventario/stock")
    assert respuesta.status_code == 405
    assert "<h1" in respuesta.get_data(as_text=True)


def test_pagina_de_ajuste_con_parametros_invalidos_no_falla(client, usuario_admin):
    login(client, "admin@test.cl")
    respuesta = client.get("/inventario/ajuste?orden=columna_inventada&dir=raro&pagina=-5&filtro=xxx")
    assert respuesta.status_code == 200
