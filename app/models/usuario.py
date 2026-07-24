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

    def tiene_permiso(self, modulo: str, accion: str = "ver") -> bool:
        if self.es_superadmin:
            return True

        from app.models.permiso import PermisoUsuario, RolModuloPermiso

        override = PermisoUsuario.query.filter_by(
            usuario_id=self.id, modulo=modulo
        ).first()
        if override is not None:
            return override.puede_editar if accion == "editar" else override.puede_ver

        default = RolModuloPermiso.query.filter_by(
            rol_id=self.rol_id, modulo=modulo
        ).first()
        if default is None:
            return False
        return default.puede_editar if accion == "editar" else default.puede_ver

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
