from app.extensions import db


class ProvisionIngreso(db.Model):
    """Una línea de la planilla "Provisión de Ingresos" (hoja Control).

    Los datos llegan importando el Excel y se van acumulando: cada importación
    agrega las líneas nuevas y deja intactas las que ya estaban, para no pisar
    lo que se editó a mano. La línea se reconoce por mes, comprobante de
    provisión y OT, que en la planilla no se repiten.

    De todas las columnas, solo cuatro se editan desde la aplicación: reversa,
    mes de reversa, comprobante de reversa y saldo. El resto viene del Excel.
    """

    __tablename__ = "provisiones_ingreso"
    __table_args__ = (
        db.UniqueConstraint("empresa_id", "mes_ano", "cbte_prov", "ot", name="uq_provision_ingreso_linea"),
    )

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)

    # --- Viene del Excel, no se edita en pantalla ---
    mes_ano = db.Column(db.Date, nullable=False)
    cbte_prov = db.Column(db.String(30), nullable=False)
    ot = db.Column(db.String(30), nullable=False)
    monto_provision = db.Column(db.Integer, nullable=False, default=0)
    cliente = db.Column(db.String(200), nullable=True)
    centro_costos = db.Column(db.String(60), nullable=True)
    rut = db.Column(db.String(20), nullable=True)
    obs = db.Column(db.String(255), nullable=True)

    # --- Se edita en pantalla ---
    reversa = db.Column(db.Integer, nullable=True)
    # Texto y no fecha: una provisión puede reversarse en más de un mes
    # ("may-26 y jun-26"), igual que en la planilla de origen.
    mes_reversa = db.Column(db.String(60), nullable=True)
    cbte_reversa = db.Column(db.String(60), nullable=True)
    saldo = db.Column(db.Integer, nullable=False, default=0)

    creado_en = db.Column(db.DateTime, server_default=db.func.now())
    actualizado_en = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def __repr__(self):
        return f"<ProvisionIngreso {self.cbte_prov}/{self.ot}>"
