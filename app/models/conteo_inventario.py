from datetime import datetime, timezone

from app.extensions import db


class ItemConteoInventario(db.Model):
    """Cruce de stock entre QMS y Defontana para toma de inventario físico."""

    __tablename__ = "items_conteo_inventario"
    __table_args__ = (db.UniqueConstraint("empresa_id", "codigo", name="uq_conteo_empresa_codigo"),)

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    codigo = db.Column(db.String(80), nullable=False, index=True)
    nombre = db.Column(db.String(255), nullable=True)
    linea_negocio = db.Column(db.String(120), nullable=True)
    ubicacion = db.Column(db.String(255), nullable=True)
    cantidad_qms = db.Column(db.Integer, default=0, nullable=False)
    cantidad_defontana = db.Column(db.Integer, default=0, nullable=False)
    cantidad_fisica = db.Column(db.Integer, nullable=True)
    contado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    contado_en = db.Column(db.DateTime, nullable=True)
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    contado_por = db.relationship("Usuario")

    @property
    def diferencia_sistemas(self) -> int:
        """QMS - Defontana. Distinto de 0 significa que los dos sistemas no cuadran entre sí."""
        return self.cantidad_qms - self.cantidad_defontana

    @property
    def diferencia_fisica(self):
        """Físico contado vs. el mayor de los dos sistemas. None si aún no se ha contado."""
        if self.cantidad_fisica is None:
            return None
        referencia = max(self.cantidad_qms, self.cantidad_defontana)
        return self.cantidad_fisica - referencia

    @property
    def tiene_diferencia(self) -> bool:
        if self.diferencia_sistemas != 0:
            return True
        if self.cantidad_fisica is not None and self.diferencia_fisica != 0:
            return True
        return False

    def __repr__(self):
        return f"<ItemConteoInventario {self.codigo}>"
