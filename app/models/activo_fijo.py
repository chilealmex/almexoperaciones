from datetime import date, datetime, timezone

from app.extensions import db


class CategoriaActivo(db.Model):
    """Tipos de categoría de activo fijo, parametrizables desde el submódulo Categorías."""

    __tablename__ = "categorias_activo"
    __table_args__ = (db.UniqueConstraint("empresa_id", "nombre", name="uq_categoria_activo_nombre"),)

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    nombre = db.Column(db.String(80), nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)
    activa = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<CategoriaActivo {self.nombre}>"


class ActivoFijo(db.Model):
    __tablename__ = "activos_fijos"

    ESTADOS = ("activo", "en_mantenimiento", "dado_de_baja", "vendido")

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    codigo_activo = db.Column(db.String(30), unique=True, nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)
    categoria = db.Column(db.String(80), nullable=True)
    fecha_compra = db.Column(db.Date, nullable=False)
    valor_compra = db.Column(db.Integer, nullable=False)  # CLP
    valor_residual = db.Column(db.Integer, default=0, nullable=False)
    vida_util_meses = db.Column(db.Integer, nullable=False)
    ubicacion = db.Column(db.String(150), nullable=True)
    responsable_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedores.id"), nullable=True)
    numero_factura_compra = db.Column(db.String(50), nullable=True)
    estado = db.Column(db.String(20), default="activo", nullable=False)
    fecha_baja = db.Column(db.Date, nullable=True)
    motivo_baja = db.Column(db.String(255), nullable=True)
    es_arrendable = db.Column(db.Boolean, default=False, nullable=False)
    creado_en = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    responsable = db.relationship("Usuario")
    proveedor = db.relationship("Proveedor")
    arriendos_salida = db.relationship("ArriendoSalida", back_populates="activo_fijo")

    @property
    def meses_transcurridos(self) -> int:
        hoy = date.today()
        return max(
            0,
            (hoy.year - self.fecha_compra.year) * 12
            + (hoy.month - self.fecha_compra.month),
        )

    @property
    def valor_libro(self) -> int:
        if self.vida_util_meses <= 0:
            return self.valor_compra
        depreciable = self.valor_compra - self.valor_residual
        meses = min(self.meses_transcurridos, self.vida_util_meses)
        depreciacion_acumulada = depreciable * meses / self.vida_util_meses
        return max(self.valor_residual, round(self.valor_compra - depreciacion_acumulada))

    @property
    def arrendado_actualmente(self) -> bool:
        return any(a.fecha_devolucion_real is None for a in self.arriendos_salida)

    @property
    def depreciacion_mensual(self) -> int:
        """Cuota de depreciación lineal del mes, 0 si ya se depreció por completo o vida útil inválida."""
        if self.vida_util_meses <= 0 or self.meses_transcurridos >= self.vida_util_meses:
            return 0
        return round((self.valor_compra - self.valor_residual) / self.vida_util_meses)

    @property
    def centro_costo(self) -> str:
        """Centro al que se imputa la depreciación: 'Arriendo' si está arrendado hoy, si no 'Administración'."""
        return "Arriendo" if self.arrendado_actualmente else "Administración"

    def __repr__(self):
        return f"<ActivoFijo {self.codigo_activo}>"
