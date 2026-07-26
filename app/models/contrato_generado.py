from datetime import datetime, timezone

from app.extensions import db


class ContratoGenerado(db.Model):
    """Contrato de arriendo de equipos generado desde la plantilla Shaw Almex, con los datos variables por cliente."""

    __tablename__ = "contratos_generados"

    TIPOS_FIADOR = ("natural", "empresa")

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)

    fecha_contrato = db.Column(db.Date, nullable=False)
    correo_arrendador = db.Column(db.String(120), nullable=True)

    # Arrendatario (parte de los datos vienen del cliente; estos son los que no están en su ficha)
    representante_nombre = db.Column(db.String(150), nullable=False)
    representante_cedula = db.Column(db.String(15), nullable=False)
    arrendatario_domicilio = db.Column(db.String(255), nullable=False)
    arrendatario_correo = db.Column(db.String(120), nullable=False)

    # Fiador y codeudor solidario
    fiador_tipo = db.Column(db.String(10), default="natural", nullable=False)
    fiador_nombre = db.Column(db.String(150), nullable=False)
    fiador_rut = db.Column(db.String(15), nullable=False)
    fiador_domicilio = db.Column(db.String(255), nullable=True)
    fiador_correo = db.Column(db.String(120), nullable=True)
    fiador_representante = db.Column(db.String(150), nullable=True)  # solo si el fiador es empresa

    cotizacion_numero = db.Column(db.String(30), nullable=False)
    cotizacion_fecha = db.Column(db.Date, nullable=False)
    planta_ubicacion = db.Column(db.String(255), nullable=False)
    deducible_uf = db.Column(db.Integer, nullable=False)

    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    creado_en = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    cliente = db.relationship("Cliente")
    creado_por = db.relationship("Usuario")

    def __repr__(self):
        return f"<ContratoGenerado cliente={self.cliente_id} cot={self.cotizacion_numero}>"
