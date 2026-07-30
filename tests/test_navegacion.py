from app.utils.navegacion import construir_navegacion
from tests.conftest import login


def _puede_todo(_modulo, _accion="ver", submodulo=None):
    return True


def _puede_nada(_modulo, _accion="ver", submodulo=None):
    return False


def test_modulos_se_filtran_por_permiso():
    nav = construir_navegacion("core.dashboard", _puede_nada)
    claves = [m["clave"] for m in nav["modulos"]]
    assert claves == ["inicio"]  # Inicio no exige permiso, el resto sí


def test_submodulos_del_modulo_activo_se_marcan():
    nav = construir_navegacion("inventario.stock", _puede_todo)

    activos = [m["clave"] for m in nav["modulos"] if m["activo"]]
    assert activos == ["inventario"]

    submodulos = {s["clave"]: s["activo"] for s in nav["submodulos"]}
    assert submodulos["stock"] is True
    assert submodulos["resumen"] is False
    assert "ajuste" in submodulos


def test_endpoint_de_detalle_mantiene_su_submodulo():
    """Ver un producto sigue mostrando la pestaña Productos marcada."""
    nav = construir_navegacion("inventario.ver_producto", _puede_todo)
    activos = [s["clave"] for s in nav["submodulos"] if s["activo"]]
    assert activos == ["productos"]


def test_arriendos_vive_bajo_contratos():
    nav = construir_navegacion("arriendos.index", _puede_todo)
    assert nav["modulo_activo"]["clave"] == "contratos"
    assert [s["clave"] for s in nav["submodulos"] if s["activo"]] == ["arriendos"]


def test_clientes_y_proveedores_viven_bajo_datos_maestros():
    nav = construir_navegacion("datos_maestros.proveedores", _puede_todo)
    assert nav["modulo_activo"]["clave"] == "datos_maestros"
    assert [s["clave"] for s in nav["submodulos"] if s["activo"]] == ["proveedores"]


def test_submodulo_de_edicion_requiere_permiso_de_editar():
    def solo_ver(_modulo, accion="ver", submodulo=None):
        return accion == "ver"

    nav = construir_navegacion("inventario.stock", solo_ver)
    assert "importar" not in [s["clave"] for s in nav["submodulos"]]


def test_endpoint_desconocido_no_rompe_la_navegacion():
    nav = construir_navegacion(None, _puede_todo)
    assert nav["modulo_activo"] is None
    assert nav["submodulos"] == []


def test_la_barra_de_submodulos_se_renderiza(client, usuario_admin):
    login(client, "admin@test.cl")
    respuesta = client.get("/inventario/stock")
    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "submodule-bar" in cuerpo
    assert "Ajuste inventario" in cuerpo
