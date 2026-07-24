from datetime import date, datetime, timezone

from sqlalchemy.ext.hybrid import hybrid_property

from app.extensions import db


class ContratoCliente(db.Model):
    __tablename__ = "contratos_cliente"

    PERIODICIDADES = ("unico", "mensual", "anual")

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    numero_contrato = db.Column(db.String(50), nullable=False)
    objeto = db.Column(db.String(255), nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_termino = db.Column(db.Date, nullable=False)
    monto = db.Column(db.Integer, nullable=False)  # CLP
    moneda = db.Column(db.String(3), default="CLP", nullable=False)
    periodicidad_pago = db.Column(db.String(10), default="unico", nullable=False)
    dias_alerta_vencimiento = db.Column(db.Integer, default=30, nullable=False)
    usuario_responsable_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=True
    )
    contrato_anterior_id = db.Column(
        db.Integer, db.ForeignKey("contratos_cliente.id"), nullable=True
    )
    notas = db.Column(db.Text, nullable=True)
    terminado_manualmente = db.Column(db.Boolean, default=False, nullable=False)
    creado_en = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    cliente = db.relationship("Cliente", back_populates="contratos")
    usuario_responsable = db.relationship("Usuario")
    contrato_anterior = db.relationship("ContratoCliente", remote_side=[id])

    @hybrid_property
    def estado(self) -> str:
        if self.terminado_manualmente:
            return "terminado"
        hoy = date.today()
        if self.fecha_termino < hoy:
            return "vencido"
        dias_restantes = (self.fecha_termino - hoy).days
        if dias_restantes <= self.dias_alerta_vencimiento:
            return "por_vencer"
        return "vigente"

    def __repr__(self):
        return f"<ContratoCliente {self.numero_contrato}>"
