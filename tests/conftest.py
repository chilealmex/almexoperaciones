import pytest

from app import create_app
from app.extensions import db as _db
from app.models.empresa import Empresa
from app.models.usuario import Rol, Usuario
from app.models.permiso import MODULOS, RolModuloPermiso


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def empresa(db):
    empresa = Empresa(rut="76.000.000-0", razon_social="Empresa de Prueba SPA")
    db.session.add(empresa)
    db.session.commit()
    return empresa


@pytest.fixture()
def roles(db):
    admin = Rol(clave="admin", nombre="Administrador")
    bodega = Rol(clave="bodega", nombre="Bodega")
    db.session.add_all([admin, bodega])
    db.session.commit()

    for modulo in MODULOS:
        db.session.add(RolModuloPermiso(rol_id=admin.id, modulo=modulo, puede_ver=True, puede_editar=True))

    db.session.add(RolModuloPermiso(rol_id=bodega.id, modulo="inventario", puede_ver=True, puede_editar=False))
    db.session.commit()
    return {"admin": admin, "bodega": bodega}


@pytest.fixture()
def usuario_admin(db, empresa, roles):
    usuario = Usuario(
        empresa_id=empresa.id,
        nombre_completo="Admin de Prueba",
        nombre_usuario="admin_prueba",
        email="admin@test.cl",
        rol_id=roles["admin"].id,
    )
    usuario.set_password("password123")
    db.session.add(usuario)
    db.session.commit()
    return usuario


@pytest.fixture()
def usuario_bodega(db, empresa, roles):
    usuario = Usuario(
        empresa_id=empresa.id,
        nombre_completo="Bodega de Prueba",
        nombre_usuario="bodega_prueba",
        email="bodega@test.cl",
        rol_id=roles["bodega"].id,
    )
    usuario.set_password("password123")
    db.session.add(usuario)
    db.session.commit()
    return usuario


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, identificador, password="password123"):
    return client.post(
        "/login", data={"identificador": identificador, "password": password}, follow_redirects=True
    )
