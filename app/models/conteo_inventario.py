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
    categoria = db.Column(db.String(120), nullable=True)
    cantidad_qms = db.Column(db.Integer, default=0, nullable=False)
    cantidad_defontana = db.Column(db.Integer, default=0, nullable=False)
    cantidad_fisica = db.Column(db.Integer, nullable=True)
    # Costo unitario y unidad de medida según cada sistema (para el ajuste de inventario)
    costo_unitario_qms = db.Column(db.Integer, nullable=True)
    costo_unitario_defontana = db.Column(db.Integer, nullable=True)
    unidad_qms = db.Column(db.String(20), nullable=True)
    unidad_defontana = db.Column(db.String(20), nullable=True)
    contado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    contado_en = db.Column(db.DateTime, nullable=True)
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    contado_por = db.relationship("Usuario")

    @property
    def contado(self) -> bool:
        return self.cantidad_fisica is not None

    @property
    def diferencia_sistemas(self) -> int:
        """QMS - Defontana. Distinto de 0 significa que los dos sistemas no cuadran entre sí."""
        return self.cantidad_qms - self.cantidad_defontana

    @property
    def diferencia_fisica_qms(self):
        """Físico contado menos lo que dice QMS. None si aún no se ha contado."""
        if not self.contado:
            return None
        return self.cantidad_fisica - self.cantidad_qms

    @property
    def diferencia_fisica_defontana(self):
        """Físico contado menos lo que dice Defontana. None si aún no se ha contado."""
        if not self.contado:
            return None
        return self.cantidad_fisica - self.cantidad_defontana

    # --- Valorización: mismo stock, distinto costo según el sistema ---

    @property
    def costo_referencia(self):
        """Costo unitario a usar cuando se necesita uno solo: QMS manda, Defontana suple."""
        if self.costo_unitario_qms:
            return self.costo_unitario_qms
        return self.costo_unitario_defontana

    @property
    def valor_qms(self) -> int:
        return (self.cantidad_qms or 0) * (self.costo_unitario_qms or 0)

    @property
    def valor_defontana(self) -> int:
        costo = self.costo_unitario_defontana
        if costo is None:
            costo = self.costo_unitario_qms or 0
        return (self.cantidad_defontana or 0) * costo

    @property
    def valor_fisico(self):
        """Valorización del conteo físico al costo de referencia. None si no se ha contado."""
        if not self.contado:
            return None
        return self.cantidad_fisica * (self.costo_referencia or 0)

    @property
    def diferencia_costo_unitario(self):
        """Costo unitario QMS menos Defontana. None si falta el dato en alguno de los dos."""
        if self.costo_unitario_qms is None or self.costo_unitario_defontana is None:
            return None
        return self.costo_unitario_qms - self.costo_unitario_defontana

    @property
    def tiene_diferencia_costo(self) -> bool:
        diferencia = self.diferencia_costo_unitario
        return diferencia is not None and diferencia != 0

    @property
    def diferencia_valor_sistemas(self) -> int:
        """Cuánto dinero explica el descuadre entre ambos sistemas."""
        return self.valor_qms - self.valor_defontana

    @property
    def diferencia_valor_fisico(self):
        """Valor del ajuste contra QMS: (físico - QMS) x costo de referencia."""
        if not self.contado:
            return None
        return (self.cantidad_fisica - (self.cantidad_qms or 0)) * (self.costo_referencia or 0)

    @property
    def diferencia_valor_fisico_defontana(self):
        if not self.contado:
            return None
        return (self.cantidad_fisica - (self.cantidad_defontana or 0)) * (self.costo_referencia or 0)

    @property
    def desviacion_costo_pct(self):
        """Cuánto se desvía el costo de QMS respecto al de Defontana, en porcentaje.

        Se mide contra Defontana; si ahí el costo es 0 no hay base de comparación.
        """
        diferencia = self.diferencia_costo_unitario
        if diferencia is None or not self.costo_unitario_defontana:
            return None
        return diferencia / self.costo_unitario_defontana * 100

    @property
    def impacto_diferencia_costo(self):
        """Cuánto dinero explica la diferencia de costo sobre el stock declarado.

        Es la plata que se gana o se pierde en la valorización según qué sistema
        se tome como bueno, así se puede priorizar qué SKU corregir primero.
        """
        diferencia = self.diferencia_costo_unitario
        if diferencia is None:
            return None
        return diferencia * (self.cantidad_qms or 0)

    @property
    def par_de_unidades(self):
        """'RL → UN' cuando las unidades no coinciden; None si están bien."""
        if self.unidades_coinciden:
            return None
        return f"{self.unidad_qms} → {self.unidad_defontana}"

    @property
    def estado_maestro(self) -> str:
        """Clasifica al SKU según la consistencia de sus datos entre sistemas."""
        if not self.tiene_costo:
            return "sin_costo"
        unidad_mal = not self.unidades_coinciden
        costo_mal = self.tiene_diferencia_costo
        if unidad_mal and costo_mal:
            return "ambas"
        if unidad_mal:
            return "dif_unidad"
        if costo_mal:
            return "dif_costo"
        return "ok"

    @property
    def unidades_coinciden(self) -> bool:
        """False sólo si ambos sistemas declaran unidad y no es la misma."""
        if not self.unidad_qms or not self.unidad_defontana:
            return True
        return self.unidad_qms.strip().upper() == self.unidad_defontana.strip().upper()

    @property
    def tiene_costo(self) -> bool:
        return bool(self.costo_unitario_qms or self.costo_unitario_defontana)

    @property
    def tiene_diferencia(self) -> bool:
        if self.diferencia_sistemas != 0:
            return True
        if self.contado and (self.diferencia_fisica_qms != 0 or self.diferencia_fisica_defontana != 0):
            return True
        return False

    def __repr__(self):
        return f"<ItemConteoInventario {self.codigo}>"
