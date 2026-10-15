"""Órdenes de trabajo internas: el registro que vivía en una planilla.

Una OT interna es un trabajo que se encarga puertas adentro. Se llevaba en un
Excel de 909 líneas desde 2010, y ahí el número de OTI se repite: la misma
orden puede tener varios ítems —hasta 32 en un caso—, cada uno con su cantidad
y su descripción.

Eso es lo que decide que sean dos tablas y no una. Medido sobre esa planilla,
dentro de una misma OTI el cliente, la fecha, el estado, la sucursal y la línea
de negocio son siempre los mismos; lo único que cambia de una línea a otra es
la cantidad y la descripción. Guardarlo todo en una sola tabla obligaría a
repetir la cabecera en cada ítem y a corregirla en todas al cambiar el estado.
"""

from datetime import date, datetime, timezone

from app.extensions import db
from app.utils.cantidades import DECIMALES, PRECISION

CANTIDAD = db.Numeric(PRECISION, DECIMALES)


class OrdenTrabajoInterna(db.Model):
    """La cabecera: de qué trabajo se trata, para quién y en qué va."""

    __tablename__ = "ordenes_trabajo_internas"
    __table_args__ = (
        # El número es la identidad de la orden: repetirlo sería tener dos
        # órdenes distintas con el mismo nombre en boca de todos.
        db.UniqueConstraint("empresa_id", "numero", name="uq_oti_numero"),
    )

    # Los cuatro que usa la planilla. "NULA" es la que se emitió y no
    # corresponde: queda registrada —el número no se reutiliza— pero no cuenta
    # como trabajo pendiente ni como trabajo hecho.
    ESTADOS = ("ABIERTA", "DETENIDA", "CERRADA", "NULA")
    # El quinto no se elige al crear una orden: lo pone sólo la carga del
    # historial. 382 de las 909 líneas de la planilla no traen estado, todas
    # entre 2010 y 2022, porque esa columna se empezó a llenar después. Darlas
    # por abiertas inundaría la vista de pendientes; darlas por cerradas sería
    # afirmar que se hicieron. No se sabe, y eso es lo que dicen.
    SIN_ESTADO = "SIN ESTADO"
    TODOS_LOS_ESTADOS = ESTADOS + (SIN_ESTADO,)
    # Las que siguen vivas, y que son las que la pantalla muestra por defecto.
    PENDIENTES = ("ABIERTA", "DETENIDA")

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False, index=True)

    numero = db.Column(db.Integer, nullable=False, index=True)
    # La planilla la tenía partida en tres columnas (AÑO, MES, DÍA). Acá es una
    # fecha: así se ordena, se filtra y se compara con las otras dos.
    fecha = db.Column(db.Date, nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=True)
    fecha_termino = db.Column(db.Date, nullable=True)

    estado = db.Column(db.String(10), nullable=False, default="ABIERTA", index=True)

    # Quién encarga el trabajo (en la planilla, "CUSTOMER") y el cliente final.
    # Son dos cosas distintas: casi siempre encarga la propia empresa y el
    # cliente es la minera a la que termina llegando.
    customer = db.Column(db.String(120), nullable=True)
    cliente = db.Column(db.String(120), nullable=True)
    sucursal = db.Column(db.String(40), nullable=True)
    linea_negocio = db.Column(db.String(40), nullable=True)
    # El número con que la misma orden existe en QMS, para poder cruzarlas.
    ot_qms = db.Column(db.String(30), nullable=True)
    observaciones = db.Column(db.Text, nullable=True)

    creado_en = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    actualizado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    actualizado_por = db.relationship("Usuario", foreign_keys=[actualizado_por_id])
    items = db.relationship(
        "ItemOTI", back_populates="oti", cascade="all, delete-orphan", order_by="ItemOTI.id"
    )

    @property
    def pendiente(self) -> bool:
        return self.estado in self.PENDIENTES

    @property
    def dias_abierta(self):
        """Cuántos días lleva viva. None si ya se cerró o se anuló.

        Es lo que se mira para saber cuál se quedó atrás: una orden de hace
        ocho meses todavía abierta no se distingue de una de ayer mirando sólo
        la fecha.
        """
        if not self.pendiente or self.fecha is None:
            return None
        return (date.today() - self.fecha).days

    def __repr__(self):
        return f"<OTI {self.numero} {self.estado}>"


class ItemOTI(db.Model):
    """Cada cosa que la orden manda a hacer: una cantidad y qué es."""

    __tablename__ = "items_oti"

    id = db.Column(db.Integer, primary_key=True)
    oti_id = db.Column(
        db.Integer, db.ForeignKey("ordenes_trabajo_internas.id"), nullable=False, index=True
    )
    cantidad = db.Column(CANTIDAD, nullable=True)
    descripcion = db.Column(db.String(500), nullable=False)

    oti = db.relationship("OrdenTrabajoInterna", back_populates="items")

    def __repr__(self):
        return f"<ItemOTI {self.descripcion[:30]}>"


def siguiente_numero(empresa_id: int) -> int:
    """El número que le toca a la próxima orden.

    Sigue la numeración que ya existe en vez de empezar de cero: la planilla va
    del 100 al 822 sin un solo salto, y esa continuidad es lo que permite
    nombrar una orden por su número sin ambigüedad.
    """
    ultimo = (
        db.session.query(db.func.max(OrdenTrabajoInterna.numero))
        .filter(OrdenTrabajoInterna.empresa_id == empresa_id)
        .scalar()
    )
    return (ultimo or 0) + 1
