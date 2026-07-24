from app.models.permiso import PermisoUsuario
from tests.conftest import login


def test_rol_admin_tiene_todos_los_permisos(usuario_admin):
    assert usuario_admin.tiene_permiso("inventario", "editar")
    assert usuario_admin.tiene_permiso("contratos", "editar")
    assert usuario_admin.tiene_permiso("admin", "editar")


def test_rol_bodega_solo_ve_inventario_sin_editar(usuario_bodega):
    assert usuario_bodega.tiene_permiso("inventario", "ver")
    assert not usuario_bodega.tiene_permiso("inventario", "editar")
    assert not usuario_bodega.tiene_permiso("contratos", "ver")


def test_override_por_usuario_tiene_prioridad_sobre_el_rol(db, usuario_bodega):
    db.session.add(
        PermisoUsuario(usuario_id=usuario_bodega.id, modulo="inventario", puede_ver=True, puede_editar=True)
    )
    db.session.commit()

    assert usuario_bodega.tiene_permiso("inventario", "editar")


def test_usuario_sin_permiso_recibe_403(client, usuario_bodega):
    login(client, "bodega@test.cl")
    response = client.get("/contratos/")
    assert response.status_code == 403


def test_usuario_con_permiso_accede(client, usuario_bodega):
    login(client, "bodega@test.cl")
    response = client.get("/inventario/")
    assert response.status_code == 200
