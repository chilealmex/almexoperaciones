from app.models.conteo_inventario import ItemConteoInventario
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


# --- Permisos a nivel de submódulo ---


def test_submodulo_sin_override_hereda_el_permiso_del_modulo(usuario_bodega):
    # Bodega tiene "inventario" ver=True a nivel de módulo y ningún override de submódulo.
    assert usuario_bodega.tiene_permiso("inventario", "ver", submodulo="stock")
    assert usuario_bodega.tiene_permiso("inventario", "ver", submodulo="ajuste")


def test_override_de_submodulo_puede_restringir_por_debajo_del_modulo(db, usuario_bodega):
    db.session.add(
        PermisoUsuario(usuario_id=usuario_bodega.id, modulo="inventario", submodulo="ajuste", puede_ver=False, puede_editar=False)
    )
    db.session.commit()

    assert not usuario_bodega.tiene_permiso("inventario", "ver", submodulo="ajuste")
    # El resto de los submódulos del mismo módulo no se ven afectados.
    assert usuario_bodega.tiene_permiso("inventario", "ver", submodulo="stock")
    assert usuario_bodega.tiene_permiso("inventario", "ver")


def test_override_de_submodulo_puede_superar_el_permiso_del_modulo(db, usuario_bodega):
    # Bodega no tiene "editar" en inventario a nivel de módulo, pero sí lo puede
    # tener puntualmente en un submódulo (ej. solo puede registrar el conteo físico).
    db.session.add(
        PermisoUsuario(usuario_id=usuario_bodega.id, modulo="inventario", submodulo="stock", puede_ver=True, puede_editar=True)
    )
    db.session.commit()

    assert usuario_bodega.tiene_permiso("inventario", "editar", submodulo="stock")
    assert not usuario_bodega.tiene_permiso("inventario", "editar")
    assert not usuario_bodega.tiene_permiso("inventario", "editar", submodulo="ajuste")


def test_ruta_respeta_el_override_de_submodulo(client, db, usuario_bodega):
    login(client, "bodega@test.cl")
    # Sin override: bodega ve tanto stock como ajuste (hereda el "ver" del módulo).
    assert client.get("/inventario/stock").status_code == 200
    assert client.get("/inventario/ajuste").status_code == 200

    db.session.add(
        PermisoUsuario(usuario_id=usuario_bodega.id, modulo="inventario", submodulo="ajuste", puede_ver=False, puede_editar=False)
    )
    db.session.commit()

    # Con el override, "ajuste" queda bloqueado pero "stock" sigue disponible.
    assert client.get("/inventario/ajuste").status_code == 403
    assert client.get("/inventario/stock").status_code == 200


def test_permisos_usuario_guarda_overrides_de_submodulo(client, db, empresa, usuario_admin):
    superadmin = _crear_superadmin(db, empresa)
    rol_usuario = Rol(clave="usuario", nombre="Usuario")
    db.session.add(rol_usuario)
    db.session.commit()
    normal = Usuario(
        empresa_id=empresa.id,
        nombre_completo="Normal",
        nombre_usuario="normal4_prueba",
        email="normal4@test.cl",
        rol_id=rol_usuario.id,
    )
    normal.set_password("password123")
    db.session.add(normal)
    db.session.commit()

    login(client, "super@test.cl")
    respuesta_form = client.get(f"/admin/usuarios/{normal.id}/permisos")
    assert b"inventario__stock" in respuesta_form.data or b"ver_inventario__stock" in respuesta_form.data

    respuesta = client.post(
        f"/admin/usuarios/{normal.id}/permisos",
        data={
            "csrf_token": "",
            "heredar_inventario": "on",
            "heredar_inventario__stock": "",
            "ver_inventario__stock": "on",
            "editar_inventario__stock": "on",
        },
    )
    assert respuesta.status_code == 302

    override = PermisoUsuario.query.filter_by(usuario_id=normal.id, modulo="inventario", submodulo="stock").first()
    assert override is not None
    assert override.puede_ver
    assert override.puede_editar

    override_modulo = PermisoUsuario.query.filter_by(usuario_id=normal.id, modulo="inventario", submodulo="").first()
    assert override_modulo is None  # "heredar" seguía marcado a nivel de módulo


def test_puede_infiere_el_submodulo_de_la_pagina_actual(client, db, empresa, usuario_bodega):
    """El helper puede() de las plantillas respeta el override de submódulo sin que la plantilla lo declare."""
    db.session.add(ItemConteoInventario(empresa_id=empresa.id, codigo="COD-001", nombre="PRODUCTO UNO", cantidad_qms=10, cantidad_defontana=10))
    db.session.add(
        PermisoUsuario(usuario_id=usuario_bodega.id, modulo="inventario", submodulo="stock", puede_ver=True, puede_editar=True)
    )
    db.session.commit()

    login(client, "bodega@test.cl")
    # Bodega no tiene "editar" a nivel de módulo, pero sí en el submódulo "stock":
    # el campo Físico debe aparecer como editable en esa página.
    cuerpo = client.get("/inventario/stock").get_data(as_text=True)
    assert "input-fisico" in cuerpo

    # En Ajuste inventario (mismo módulo, sin override propio) no hereda ese editar.
    assert not usuario_bodega.tiene_permiso("inventario", "editar", submodulo="ajuste")
