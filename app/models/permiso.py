from app.extensions import db

MODULOS = ("inventario", "contratos", "activos_fijos", "arriendos", "admin")


class RolModuloPermiso(db.Model):
    """Matriz de permisos por defecto para cada rol."""

    __tablename__ = "rol_modulo_permiso"
    __table_args__ = (db.UniqueConstraint("rol_id", "modulo", name="uq_rol_modulo"),)

    id = db.Column(db.Integer, primary_key=True)
    rol_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    modulo = db.Column(db.String(30), nullable=False)
    puede_ver = db.Column(db.Boolean, default=False, nullable=False)
    puede_editar = db.Column(db.Boolean, default=False, nullable=False)

    rol = db.relationship("Rol", back_populates="permisos")


class PermisoUsuario(db.Model):
    """Override individual de permisos por usuario, tiene prioridad sobre el rol."""

    __tablename__ = "permisos_usuario"
    __table_args__ = (
        db.UniqueConstraint("usuario_id", "modulo", name="uq_usuario_modulo"),
    )

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    modulo = db.Column(db.String(30), nullable=False)
    puede_ver = db.Column(db.Boolean, default=False, nullable=False)
    puede_editar = db.Column(db.Boolean, default=False, nullable=False)

    usuario = db.relationship("Usuario", back_populates="permisos_custom")
