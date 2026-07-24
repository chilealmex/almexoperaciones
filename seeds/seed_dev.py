"""Crea datos iniciales: empresa, roles con su matriz de permisos, y un usuario admin.

Uso:
    python seeds/seed_dev.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.empresa import Empresa
from app.models.usuario import Rol, Usuario
from app.models.permiso import MODULOS, RolModuloPermiso

ROLES_PERMISOS = {
    "admin": {modulo: (True, True) for modulo in MODULOS},
    "contador": {
        "inventario": (True, True),
        "contratos": (True, True),
        "activos_fijos": (True, True),
        "arriendos": (True, True),
        "admin": (False, False),
    },
    "bodega": {
        "inventario": (True, True),
        "contratos": (False, False),
        "activos_fijos": (True, False),
        "arriendos": (False, False),
        "admin": (False, False),
    },
    "lectura": {modulo: (True, False) for modulo in MODULOS if modulo != "admin"},
}
ROLES_PERMISOS["lectura"]["admin"] = (False, False)

ROLES_NOMBRES = {
    "admin": "Administrador",
    "contador": "Contador",
    "bodega": "Bodega",
    "lectura": "Solo lectura",
}


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()

        empresa = Empresa.query.filter_by(rut="76.000.000-0").first()
        if empresa is None:
            empresa = Empresa(
                rut="76.000.000-0",
                razon_social="Mi Empresa SPA",
                giro="Servicios",
            )
            db.session.add(empresa)
            db.session.flush()

        roles_creados = {}
        for clave, nombre in ROLES_NOMBRES.items():
            rol = Rol.query.filter_by(clave=clave).first()
            if rol is None:
                rol = Rol(clave=clave, nombre=nombre)
                db.session.add(rol)
                db.session.flush()
            roles_creados[clave] = rol

            for modulo, (puede_ver, puede_editar) in ROLES_PERMISOS[clave].items():
                permiso = RolModuloPermiso.query.filter_by(rol_id=rol.id, modulo=modulo).first()
                if permiso is None:
                    permiso = RolModuloPermiso(rol_id=rol.id, modulo=modulo)
                    db.session.add(permiso)
                permiso.puede_ver = puede_ver
                permiso.puede_editar = puede_editar

        db.session.commit()

        admin_email = "admin@miempresa.cl"
        admin = Usuario.query.filter_by(email=admin_email).first()
        if admin is None:
            admin = Usuario(
                empresa_id=empresa.id,
                nombre_completo="Administrador",
                email=admin_email,
                rol_id=roles_creados["admin"].id,
            )
            admin.set_password("CambiarAhora123")
            db.session.add(admin)
            db.session.commit()
            print(f"Usuario admin creado: {admin_email} / CambiarAhora123 (cámbiala al primer ingreso)")
        else:
            print(f"Usuario admin ya existía: {admin_email}")

        print("Datos iniciales listos.")


if __name__ == "__main__":
    seed()
