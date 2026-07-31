from app.extensions import db

ESTADOS_IMPORTACION = (("pendiente", "Pendiente"), ("costeando", "Costeando"), ("cerrado", "Cerrado"))
TIPOS_SALDO = (("a_favor", "A favor"), ("en_contra", "En contra"))
TRATADOS_TLC = (("SI", "Sí"), ("NO", "No"), ("PARCIAL", "Parcial"))
ESTADOS_DIN = (("pendiente", "Pendiente"), ("revision", "Revisión"), ("pagado", "Pagado"))


class ProveedorImportacion(db.Model):
    """Proveedor extranjero del catálogo usado para armar las importaciones."""

    __tablename__ = "proveedores_importacion"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    rut = db.Column(db.String(20), nullable=True)
    nombre = db.Column(db.String(150), nullable=False)
    pais = db.Column(db.String(80), nullable=True)
    tratado_tlc = db.Column(db.String(10), nullable=True)
    creado_en = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f"<ProveedorImportacion {self.nombre}>"


class Importacion(db.Model):
    """Una importación (PEI): datos generales y el resumen de su costeo."""

    __tablename__ = "importaciones"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)

    fecha_pei = db.Column(db.Date, nullable=True)
    pei = db.Column(db.String(30), nullable=True)
    imp = db.Column(db.String(30), nullable=True)
    proveedor_nombre = db.Column(db.String(150), nullable=True)
    oc = db.Column(db.String(30), nullable=True)
    monto = db.Column(db.Integer, nullable=False, default=0)  # monto guía, CLP
    agencia = db.Column(db.String(100), nullable=True)
    tipo_saldo = db.Column(db.String(12), nullable=False, default="a_favor")
    saldo_agencia = db.Column(db.Integer, nullable=False, default=0)
    pais = db.Column(db.String(80), nullable=True)
    tratado_tlc = db.Column(db.String(10), nullable=True)
    notas = db.Column(db.Text, nullable=True)
    estado = db.Column(db.String(15), nullable=False, default="pendiente")

    # Resumen de costeo, recalculado por app.utils.importaciones_calculo.recalcular()
    costeo_valor = db.Column(db.Integer, nullable=False, default=0)
    costeo_suma = db.Column(db.Integer, nullable=False, default=0)
    costeo_diferencia = db.Column(db.Integer, nullable=False, default=0)

    creado_en = db.Column(db.DateTime, server_default=db.func.now())
    actualizado_en = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    lineas = db.relationship(
        "ImportacionAsientoLinea",
        back_populates="importacion",
        cascade="all, delete-orphan",
        order_by="ImportacionAsientoLinea.orden",
    )
    grupos_meta = db.relationship(
        "ImportacionGrupoMeta", back_populates="importacion", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Importacion PEI {self.pei}>"

    def lineas_de(self, tipo):
        return [linea for linea in self.lineas if linea.tipo == tipo]

    def linea_por_rol(self, tipo, rol):
        return next((linea for linea in self.lineas if linea.tipo == tipo and linea.rol == rol), None)

    def meta_de(self, tipo):
        return next((grupo for grupo in self.grupos_meta if grupo.tipo == tipo), None)

    @property
    def saldo_signado(self):
        signo = -1 if self.tipo_saldo == "en_contra" else 1
        return (self.saldo_agencia or 0) * signo


class ImportacionAsientoLinea(db.Model):
    """Una línea (cuenta contable) dentro de uno de los seis grupos de asientos de una importación."""

    __tablename__ = "importacion_asiento_lineas"

    id = db.Column(db.Integer, primary_key=True)
    importacion_id = db.Column(db.Integer, db.ForeignKey("importaciones.id"), nullable=False)
    tipo = db.Column(db.String(25), nullable=False)
    rol = db.Column(db.String(40), nullable=True)
    orden = db.Column(db.Integer, nullable=False, default=0)

    proveedor = db.Column(db.String(150), nullable=True)
    fecha = db.Column(db.Date, nullable=True)
    tipo_doc = db.Column(db.String(30), nullable=True)
    n_doc = db.Column(db.String(30), nullable=True)
    cuenta = db.Column(db.String(120), nullable=True)
    debe = db.Column(db.Integer, nullable=False, default=0)
    haber = db.Column(db.Integer, nullable=False, default=0)
    ecomex = db.Column(db.Integer, nullable=True)
    dif = db.Column(db.Integer, nullable=True)
    descripcion = db.Column(db.String(150), nullable=True)
    cbte_linea = db.Column(db.String(30), nullable=True)
    n_cuenta = db.Column(db.String(30), nullable=True)

    importacion = db.relationship("Importacion", back_populates="lineas")

    def __repr__(self):
        return f"<ImportacionAsientoLinea {self.tipo}/{self.rol}>"


class ImportacionGrupoMeta(db.Model):
    """Datos de cabecera de cada grupo de asientos (comprobante, saldo, tipo de cambio)."""

    __tablename__ = "importacion_grupo_meta"
    __table_args__ = (db.UniqueConstraint("importacion_id", "tipo", name="uq_importacion_grupo_meta"),)

    id = db.Column(db.Integer, primary_key=True)
    importacion_id = db.Column(db.Integer, db.ForeignKey("importaciones.id"), nullable=False)
    tipo = db.Column(db.String(25), nullable=False)

    cbte = db.Column(db.String(30), nullable=True)
    saldo_anterior_monto = db.Column(db.Integer, nullable=False, default=0)
    saldo_nuevo_tipo = db.Column(db.String(12), nullable=False, default="a_favor")
    saldo_nuevo_cuenta = db.Column(db.String(120), nullable=True)
    saldo_nuevo_monto = db.Column(db.Integer, nullable=False, default=0)
    monto_usd = db.Column(db.Float, nullable=False, default=0)
    tipo_cambio = db.Column(db.Float, nullable=False, default=0)
    proveedor = db.Column(db.String(150), nullable=True)
    fecha = db.Column(db.Date, nullable=True)
    tipo_doc = db.Column(db.String(30), nullable=True)
    n_doc = db.Column(db.String(30), nullable=True)

    importacion = db.relationship("Importacion", back_populates="grupos_meta")

    def __repr__(self):
        return f"<ImportacionGrupoMeta {self.tipo}>"


class DinRegistro(db.Model):
    """Control de pagos de Declaraciones de Ingreso (DIN) por agencia."""

    __tablename__ = "din_registros"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)

    numero = db.Column(db.String(30), nullable=True)
    oc = db.Column(db.String(30), nullable=True)
    agencia = db.Column(db.String(100), nullable=True)
    n_doc_agencia = db.Column(db.String(30), nullable=True)
    monto_doc_agencia = db.Column(db.Integer, nullable=False, default=0)
    proveedor = db.Column(db.String(150), nullable=True)
    n_invoice = db.Column(db.String(40), nullable=True)
    estado = db.Column(db.String(15), nullable=False, default="pendiente")
    rut = db.Column(db.String(20), nullable=True)
    razon_social = db.Column(db.String(150), nullable=True)
    formulario = db.Column(db.String(10), nullable=True)
    folio = db.Column(db.String(30), nullable=True)
    fecha_pago = db.Column(db.Date, nullable=True)
    vcto = db.Column(db.Date, nullable=True)
    advalorem = db.Column(db.Integer, nullable=False, default=0)
    total_pagado = db.Column(db.Integer, nullable=False, default=0)
    creado_en = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f"<DinRegistro {self.numero}>"
