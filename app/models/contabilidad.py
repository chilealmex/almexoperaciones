from app.extensions import db
from app.utils.provision_ingresos_excel import MESES_NOMBRES


class ProvisionIngreso(db.Model):
    """Una línea de la planilla "Provisión de Ingresos" (hoja Control).

    Los datos llegan importando el Excel y se van acumulando: cada importación
    agrega las líneas nuevas y deja intactas las que ya estaban, para no pisar
    lo que se editó a mano. La línea se reconoce por mes, comprobante de
    provisión y OT, que en la planilla no se repiten.

    Lo que se edita desde la aplicación son las reversas, que viven aparte
    porque son varias (ver ReversaProvision), y el comprobante de provisión y
    la OT cuando vienen mal escritos. El resto viene del Excel.
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
    saldo = db.Column(db.Integer, nullable=False, default=0)

    creado_en = db.Column(db.DateTime, server_default=db.func.now())
    actualizado_en = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    reversas = db.relationship(
        "ReversaProvision",
        back_populates="provision",
        cascade="all, delete-orphan",
        order_by="ReversaProvision.mes",
    )

    @property
    def reversado(self) -> int:
        """Todo lo reversado hasta ahora. Es la suma, no la última."""
        return sum(r.monto or 0 for r in self.reversas)

    @property
    def saldo_actual(self) -> int:
        """Lo que queda por reversar: la provisión menos todo lo reversado."""
        return (self.monto_provision or 0) - self.reversado

    @property
    def reversado_de_mas(self) -> int:
        """Cuánto se pasó, si se reversó más de lo provisionado. 0 si no.

        En la planilla de la que salió esto hay líneas así, y son errores de la
        planilla, no un caso del negocio. El sistema no lo impide —puede ser un
        monto mal tecleado que se corrige con la reversa siguiente— pero lo
        muestra en rojo en vez de dejarlo pasar: que una planilla no avise es
        justamente lo que hace que el error llegue lejos.
        """
        return max(0, self.reversado - (self.monto_provision or 0))

    @property
    def meses_reversados(self) -> list:
        """Los meses en que se reversó, una sola vez cada uno y en orden."""
        return sorted({r.mes for r in self.reversas if r.mes})

    def __repr__(self):
        return f"<ProvisionIngreso {self.cbte_prov}/{self.ot}>"


class ReversaProvision(db.Model):
    """Cada reversa de una provisión: cuánto, en qué mes y con qué comprobante.

    Antes era una sola por línea, con el mes guardado como texto justamente
    porque no alcanzaba: cuando la reversa se partía en varios meses había que
    escribir "may-26 y jun-26" en una casilla, y entonces el monto de cada mes
    ya no se sabía y el saldo quedaba a ojo.

    Son varias, y el saldo es la provisión menos la suma. Eso es lo que permite
    verlas como las ve el área de contabilidad: una columna por mes, el monto
    en la celda que corresponde y el total a la derecha.
    """

    __tablename__ = "reversas_provision"

    id = db.Column(db.Integer, primary_key=True)
    provision_id = db.Column(
        db.Integer, db.ForeignKey("provisiones_ingreso.id"), nullable=False, index=True
    )

    monto = db.Column(db.Integer, nullable=False, default=0)
    # Texto y no fecha, igual que antes: lo que ya está cargado viene escrito
    # de varias formas ("09.2026", "may-26") y convertirlo perdería lo que no
    # calce. La pantalla lo normaliza al escribirlo nuevo.
    mes = db.Column(db.String(60), nullable=True)
    comprobante = db.Column(db.String(60), nullable=True)
    # Por qué este monto quedó así. Es el respaldo cuando lo que llegó de
    # contabilidad viene equivocado: en una planilla eso se discute de
    # memoria, acá queda escrito al lado de la cifra que se discute.
    nota = db.Column(db.Text, nullable=True)

    creado_en = db.Column(db.DateTime, server_default=db.func.now())
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    provision = db.relationship("ProvisionIngreso", back_populates="reversas")
    creado_por = db.relationship("Usuario")

    def __repr__(self):
        return f"<ReversaProvision {self.mes} {self.monto}>"


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
    # Tipo de cambio de respaldo, para las líneas cuya moneda no esté en la
    # tabla del período. La tabla (tipos_cambio) es la que manda.
    tipo_cambio = db.Column(db.Float, nullable=False, default=0)
    estado = db.Column(db.String(15), nullable=False, default="en_proceso")
    notas = db.Column(db.String(255), nullable=True)

    creado_en = db.Column(db.DateTime, server_default=db.func.now())
    actualizado_en = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    lineas = db.relationship(
        "LineaDifTc", back_populates="periodo", cascade="all, delete-orphan",
        order_by="LineaDifTc.orden",
    )
    tipos_cambio = db.relationship(
        "TipoCambioDifTc", back_populates="periodo", cascade="all, delete-orphan",
        order_by="TipoCambioDifTc.moneda",
    )

    def tipo_cambio_de(self, moneda):
        """El tipo de cambio de esa moneda en este mes, o el de respaldo si no está."""
        clave = (moneda or "").strip().upper()
        for tc in self.tipos_cambio:
            if tc.moneda == clave:
                return tc.valor
        return self.tipo_cambio or 0

    def __repr__(self):
        return f"<PeriodoDifTc {self.mes:02d}.{self.anio}>"


class TipoCambioDifTc(db.Model):
    """Una fila de la tabla de tipos de cambio del mes (Moneda y Tipo de Cambio).

    En la planilla es el bloque amarillo AC:AD, y la columna "Valor en $" lo
    consulta con un VLOOKUP según la moneda de cada línea.
    """

    __tablename__ = "tipos_cambio_dif_tc"
    __table_args__ = (
        db.UniqueConstraint("periodo_id", "moneda", name="uq_tipo_cambio_dif_tc_moneda"),
    )

    id = db.Column(db.Integer, primary_key=True)
    periodo_id = db.Column(db.Integer, db.ForeignKey("periodos_dif_tc.id"), nullable=False, index=True)
    moneda = db.Column(db.String(10), nullable=False)
    valor = db.Column(db.Float, nullable=False, default=0)

    periodo = db.relationship("PeriodoDifTc", back_populates="tipos_cambio")

    def __repr__(self):
        return f"<TipoCambioDifTc {self.moneda}={self.valor}>"


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

    # --- Columnas amarillas: se escriben a mano ---
    # La moneda de la línea decide qué tipo de cambio se le aplica.
    tipo_moneda = db.Column(db.String(10), nullable=True)
    mon_orig = db.Column(db.Float, nullable=True)

    # --- Calculadas con el tipo de cambio del período ---
    valor_clp = db.Column(db.BigInteger, nullable=False, default=0)
    dif_cambio = db.Column(db.BigInteger, nullable=False, default=0)
    pct_variacion = db.Column(db.Float, nullable=False, default=0)

    periodo = db.relationship("PeriodoDifTc", back_populates="lineas")

    def __repr__(self):
        return f"<LineaDifTc {self.cuenta}/{self.numero_doc}>"


class ConciliacionSii(db.Model):
    """Un mes de conciliación entre el RCV del SII y los libros de Defontana.

    El período agrupa los dos libros —compras y ventas—, que se cargan por
    separado: es normal tener listo el de compras y estar esperando el de
    ventas, y no tiene sentido bloquear uno por el otro.

    Un mes ya revisado se cierra. Cerrarlo lo deja de solo lectura: el mes se
    carga eligiendo su año y mes a mano, y equivocarse en esa lista reemplazaba
    en silencio un mes que ya estaba conciliado.
    """

    __tablename__ = "conciliaciones_sii"
    __table_args__ = (
        db.UniqueConstraint("empresa_id", "anio", "mes", name="uq_conciliacion_sii_mes"),
    )

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    anio = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)

    estado = db.Column(
        db.String(20), nullable=False, default="abierto", server_default="abierto"
    )
    cerrado_en = db.Column(db.DateTime, nullable=True)
    cerrado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    creado_en = db.Column(db.DateTime, server_default=db.func.now())
    actualizado_en = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    libros = db.relationship(
        "ConciliacionSiiLibro", back_populates="conciliacion",
        cascade="all, delete-orphan", order_by="ConciliacionSiiLibro.libro",
    )
    cerrado_por = db.relationship("Usuario")

    @property
    def cerrado(self) -> bool:
        return self.estado == "cerrado"

    def libro_por_clave(self, clave):
        return next((l for l in self.libros if l.libro == clave), None)

    @property
    def compras(self):
        return self.libro_por_clave("compra")

    @property
    def ventas(self):
        return self.libro_por_clave("venta")

    def __repr__(self):
        return f"<ConciliacionSii {self.anio}-{self.mes:02d}>"


class ConciliacionSiiLibro(db.Model):
    """El cruce de un libro (compras o ventas) dentro de un período.

    Guarda los totales y los conteos ya calculados además del detalle. Sin eso,
    el listado de períodos tendría que recorrer todos los documentos de todos
    los meses para pintar una tabla de resumen.
    """

    __tablename__ = "conciliacion_sii_libros"
    __table_args__ = (
        db.UniqueConstraint("conciliacion_id", "libro", name="uq_conciliacion_sii_libro"),
    )

    LIBROS = (("compra", "Compras"), ("venta", "Ventas"))

    id = db.Column(db.Integer, primary_key=True)
    conciliacion_id = db.Column(
        db.Integer, db.ForeignKey("conciliaciones_sii.id"), nullable=False, index=True
    )
    libro = db.Column(db.String(10), nullable=False)

    archivo_sii = db.Column(db.String(255), nullable=True)
    archivo_defontana = db.Column(db.String(255), nullable=True)
    cargado_en = db.Column(db.DateTime, server_default=db.func.now())
    cargado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    # Cuántas veces se recargó el mismo libro: la conciliación se rehace varias
    # veces en el mes a medida que se van corrigiendo los asientos.
    cargas = db.Column(db.Integer, nullable=False, default=1)

    n_coincide = db.Column(db.Integer, nullable=False, default=0)
    n_solo_sii = db.Column(db.Integer, nullable=False, default=0)
    n_solo_defontana = db.Column(db.Integer, nullable=False, default=0)
    n_dif_monto = db.Column(db.Integer, nullable=False, default=0)
    # Cuadra la plata pero el RUT o la razón social no coinciden.
    n_dif_datos = db.Column(db.Integer, nullable=False, default=0)
    # Diferencias revisadas y dadas por buenas (impuesto específico y similares).
    n_aceptados = db.Column(db.Integer, nullable=False, default=0)
    # Documentos que quedaron contabilizados en otro mes: están, pero en otro
    # libro. No se cuentan dos veces con los aceptados.
    n_otro_mes = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    # BigInteger: son sumas de todo un mes de facturación en pesos.
    neto_sii = db.Column(db.BigInteger, nullable=False, default=0)
    neto_defontana = db.Column(db.BigInteger, nullable=False, default=0)
    exento_sii = db.Column(db.BigInteger, nullable=False, default=0)
    exento_defontana = db.Column(db.BigInteger, nullable=False, default=0)
    iva_sii = db.Column(db.BigInteger, nullable=False, default=0)
    iva_defontana = db.Column(db.BigInteger, nullable=False, default=0)
    total_sii = db.Column(db.BigInteger, nullable=False, default=0)
    total_defontana = db.Column(db.BigInteger, nullable=False, default=0)

    conciliacion = db.relationship("ConciliacionSii", back_populates="libros")
    cargado_por = db.relationship("Usuario")
    documentos = db.relationship(
        "ConciliacionSiiDocumento", back_populates="libro_ref",
        cascade="all, delete-orphan",
    )

    @property
    def etiqueta(self) -> str:
        return dict(self.LIBROS).get(self.libro, self.libro)

    @property
    def diferencia(self) -> int:
        return (self.total_sii or 0) - (self.total_defontana or 0)

    @property
    def pendientes(self) -> int:
        """Documentos que todavía exigen trabajo.

        Los que no cuadran, menos los que alguien ya revisó y dio por buenos
        —una factura de combustible con impuesto específico descuadra siempre, y
        seguir contándola haría que el mes nunca llegue a cero— y menos los que
        quedaron contabilizados en otro mes, que están pero en otro libro.
        """
        sin_cuadrar = ((self.n_solo_sii or 0) + (self.n_solo_defontana or 0)
                       + (self.n_dif_monto or 0) + (self.n_dif_datos or 0))
        return max(0, sin_cuadrar - (self.n_aceptados or 0) - (self.n_otro_mes or 0))

    @property
    def cuadra(self) -> bool:
        return self.pendientes == 0

    def __repr__(self):
        return f"<ConciliacionSiiLibro {self.libro} #{self.conciliacion_id}>"


class ConciliacionSiiDocumento(db.Model):
    """Un documento del cruce, con lo que dice cada sistema lado a lado.

    Se guardan las dos versiones completas —no sólo la diferencia— porque para
    corregir un asiento hay que ver qué puso cada uno en cada columna.
    """

    __tablename__ = "conciliacion_sii_documentos"

    id = db.Column(db.Integer, primary_key=True)
    libro_id = db.Column(
        db.Integer, db.ForeignKey("conciliacion_sii_libros.id"), nullable=False, index=True
    )

    tipo_doc = db.Column(db.String(10), nullable=False)
    tipo_doc_desc = db.Column(db.String(60), nullable=True)
    folio = db.Column(db.String(40), nullable=False)
    # Texto y no fecha: cada sistema la escribe a su manera y aquí sólo se
    # muestra; convertirla obligaría a descartar documentos por un formato raro.
    fecha = db.Column(db.String(20), nullable=True)

    rut_sii = db.Column(db.String(20), nullable=True)
    contraparte_sii = db.Column(db.String(200), nullable=True)
    rut_defontana = db.Column(db.String(20), nullable=True)
    contraparte_defontana = db.Column(db.String(200), nullable=True)

    neto_sii = db.Column(db.BigInteger, nullable=False, default=0)
    neto_defontana = db.Column(db.BigInteger, nullable=False, default=0)
    exento_sii = db.Column(db.BigInteger, nullable=False, default=0)
    exento_defontana = db.Column(db.BigInteger, nullable=False, default=0)
    iva_sii = db.Column(db.BigInteger, nullable=False, default=0)
    iva_defontana = db.Column(db.BigInteger, nullable=False, default=0)
    total_sii = db.Column(db.BigInteger, nullable=False, default=0)
    total_defontana = db.Column(db.BigInteger, nullable=False, default=0)
    # Una diferencia por columna, no sólo la del total: permite ver de un
    # vistazo si lo que baila es el neto, el exento o el IVA.
    dif_neto = db.Column(db.BigInteger, nullable=False, default=0)
    dif_exento = db.Column(db.BigInteger, nullable=False, default=0)
    dif_iva = db.Column(db.BigInteger, nullable=False, default=0)
    diferencia = db.Column(db.BigInteger, nullable=False, default=0)

    estado = db.Column(db.String(20), nullable=False)
    # En qué se diferencian, ya escrito: "Neto: $100.000 vs $90.000 · IVA: ...".
    diferencia_descrita = db.Column(db.String(400), nullable=True)
    orden = db.Column(db.Integer, nullable=False, default=0)

    # Diferencia revisada y dada por buena. Hay descuadres que son correctos:
    # las facturas de combustible llevan impuesto específico, que el SII y
    # Defontana no reparten igual entre neto e impuestos. Marcarlas saca el
    # documento de lo pendiente sin ocultarlo ni alterar los montos.
    aceptado = db.Column(db.Boolean, nullable=False, default=False)
    motivo_aceptacion = db.Column(db.String(200), nullable=True)
    aceptado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    aceptado_en = db.Column(db.DateTime, nullable=True)

    # En qué mes quedó contabilizado el documento, cuando no es el del período.
    # En Defontana el libro lo decide la "fecha contable", que es otro campo que
    # la fecha del documento: una factura de octubre con fecha contable de
    # noviembre queda en el libro de noviembre, y al revés. Cuando esa fecha
    # queda en el mes equivocado, el documento aparece en un período y falta en
    # el otro, sin que ninguno de los dos sistemas esté mal. Anotarlo explica
    # la fila sin tocar montos y la saca de lo pendiente.
    #
    # Se guarda como "AAAA-MM": es un mes, no un día, y así se ordena solo.
    mes_contable = db.Column(db.String(7), nullable=True)
    mes_contable_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    mes_contable_en = db.Column(db.DateTime, nullable=True)

    libro_ref = db.relationship("ConciliacionSiiLibro", back_populates="documentos")
    # Dos caminos distintos a la misma tabla de usuarios —quien aceptó la
    # diferencia y quien anotó el mes contable—, así que hay que decir cuál es
    # cuál o SQLAlchemy no sabe por dónde unirlas.
    aceptado_por = db.relationship("Usuario", foreign_keys=[aceptado_por_id])
    mes_contable_por = db.relationship("Usuario", foreign_keys=[mes_contable_por_id])

    @property
    def llave(self):
        """Identifica al documento entre recargas del mismo libro."""
        return (self.tipo_doc, self.folio)

    @property
    def mes_contable_texto(self) -> str:
        """El mes anotado, escrito como se lee: "octubre 2025"."""
        if not self.mes_contable:
            return ""
        try:
            anio, mes = self.mes_contable.split("-")
            return f"{MESES_NOMBRES[int(mes) - 1]} {anio}"
        except (ValueError, IndexError):
            return self.mes_contable

    @property
    def resuelto(self) -> bool:
        """Si ya no hay nada que hacer con este documento en este período.

        O cuadra, o alguien revisó la diferencia y la dio por buena, o el
        documento quedó contabilizado en otro mes.
        """
        return self.estado == "coincide" or self.aceptado or bool(self.mes_contable)

    def __repr__(self):
        return f"<ConciliacionSiiDocumento {self.tipo_doc}/{self.folio} {self.estado}>"
