from datetime import datetime, timezone

from app.extensions import db


class RegularizacionArchivo(db.Model):
    """Lo que se sube al submódulo Regularización, para no tener que volver a subirlo.

    Hay una fila por empresa y por clave, y cada subida reemplaza a la anterior:
      - "conteo": Excel del conteo físico (archivo 1).
      - "informe": Informe de Documentos de Defontana (archivo 2).
      - "informe_ajustes": el informe descargado de nuevo con los ajustes (archivo 3).
      - "ajustes": informe solo con los comprobantes de ajuste ya hechos.
      - "estado": JSON con los recuentos, los PMP corregidos a mano y los documentos
        de ajuste marcados.

    El contenido va en la base y no en el disco: en Render el disco se borra en
    cada despliegue, y la base (Neon) es lo único que persiste.
    """

    __tablename__ = "regularizacion_archivos"
    __table_args__ = (db.UniqueConstraint("empresa_id", "clave", name="uq_regularizacion_empresa_clave"),)

    CLAVES = ("conteo", "informe", "informe_ajustes", "ajustes", "estado")

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    clave = db.Column(db.String(30), nullable=False)
    nombre = db.Column(db.String(255), nullable=True)
    contenido = db.Column(db.LargeBinary, nullable=False)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    actualizado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    actualizado_por = db.relationship("Usuario")

    def __repr__(self):
        return f"<RegularizacionArchivo {self.clave} empresa={self.empresa_id}>"


class RegularizacionHistorial(db.Model):
    """Una regularización guardada aparte, para poder volver a verla cuando se quiera.

    Al empezar una regularización nueva, los archivos y el estado que estaban en
    uso se copian aquí (con su nombre y fecha) y la pantalla queda vacía para
    subir la información nueva.
    """

    __tablename__ = "regularizacion_historial"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False, index=True)
    nombre = db.Column(db.String(150), nullable=False)
    creado_en = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    creado_por = db.relationship("Usuario")
    archivos = db.relationship("RegularizacionHistorialArchivo", backref="historial", cascade="all, delete-orphan",
                               order_by="RegularizacionHistorialArchivo.id")

    def __repr__(self):
        return f"<RegularizacionHistorial {self.nombre!r} empresa={self.empresa_id}>"


class RegularizacionHistorialArchivo(db.Model):
    """Copia de un archivo (o del estado) de una regularización guardada en el historial."""

    __tablename__ = "regularizacion_historial_archivos"

    id = db.Column(db.Integer, primary_key=True)
    historial_id = db.Column(db.Integer, db.ForeignKey("regularizacion_historial.id", ondelete="CASCADE"), nullable=False, index=True)
    clave = db.Column(db.String(30), nullable=False)
    nombre = db.Column(db.String(255), nullable=True)
    contenido = db.Column(db.LargeBinary, nullable=False)
    actualizado_en = db.Column(db.DateTime, nullable=False)
    actualizado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    actualizado_por = db.relationship("Usuario")
