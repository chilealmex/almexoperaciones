from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


class Rol(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(30), unique=True, nullable=False)
    nombre = db.Column(db.String(80), nullable=False)

    usuarios = db.relationship("Usuario", back_populates="rol")
    permisos = db.relationship(
        "RolModuloPermiso", back_populates="rol", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Rol {self.clave}>"


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    nombre_completo = db.Column(db.String(150), nullable=False)
    nombre_usuario = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    rut = db.Column(db.String(12), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    creado_en = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    ultimo_login = db.Column(db.DateTime, nullable=True)

    rol = db.relationship("Rol", back_populates="usuarios")
    empresa = db.relationship("Empresa", back_populates="usuarios")
    permisos_custom = db.relationship(
        "PermisoUsuario", back_populates="usuario", cascade="all, delete-orphan"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.activo

    def _mapa_permisos(self):
        """Todos los permisos del usuario, leídos de la base una sola vez por petición.

        Antes cada consulta de permiso iba a la base, y como se pregunta por cada
        módulo del menú y por cada fila de una tabla, una sola pantalla llegaba a
        hacer cientos de idas.

        Se guardan en el contexto de la petición y no en el objeto del usuario:
        ese contexto se limpia solo al terminar cada petición, así que un cambio
        de permisos nunca queda pegado de una petición a la siguiente.
        """
        from flask import g, has_request_context

        from app.models.permiso import PermisoUsuario, RolModuloPermiso

        def leer():
            propios = {
                (p.modulo, p.submodulo or ""): p
                for p in PermisoUsuario.query.filter_by(usuario_id=self.id).all()
            }
            del_rol = {
                p.modulo: p for p in RolModuloPermiso.query.filter_by(rol_id=self.rol_id).all()
            }
            return propios, del_rol

        if not has_request_context():
            return leer()

        cache = getattr(g, "_permisos_por_usuario", None)
        if cache is None:
            cache = g._permisos_por_usuario = {}
        if self.id not in cache:
            cache[self.id] = leer()
        return cache[self.id]

    def tiene_permiso(self, modulo: str, accion: str = "ver", submodulo: str | None = None) -> bool:
        if self.es_superadmin:
            return True

        propios, del_rol = self._mapa_permisos()

        def resolver(permiso):
            return permiso.puede_editar if accion == "editar" else permiso.puede_ver

        if submodulo:
            override_sub = propios.get((modulo, submodulo))
            if override_sub is not None:
                return resolver(override_sub)
            # Sin override propio del submódulo: hereda el permiso del módulo completo.

        override = propios.get((modulo, ""))
        if override is not None:
            return resolver(override)

        default = del_rol.get(modulo)
        if default is None:
            return False
        return resolver(default)

    @property
    def es_superadmin(self) -> bool:
        return self.rol is not None and self.rol.clave == "superadmin"

    @property
    def es_admin_o_superior(self) -> bool:
        return self.rol is not None and self.rol.clave in ("admin", "superadmin")

    def puede_gestionar_a(self, otro: "Usuario") -> bool:
        """Un superadmin gestiona a cualquiera; un admin solo a usuarios normales (no a otros admins/superadmins)."""
        if self.es_superadmin:
            return True
        if self.es_admin_o_superior:
            return not otro.es_admin_o_superior
        return False

    def __repr__(self):
        return f"<Usuario {self.email}>"
