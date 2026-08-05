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


class PeriodoDifTc(db.Model):
    """Un mes de la contabilización de diferencia de tipo de cambio.

    Cada mes se parte de la base contable del momento y se aplica el tipo de
    cambio de cierre. Como el tipo de cambio cambia mes a mes, cada período
    guarda el suyo y sus propias líneas: así queda el historial y se puede
    volver a mirar un mes ya contabilizado sin que lo altere el mes siguiente.
    """

    __tablename__ = "periodos_dif_tc"
    __table_args__ = (
        db.UniqueConstraint("empresa_id", "anio", "mes", name="uq_periodo_dif_tc_mes"),
    )

    ESTADOS = (("en_proceso", "En proceso"), ("cerrado", "Cerrado"))

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    anio = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)
    # El tipo de cambio de cierre del mes: multiplica el monto en moneda origen
    # de todas las líneas (la celda AB2 de la planilla).
    tipo_cambio = db.Column(db.Float, nullable=False, default=0)
    estado = db.Column(db.String(15), nullable=False, default="en_proceso")
    notas = db.Column(db.String(255), nullable=True)

    creado_en = db.Column(db.DateTime, server_default=db.func.now())
    actualizado_en = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    lineas = db.relationship(
        "LineaDifTc", back_populates="periodo", cascade="all, delete-orphan",
        order_by="LineaDifTc.orden",
    )

    def __repr__(self):
        return f"<PeriodoDifTc {self.mes:02d}.{self.anio}>"


class LineaDifTc(db.Model):
    """Una línea del mayor con su diferencia de cambio.

    Las columnas de la izquierda vienen del mayor contable y no se editan. Solo
    "Mon Orig" se escribe a mano (es la columna amarilla de la planilla); el
    valor en pesos, la diferencia y el porcentaje se calculan.
    """

    __tablename__ = "lineas_dif_tc"

    id = db.Column(db.Integer, primary_key=True)
    periodo_id = db.Column(db.Integer, db.ForeignKey("periodos_dif_tc.id"), nullable=False, index=True)
    orden = db.Column(db.Integer, nullable=False, default=0)

    # --- Vienen del mayor, no se editan ---
    cuenta = db.Column(db.String(30), nullable=True)
    descripcion = db.Column(db.String(150), nullable=True)
    fecha = db.Column(db.Date, nullable=True)
    tipo = db.Column(db.String(30), nullable=True)
    numero = db.Column(db.String(30), nullable=True)
    id_ficha = db.Column(db.String(30), nullable=True)
    ficha = db.Column(db.String(150), nullable=True)
    cargo = db.Column(db.BigInteger, nullable=False, default=0)
    abono = db.Column(db.BigInteger, nullable=False, default=0)
    saldo = db.Column(db.BigInteger, nullable=False, default=0)
    codigo_doc = db.Column(db.String(40), nullable=True)
    documento = db.Column(db.String(120), nullable=True)
    vencimiento = db.Column(db.String(20), nullable=True)
    numero_doc = db.Column(db.String(40), nullable=True)
    tipo_mov = db.Column(db.String(40), nullable=True)
    serie = db.Column(db.String(40), nullable=True)
    numero_mov = db.Column(db.String(40), nullable=True)
    moneda_ref = db.Column(db.String(20), nullable=True)
    comentario = db.Column(db.String(255), nullable=True)
    doc_pago = db.Column(db.String(40), nullable=True)
    numero_doc_pago = db.Column(db.String(40), nullable=True)
    serie_doc_pago = db.Column(db.String(40), nullable=True)

    # --- Columna amarilla: se escribe a mano ---
    mon_orig = db.Column(db.Float, nullable=True)

    # --- Calculadas con el tipo de cambio del período ---
    valor_clp = db.Column(db.BigInteger, nullable=False, default=0)
    dif_cambio = db.Column(db.BigInteger, nullable=False, default=0)
    pct_variacion = db.Column(db.Float, nullable=False, default=0)

    periodo = db.relationship("PeriodoDifTc", back_populates="lineas")

    def __repr__(self):
        return f"<LineaDifTc {self.cuenta}/{self.numero_doc}>"
