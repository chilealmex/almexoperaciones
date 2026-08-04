from app.extensions import db

MONEDAS = (("USD", "USD"), ("EUR", "EUR"), ("CLP", "CLP"))
ESTADOS_COSTEO = (
    ("en_proceso", "En proceso"),
    ("cerrado", "Cerrado"),
)


class CosteoImportacion(db.Model):
    """Cabecera del costeo detallado de una importación (prorrateo de CIF y gastos por producto)."""

    __tablename__ = "costeo_importaciones"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    importacion_id = db.Column(db.Integer, db.ForeignKey("importaciones.id"), nullable=True)

    n_importacion = db.Column(db.String(30), nullable=True)
    fecha_llegada = db.Column(db.Date, nullable=True)
    guia_despacho = db.Column(db.String(40), nullable=True)
    proveedor = db.Column(db.String(150), nullable=True)
    modo_venta = db.Column(db.String(40), nullable=True)
    purchase_order = db.Column(db.String(40), nullable=True)
    orden_trabajo = db.Column(db.String(60), nullable=True)
    responsable_costeo = db.Column(db.String(120), nullable=True)
    tipo_flete_proyectado = db.Column(db.String(20), nullable=True)
    solicitud_compra = db.Column(db.String(40), nullable=True)
    tasa_ad_valorem = db.Column(db.Float, nullable=False, default=0.06)
    estado = db.Column(db.String(15), nullable=False, default="en_proceso")

    # --- Control DIN de esta importación (antes era un submódulo aparte) ---
    din_agencia = db.Column(db.String(100), nullable=True)
    din_n_doc_agencia = db.Column(db.String(40), nullable=True)
    din_monto_doc_agencia = db.Column(db.Integer, nullable=True)
    din_n_invoice = db.Column(db.String(40), nullable=True)
    din_estado = db.Column(db.String(15), nullable=True)
    din_rut = db.Column(db.String(20), nullable=True)
    din_razon_social = db.Column(db.String(150), nullable=True)
    din_formulario = db.Column(db.String(10), nullable=True)
    din_folio = db.Column(db.String(30), nullable=True)
    din_fecha_pago = db.Column(db.Date, nullable=True)
    din_vcto = db.Column(db.Date, nullable=True)
    din_advalorem_clp = db.Column(db.Integer, nullable=True)
    din_total_pagado = db.Column(db.Integer, nullable=True)

    creado_en = db.Column(db.DateTime, server_default=db.func.now())
    actualizado_en = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    importacion = db.relationship("Importacion")

    documentos = db.relationship(
        "CosteoImportacionDocumento",
        back_populates="costeo",
        cascade="all, delete-orphan",
        order_by="CosteoImportacionDocumento.orden",
    )
    gastos_internos = db.relationship(
        "CosteoImportacionGastoInterno",
        back_populates="costeo",
        cascade="all, delete-orphan",
        order_by="CosteoImportacionGastoInterno.orden",
    )
    productos = db.relationship(
        "CosteoImportacionProducto",
        back_populates="costeo",
        cascade="all, delete-orphan",
        order_by="CosteoImportacionProducto.orden",
    )

    def __repr__(self):
        return f"<CosteoImportacion {self.n_importacion}>"

    def documento_por_rol(self, rol):
        return next((d for d in self.documentos if d.rol == rol), None)

    def gasto_por_rol(self, rol):
        return next((g for g in self.gastos_internos if g.rol == rol), None)


