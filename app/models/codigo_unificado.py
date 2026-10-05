"""Códigos que se retiraron al unir dos líneas del mismo artículo.

Unificar dos líneas borraba una y no dejaba rastro. El importador reconoce al
artículo por su código, así que en cuanto la planilla volvía a traer el código
retirado —y lo trae todos los meses, porque quien exporta no cambió nada— la
línea se creaba de nuevo y el duplicado reaparecía solo. Había que rehacer el
mismo trabajo en cada carga.

Esto guarda hacia dónde apunta cada código retirado. Los dos importadores lo
consultan antes de buscar el artículo, así que se unifica una vez y la unión
queda.

Es lo mismo que hace [EquivalenciaCodigo] para las parejas entre QMS y
Defontana, pero esa tabla responde otra pregunta: allí los dos códigos siguen
vivos, uno en cada sistema, y la pantalla los muestra como pareja confirmada.
Acá uno de los dos dejó de existir en el maestro. Mezclarlas llenaría la lista
de parejas confirmadas con filas que no son parejas de nada.
"""

from datetime import datetime, timezone

from app.extensions import db
from app.utils.codigos import codigo_normalizado


class CodigoUnificado(db.Model):
    """Un código que ya no tiene línea propia: su artículo es otro."""

    __tablename__ = "codigos_unificados"
    __table_args__ = (
        # Un código retirado no puede apuntar a dos artículos distintos.
        db.UniqueConstraint(
            "empresa_id", "clave_retirada", name="uq_codigo_unificado_retirada"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False, index=True)

    # Tal como los escribe cada planilla: es lo que se muestra en pantalla.
    codigo_retirado = db.Column(db.String(80), nullable=False)
    codigo_vigente = db.Column(db.String(80), nullable=False)
    # Por acá buscan los importadores, con la misma función que usan para cruzar.
    clave_retirada = db.Column(db.String(80), nullable=False, index=True)
    clave_vigente = db.Column(db.String(80), nullable=False, index=True)

    creado_en = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    creado_por = db.relationship("Usuario")

    def __repr__(self):
        return f"<CodigoUnificado {self.codigo_retirado} -> {self.codigo_vigente}>"


def registrar_unificacion(empresa_id, codigo_vigente, codigo_retirado, usuario_id=None):
    """Deja guardado que 'codigo_retirado' ya no tiene línea propia.

    Si ese código ya estaba apuntando a otro lado, se repunta: la unión más
    reciente es la que vale. Devuelve el registro, o None si los dos códigos
    son el mismo para el importador y no hay nada que redirigir.
    """
    clave_vigente = codigo_normalizado(codigo_vigente)
    clave_retirada = codigo_normalizado(codigo_retirado)
    if not clave_vigente or not clave_retirada or clave_vigente == clave_retirada:
        return None

    registro = CodigoUnificado.query.filter_by(
        empresa_id=empresa_id, clave_retirada=clave_retirada
    ).first()
    if registro is None:
        registro = CodigoUnificado(
            empresa_id=empresa_id,
            codigo_retirado=str(codigo_retirado)[:80],
            clave_retirada=clave_retirada[:80],
            creado_por_id=usuario_id,
        )
        db.session.add(registro)
    registro.codigo_vigente = str(codigo_vigente)[:80]
    registro.clave_vigente = clave_vigente[:80]

    # Lo que apuntaba al código que se acaba de retirar tiene que seguirlo
    # hasta el nuevo destino. Sin esto quedaría una cadena A->B->C, y los
    # importadores resuelven un solo salto: A se volvería a crear.
    for anterior in CodigoUnificado.query.filter_by(
        empresa_id=empresa_id, clave_vigente=clave_retirada
    ).all():
        if anterior.id != registro.id:
            anterior.codigo_vigente = registro.codigo_vigente
            anterior.clave_vigente = registro.clave_vigente
    return registro


def redirecciones(empresa_id) -> dict:
    """{clave retirada: clave vigente}, para que los importadores no la recreen."""
    return {
        u.clave_retirada: u.clave_vigente
        for u in CodigoUnificado.query.filter_by(empresa_id=empresa_id).all()
    }
