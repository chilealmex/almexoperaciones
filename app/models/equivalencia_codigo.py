"""Códigos distintos que son el mismo artículo en QMS y en Defontana.

El mismo artículo debería existir en los dos sistemas: en eso consiste el
cruce. Pero el código no siempre se creó igual en cada uno, y entonces el
cruce por código deja dos filas sueltas que nunca se encuentran.

Esto guarda las parejas ya confirmadas por alguien. Es una tabla de traducción
permanente, no una fusión de una sola vez: el importador la consulta en cada
carga, así que se confirma una vez y cruza para siempre. Si fuera una fusión,
la próxima importación volvería a crear los dos artículos separados y habría
que rehacer el trabajo todos los meses.

Se guarda siempre el código tal como lo escribe cada sistema, más su forma
normalizada, que es por la que busca el importador.
"""

from datetime import datetime, timezone

from app.extensions import db
from app.utils.codigos import codigo_normalizado


class EquivalenciaCodigo(db.Model):
    """Un código de Defontana que apunta al mismo artículo que uno de QMS."""

    __tablename__ = "equivalencias_codigos"
    __table_args__ = (
        # Un código de Defontana no puede apuntar a dos artículos distintos.
        db.UniqueConstraint(
            "empresa_id", "clave_defontana", name="uq_equivalencia_defontana"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False, index=True)

    # Tal como los escribe cada sistema: es lo que se muestra en pantalla.
    codigo_qms = db.Column(db.String(80), nullable=False)
    codigo_defontana = db.Column(db.String(80), nullable=False)
    # Por acá busca el importador, con la misma función que usa para cruzar.
    clave_qms = db.Column(db.String(80), nullable=False, index=True)
    clave_defontana = db.Column(db.String(80), nullable=False, index=True)

    # Para poder revisar después por qué se unieron, y deshacerlo con criterio.
    puntaje = db.Column(db.Integer, nullable=True)
    motivo = db.Column(db.String(120), nullable=True)

    creado_en = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    creado_por = db.relationship("Usuario")

    def __repr__(self):
        return f"<EquivalenciaCodigo {self.codigo_defontana} -> {self.codigo_qms}>"


def crear_equivalencia(empresa_id, codigo_qms, codigo_defontana, usuario_id,
                       puntaje=None, motivo=None):
    """Confirma que los dos códigos son el mismo artículo.

    Devuelve (equivalencia, error). El error es un texto para mostrar: vale más
    explicar por qué no se puede que dejar reventar una restricción de la base.
    """
    clave_qms = codigo_normalizado(codigo_qms)
    clave_defo = codigo_normalizado(codigo_defontana)
    if not clave_qms or not clave_defo:
        return None, "Faltan los dos códigos."
    if clave_qms == clave_defo:
        return None, "Esos dos códigos ya cruzan solos: no hace falta unirlos."

    ya = EquivalenciaCodigo.query.filter_by(
        empresa_id=empresa_id, clave_defontana=clave_defo
    ).first()
    if ya is not None:
        return None, (
            f"{codigo_defontana} ya está unido a {ya.codigo_qms}. "
            "Deshaz esa unión antes de hacer otra."
        )

    equivalencia = EquivalenciaCodigo(
        empresa_id=empresa_id,
        codigo_qms=str(codigo_qms)[:80],
        codigo_defontana=str(codigo_defontana)[:80],
        clave_qms=clave_qms[:80],
        clave_defontana=clave_defo[:80],
        puntaje=int(round((puntaje or 0) * 100)) or None,
        motivo=(motivo or "")[:120] or None,
        creado_por_id=usuario_id,
    )
    db.session.add(equivalencia)
    return equivalencia, None


def traducciones(empresa_id) -> dict:
    """{clave de Defontana: clave de QMS}, para que el importador cruce solo."""
    return {
        e.clave_defontana: e.clave_qms
        for e in EquivalenciaCodigo.query.filter_by(empresa_id=empresa_id).all()
    }
