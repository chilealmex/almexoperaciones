from datetime import date, datetime, timezone

from app.extensions import db


class ArriendoSalida(db.Model):
    """La empresa arrienda un activo propio A un cliente."""

    __tablename__ = "arriendos_salida"

    PERIODICIDADES = ("diario", "semanal", "mensual")
    ESTADOS = ("activo", "finalizado", "atrasado")

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    activo_fijo_id = db.Column(
        db.Integer, db.ForeignKey("activos_fijos.id"), nullable=False
    )
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_termino_prevista = db.Column(db.Date, nullable=False)
    fecha_devolucion_real = db.Column(db.Date, nullable=True)
    monto_periodo = db.Column(db.Integer, nullable=False)  # CLP
    periodicidad = db.Column(db.String(10), default="mensual", nullable=False)
    condiciones = db.Column(db.Text, nullable=True)
    creado_en = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    firma_cliente_nombre = db.Column(db.String(150), nullable=True)
    firma_cliente_ruta = db.Column(db.String(500), nullable=True)
    firma_cliente_en = db.Column(db.DateTime, nullable=True)
    firma_cliente_ip = db.Column(db.String(45), nullable=True)

    activo_fijo = db.relationship("ActivoFijo", back_populates="arriendos_salida")
    cliente = db.relationship("Cliente", back_populates="arriendos_salida")
    facturaciones = db.relationship(
        "FacturacionArriendoSalida",
        back_populates="arriendo",
        cascade="all, delete-orphan",
    )

    @property
    def estado(self) -> str:
        if self.fecha_devolucion_real is not None:
            return "finalizado"
        if self.fecha_termino_prevista < date.today():
            return "atrasado"
        return "activo"

    @property
    def firmado(self) -> bool:
        return self.firma_cliente_ruta is not None

    def __repr__(self):
        return f"<ArriendoSalida activo={self.activo_fijo_id} cliente={self.cliente_id}>"


class FacturacionArriendoSalida(db.Model):
    __tablename__ = "facturacion_arriendo_salida"

    ESTADOS_PAGO = ("pendiente", "pagado", "vencido")

    id = db.Column(db.Integer, primary_key=True)
    arriendo_salida_id = db.Column(
        db.Integer, db.ForeignKey("arriendos_salida.id"), nullable=False
    )
    periodo = db.Column(db.String(7), nullable=False)  # "YYYY-MM"
    monto = db.Column(db.Integer, nullable=False)
    numero_documento = db.Column(db.String(50), nullable=True)
    estado_pago = db.Column(db.String(10), default="pendiente", nullable=False)
    fecha_pago = db.Column(db.Date, nullable=True)

    arriendo = db.relationship("ArriendoSalida", back_populates="facturaciones")


class ArriendoEntrada(db.Model):
    """La empresa arrienda un activo DE un proveedor externo para uso propio."""

    __tablename__ = "arriendos_entrada"

    PERIODICIDADES = ("diario", "semanal", "mensual")

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedores.id"), nullable=False)
    descripcion_activo = db.Column(db.String(255), nullable=False)
    numero_contrato = db.Column(db.String(50), nullable=True)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_termino = db.Column(db.Date, nullable=False)
    monto_periodo = db.Column(db.Integer, nullable=False)
    periodicidad = db.Column(db.String(10), default="mensual", nullable=False)
    dias_alerta_vencimiento = db.Column(db.Integer, default=30, nullable=False)
    ubicacion_uso = db.Column(db.String(150), nullable=True)
    responsable_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    terminado_manualmente = db.Column(db.Boolean, default=False, nullable=False)
    creado_en = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    proveedor = db.relationship("Proveedor", back_populates="arriendos_entrada")
    responsable = db.relationship("Usuario")
    pagos = db.relationship(
        "PagoArriendoEntrada", back_populates="arriendo", cascade="all, delete-orphan"
    )

    @property
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
        return f"<ArriendoEntrada proveedor={self.proveedor_id}>"


class PagoArriendoEntrada(db.Model):
    __tablename__ = "pagos_arriendo_entrada"

    ESTADOS_PAGO = ("pendiente", "pagado", "atrasado")

    id = db.Column(db.Integer, primary_key=True)
    arriendo_entrada_id = db.Column(
        db.Integer, db.ForeignKey("arriendos_entrada.id"), nullable=False
    )
    periodo = db.Column(db.String(7), nullable=False)
    monto = db.Column(db.Integer, nullable=False)
    fecha_pago_programada = db.Column(db.Date, nullable=False)
    fecha_pago_real = db.Column(db.Date, nullable=True)
    estado_pago = db.Column(db.String(10), default="pendiente", nullable=False)
    numero_documento = db.Column(db.String(50), nullable=True)

    arriendo = db.relationship("ArriendoEntrada", back_populates="pagos")
