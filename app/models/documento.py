from datetime import datetime, timezone

from app.extensions import db


class Documento(db.Model):
    """Adjunto genérico reutilizado por todos los módulos (contratos, movimientos, activos, arriendos)."""

    __tablename__ = "documentos"

    ENTIDADES = (
        "contrato_cliente",
        "movimiento_inventario",
        "activo_fijo",
        "arriendo_salida",
        "arriendo_entrada",
    )

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    entidad_tipo = db.Column(db.String(30), nullable=False)
    entidad_id = db.Column(db.Integer, nullable=False)
    nombre_archivo = db.Column(db.String(255), nullable=False)
    ruta_archivo = db.Column(db.String(500), nullable=False)
    tipo_mime = db.Column(db.String(100), nullable=True)
    tamano_bytes = db.Column(db.Integer, nullable=True)
    subido_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    subido_en = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    subido_por = db.relationship("Usuario")

    def __repr__(self):
        return f"<Documento {self.nombre_archivo} ({self.entidad_tipo}#{self.entidad_id})>"
