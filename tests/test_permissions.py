from app.models.permiso import PermisoUsuario, RolModuloPermiso
from app.models.usuario import Rol, Usuario
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


def _crear_superadmin(db, empresa):
    rol = Rol(clave="superadmin", nombre="Super administrador")
    db.session.add(rol)
    db.session.commit()
    usuario = Usuario(
        empresa_id=empresa.id,
        nombre_completo="Super",
        nombre_usuario="super_prueba",
        email="super@test.cl",
        rol_id=rol.id,
    )
    usuario.set_password("password123")
    db.session.add(usuario)
    db.session.commit()
    return usuario


def test_superadmin_tiene_acceso_a_todo_sin_permisos_explicitos(db, empresa):
    superadmin = _crear_superadmin(db, empresa)
    assert superadmin.tiene_permiso("inventario", "editar")
    assert superadmin.tiene_permiso("admin", "editar")


def test_admin_no_puede_gestionar_a_otro_admin(db, usuario_admin):
    otro_admin = Usuario(
        empresa_id=usuario_admin.empresa_id,
        nombre_completo="Otro admin",
        nombre_usuario="otroadmin_prueba",
        email="otroadmin@test.cl",
        rol_id=usuario_admin.rol_id,
    )
    otro_admin.set_password("password123")
    db.session.add(otro_admin)
    db.session.commit()

    assert not usuario_admin.puede_gestionar_a(otro_admin)


def test_admin_puede_gestionar_a_usuario_normal(db, empresa, usuario_admin):
    rol_usuario = Rol(clave="usuario", nombre="Usuario")
    db.session.add(rol_usuario)
    db.session.commit()
    normal = Usuario(
        empresa_id=empresa.id,
        nombre_completo="Normal",
        nombre_usuario="normal_prueba",
        email="normal@test.cl",
        rol_id=rol_usuario.id,
    )
    normal.set_password("password123")
    db.session.add(normal)
    db.session.commit()

    assert usuario_admin.puede_gestionar_a(normal)


def test_admin_no_puede_editar_a_otro_admin_via_ruta(client, db, usuario_admin):
    otro_admin = Usuario(
        empresa_id=usuario_admin.empresa_id,
        nombre_completo="Otro admin",
        nombre_usuario="otroadmin2_prueba",
        email="otroadmin2@test.cl",
        rol_id=usuario_admin.rol_id,
    )
    otro_admin.set_password("password123")
    db.session.add(otro_admin)
    db.session.commit()

    login(client, "admin@test.cl")
    response = client.get(f"/admin/usuarios/{otro_admin.id}/editar")
    assert response.status_code == 403


def test_admin_no_puede_configurar_permisos_ni_por_url_directa(client, db, empresa, usuario_admin):
    rol_usuario = Rol(clave="usuario", nombre="Usuario")
    db.session.add(rol_usuario)
    db.session.commit()
    normal = Usuario(
        empresa_id=empresa.id,
        nombre_completo="Normal",
        nombre_usuario="normal2_prueba",
        email="normal2@test.cl",
        rol_id=rol_usuario.id,
    )
    normal.set_password("password123")
    db.session.add(normal)
    db.session.commit()

    login(client, "admin@test.cl")
    response = client.get(f"/admin/usuarios/{normal.id}/permisos")
    assert response.status_code == 403


def test_superadmin_si_puede_configurar_permisos(client, db, empresa, usuario_admin):
    superadmin = _crear_superadmin(db, empresa)
    rol_usuario = Rol(clave="usuario", nombre="Usuario")
    db.session.add(rol_usuario)
    db.session.commit()
    normal = Usuario(
        empresa_id=empresa.id,
        nombre_completo="Normal",
        nombre_usuario="normal3_prueba",
        email="normal3@test.cl",
        rol_id=rol_usuario.id,
    )
    normal.set_password("password123")
    db.session.add(normal)
    db.session.commit()

    login(client, "super@test.cl")
    response = client.get(f"/admin/usuarios/{normal.id}/permisos")
    assert response.status_code == 200


def test_link_de_permisos_no_aparece_para_admin_normal(client, usuario_admin, usuario_bodega):
    login(client, "admin@test.cl")
    response = client.get("/admin/usuarios")
    assert b"Editar" in response.data
    assert b"/permisos" not in response.data
