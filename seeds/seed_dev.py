"""Crea datos iniciales: empresa, roles con su matriz de permisos, y el usuario super admin.

Uso:
    python seeds/seed_dev.py
"""
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.empresa import Empresa
from app.models.usuario import Rol, Usuario
from app.models.permiso import MODULOS, RolModuloPermiso

# Jerarquía de 3 niveles:
#  - superadmin: acceso total, único que puede crear/editar otros admins o superadmins.
#  - admin: acceso total a los módulos de negocio, pero solo gestiona usuarios de rol "usuario".
#  - usuario: sin acceso por defecto; el admin/superadmin parametriza módulo por módulo.
ROLES_PERMISOS = {
    "superadmin": {modulo: (True, True) for modulo in MODULOS},
    "admin": {modulo: (True, True) for modulo in MODULOS},
    "usuario": {modulo: (False, False) for modulo in MODULOS},
}

ROLES_NOMBRES = {
    "superadmin": "Super administrador",
    "admin": "Administrador",
    "usuario": "Usuario",
}


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()

        empresa_rut = os.environ.get("EMPRESA_RUT", "76.000.000-0")
        empresa = Empresa.query.filter_by(rut=empresa_rut).first()
        if empresa is None:
            empresa = Empresa(
                rut=empresa_rut,
                razon_social=os.environ.get("EMPRESA_NOMBRE", "Mi Empresa SPA"),
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

        admin_email = os.environ.get("ADMIN_EMAIL", "admin@miempresa.cl")
        admin_username = os.environ.get("ADMIN_USERNAME", "admin")
        admin = Usuario.query.filter_by(email=admin_email).first()
        if admin is None:
            password_inicial = secrets.token_urlsafe(12)
            admin = Usuario(
                empresa_id=empresa.id,
                nombre_completo="Super Administrador",
                nombre_usuario=admin_username,
                email=admin_email,
                rol_id=roles_creados["superadmin"].id,
            )
            admin.set_password(password_inicial)
            db.session.add(admin)
            db.session.commit()
            print("=" * 60)
            print(f"Usuario super admin creado: {admin_username} ({admin_email})")
            print(f"Contraseña inicial (cópiala ahora, no se vuelve a mostrar): {password_inicial}")
            print("Cámbiala apenas inicies sesión, en tu nombre (arriba a la derecha) > Cambiar contraseña.")
            print("=" * 60)
        else:
            cambios = []
            if not admin.es_superadmin:
                # Compatibilidad: instalaciones previas a la jerarquía de 3 niveles.
                admin.rol_id = roles_creados["superadmin"].id
                cambios.append("rol -> superadmin")
            if not admin.nombre_usuario:
                # Compatibilidad: instalaciones previas al login por nombre de usuario.
                admin.nombre_usuario = admin_username
                cambios.append(f"nombre_usuario -> {admin_username}")
            if cambios:
                db.session.commit()
                print(f"Usuario {admin_email} actualizado: {', '.join(cambios)}.")
            else:
                print(f"Usuario super admin ya existía: {admin.nombre_usuario} ({admin_email})")

        print("Datos iniciales listos.")


if __name__ == "__main__":
    seed()