class CosteoImportacionDocumento(db.Model):
    """Una de las 8 líneas fijas de la tabla de documentos (Invoice 1-4, Seguro, Flete, Crating)."""

    __tablename__ = "costeo_importacion_documentos"
    __table_args__ = (db.UniqueConstraint("costeo_id", "rol", name="uq_costeo_documento_rol"),)

    id = db.Column(db.Integer, primary_key=True)
    costeo_id = db.Column(db.Integer, db.ForeignKey("costeo_importaciones.id"), nullable=False)
    rol = db.Column(db.String(20), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0)

    moneda = db.Column(db.String(6), nullable=False, default="USD")
    nro_doc = db.Column(db.String(40), nullable=True)
    valor_tc = db.Column(db.Float, nullable=True)
    valor_total_inv = db.Column(db.Float, nullable=True)
    valor_clp = db.Column(db.Integer, nullable=False, default=0)

    costeo = db.relationship("CosteoImportacion", back_populates="documentos")

    def __repr__(self):
        return f"<CosteoImportacionDocumento {self.rol}>"


class CosteoImportacionGastoInterno(db.Model):
    """Una de las 6 líneas fijas de gastos internos nacionales (Almacenaje, Desconsolidación, etc.)."""

    __tablename__ = "costeo_importacion_gastos_internos"
    __table_args__ = (db.UniqueConstraint("costeo_id", "rol", name="uq_costeo_gasto_rol"),)

    id = db.Column(db.Integer, primary_key=True)
    costeo_id = db.Column(db.Integer, db.ForeignKey("costeo_importaciones.id"), nullable=False)
    rol = db.Column(db.String(20), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0)

    nro_doc = db.Column(db.String(40), nullable=True)
    valor_clp = db.Column(db.Integer, nullable=False, default=0)

    costeo = db.relationship("CosteoImportacion", back_populates="gastos_internos")

    def __repr__(self):
        return f"<CosteoImportacionGastoInterno {self.rol}>"


class CosteoImportacionProducto(db.Model):
    """Una línea de producto: datos manuales + el prorrateo de CIF/gastos calculado por recalcular()."""

    __tablename__ = "costeo_importacion_productos"

    id = db.Column(db.Integer, primary_key=True)
    costeo_id = db.Column(db.Integer, db.ForeignKey("costeo_importaciones.id"), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0)

    # --- Datos manuales (equivalentes a las columnas C:H de la planilla) ---
    producto = db.Column(db.String(200), nullable=True)
    codigo = db.Column(db.String(40), nullable=True)
    valor_unitario_tc = db.Column(db.Float, nullable=False, default=0)
    cantidad = db.Column(db.Float, nullable=False, default=0)
    unidad_tc = db.Column(db.String(6), nullable=False, default="USD")
    activo_fijo = db.Column(db.String(80), nullable=False, default="NO")
    tiene_ad_valorem = db.Column(db.String(3), nullable=False, default="SI")
    # Monto de ad valorem escrito a mano. Si viene vacío se calcula como
    # CIF x tasa; sirve para cuando la DIN trae un monto distinto al teórico.
    ad_valorem_manual_clp = db.Column(db.Integer, nullable=True)

    # --- Prorrateo calculado por recalcular() (columnas I:U de la planilla) ---
    exw_moneda = db.Column(db.Float, nullable=False, default=0)
    porcentaje = db.Column(db.Float, nullable=False, default=0)
    exw_clp = db.Column(db.Integer, nullable=False, default=0)
    crating_clp = db.Column(db.Integer, nullable=False, default=0)
    flete_clp = db.Column(db.Integer, nullable=False, default=0)
    seguro_clp = db.Column(db.Integer, nullable=False, default=0)
    cif_clp = db.Column(db.Integer, nullable=False, default=0)
    ad_valorem_clp = db.Column(db.Integer, nullable=False, default=0)
    gastos_internos_clp = db.Column(db.Integer, nullable=False, default=0)
    costo_total_clp = db.Column(db.Integer, nullable=False, default=0)
    costo_unitario_inicial_clp = db.Column(db.Integer, nullable=False, default=0)
    costo_unitario_final_clp = db.Column(db.Integer, nullable=False, default=0)
    impacto_pct = db.Column(db.Float, nullable=False, default=0)

    costeo = db.relationship("CosteoImportacion", back_populates="productos")

    def __repr__(self):
        return f"<CosteoImportacionProducto {self.producto}>"
