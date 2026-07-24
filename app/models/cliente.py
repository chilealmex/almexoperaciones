from app.extensions import db


class Cliente(db.Model):
    __tablename__ = "clientes"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    rut = db.Column(db.String(12), nullable=False)
    razon_social = db.Column(db.String(150), nullable=False)
    giro = db.Column(db.String(150), nullable=True)
    direccion = db.Column(db.String(200), nullable=True)
    comuna = db.Column(db.String(80), nullable=True)
    ciudad = db.Column(db.String(80), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    contacto_nombre = db.Column(db.String(120), nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    creado_en = db.Column(db.DateTime, server_default=db.func.now())

    contratos = db.relationship("ContratoCliente", back_populates="cliente")
    arriendos_salida = db.relationship("ArriendoSalida", back_populates="cliente")

    def __repr__(self):
        return f"<Cliente {self.razon_social}>"


class Proveedor(db.Model):
    __tablename__ = "proveedores"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    rut = db.Column(db.String(12), nullable=False)
    razon_social = db.Column(db.String(150), nullable=False)
    giro = db.Column(db.String(150), nullable=True)
    direccion = db.Column(db.String(200), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    contacto_nombre = db.Column(db.String(120), nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    creado_en = db.Column(db.DateTime, server_default=db.func.now())

    arriendos_entrada = db.relationship("ArriendoEntrada", back_populates="proveedor")

    def __repr__(self):
        return f"<Proveedor {self.razon_social}>"
