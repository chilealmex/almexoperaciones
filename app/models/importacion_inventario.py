"""Rastro de la última importación de cada sistema.

Cuando se sube el archivo de QMS o de Defontana sale un mensaje verde con el
resumen, y al cambiar de pantalla no queda rastro. Entonces, mirando el stock,
no hay forma de saber si viene del archivo de hoy o del de la semana pasada:
el número se ve igual de convincente en los dos casos.

Se guarda una fila por empresa y por sistema, que se reemplaza en cada subida.
No es un historial: la pregunta que responde es "¿esto está al día?", y para
eso lo único que importa es la última.
"""

from datetime import datetime, timezone

from app.extensions import db


class ImportacionInventario(db.Model):
    """Qué archivo se subió, cuándo, quién y qué trajo."""

    __tablename__ = "importaciones_inventario"
    __table_args__ = (
        db.UniqueConstraint("empresa_id", "sistema", name="uq_importacion_inventario_sistema"),
    )

    SISTEMAS = (("qms", "QMS"), ("defontana", "Defontana"))

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    sistema = db.Column(db.String(20), nullable=False)

    archivo = db.Column(db.String(255), nullable=True)
    importado_en = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    importado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    # El resumen que ya calcula el importador: sirve para notar de inmediato que
    # se subió el archivo equivocado, cuando los números no se parecen en nada
    # a los de la vez anterior.
    total_codigos = db.Column(db.Integer, nullable=False, default=0)
    creados = db.Column(db.Integer, nullable=False, default=0)
    actualizados = db.Column(db.Integer, nullable=False, default=0)

    importado_por = db.relationship("Usuario")

    @property
    def etiqueta(self) -> str:
        return dict(self.SISTEMAS).get(self.sistema, self.sistema)

    def __repr__(self):
        return f"<ImportacionInventario {self.sistema} empresa={self.empresa_id}>"


def registrar_importacion(empresa_id, sistema, archivo, usuario_id, resultado):
    """Deja constancia de una importación, reemplazando la anterior del sistema.

    Recibe el mismo diccionario que devuelve el importador, así que no hay un
    segundo recuento que pueda discrepar del que se muestra al subir.
    """
    registro = ImportacionInventario.query.filter_by(
        empresa_id=empresa_id, sistema=sistema
    ).first()
    if registro is None:
        registro = ImportacionInventario(empresa_id=empresa_id, sistema=sistema)
        db.session.add(registro)

    registro.archivo = (archivo or "")[:255] or None
    registro.importado_en = datetime.now(timezone.utc)
    registro.importado_por_id = usuario_id
    registro.total_codigos = (resultado or {}).get("total_codigos", 0)
    registro.creados = (resultado or {}).get("creados", 0)
    registro.actualizados = (resultado or {}).get("actualizados", 0)
    return registro


def ultimas_importaciones(empresa_id) -> dict:
    """{'qms': registro, 'defontana': registro}, con None en el que falte."""
    registros = {
        r.sistema: r
        for r in ImportacionInventario.query.filter_by(empresa_id=empresa_id).all()
    }
    return {clave: registros.get(clave) for clave, _etiqueta in ImportacionInventario.SISTEMAS}
