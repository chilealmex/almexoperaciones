"""Dos planillas subidas para compararlas, sin cargarlas al sistema.

Comparar no es importar. El maestro de artículos es uno solo y lo miran todos
los submódulos de Inventario —Stock y conteo, Ajuste inventario, Unificar
códigos—, así que escribir en él para poder ver un cruce obliga a cambiarle los
datos a todo el mundo. Acá las planillas se leen, se comparan y se guarda
únicamente el resultado de esa lectura, aparte del maestro, que no se toca.

Es por usuario: la prueba de uno no puede cambiarle la pantalla a otro.
"""

import gzip
import json
from datetime import datetime, timezone

from app.extensions import db


class CruceDePrueba(db.Model):
    __tablename__ = "cruce_prueba"
    __table_args__ = (
        db.UniqueConstraint("empresa_id", "usuario_id", name="uq_cruce_prueba_usuario"),
    )

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    nombre_qms = db.Column(db.String(255), nullable=True)
    nombre_defontana = db.Column(db.String(255), nullable=True)
    # Lo leído de las dos planillas, comprimido: en una de 3.000 artículos son
    # 835 KB de texto que bajan a 126 KB, y volver a leerlas desde el archivo
    # cuesta 1,2 s en cada clic de un filtro.
    datos = db.Column(db.LargeBinary, nullable=False)
    creado_en = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    usuario = db.relationship("Usuario")

    def __repr__(self):
        return f"<CruceDePrueba empresa={self.empresa_id} usuario={self.usuario_id}>"

    @property
    def contenido(self) -> dict:
        return json.loads(gzip.decompress(self.datos))

    @contenido.setter
    def contenido(self, valor: dict):
        self.datos = gzip.compress(json.dumps(valor).encode("utf-8"), 6)


def guardar_prueba(empresa_id, usuario_id, contenido, nombre_qms, nombre_defontana):
    """Deja una sola prueba por persona: subir otra reemplaza la anterior."""
    prueba = CruceDePrueba.query.filter_by(empresa_id=empresa_id, usuario_id=usuario_id).first()
    if prueba is None:
        prueba = CruceDePrueba(empresa_id=empresa_id, usuario_id=usuario_id)
        db.session.add(prueba)
    prueba.contenido = contenido
    prueba.nombre_qms = (nombre_qms or "")[:255] or None
    prueba.nombre_defontana = (nombre_defontana or "")[:255] or None
    prueba.creado_en = datetime.now(timezone.utc)
    return prueba


def prueba_en_curso(empresa_id, usuario_id):
    return CruceDePrueba.query.filter_by(empresa_id=empresa_id, usuario_id=usuario_id).first()


def borrar_prueba(empresa_id, usuario_id) -> bool:
    prueba = prueba_en_curso(empresa_id, usuario_id)
    if prueba is None:
        return False
    db.session.delete(prueba)
    return True
