from app.extensions import db


class Empresa(db.Model):
    __tablename__ = "empresas"

    id = db.Column(db.Integer, primary_key=True)
    rut = db.Column(db.String(12), unique=True, nullable=False)
    razon_social = db.Column(db.String(150), nullable=False)
    nombre_fantasia = db.Column(db.String(150), nullable=True)
    giro = db.Column(db.String(150), nullable=True)
    direccion = db.Column(db.String(200), nullable=True)
    comuna = db.Column(db.String(80), nullable=True)
    ciudad = db.Column(db.String(80), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    logo_path = db.Column(db.String(255), nullable=True)

    usuarios = db.relationship("Usuario", back_populates="empresa")

    def __repr__(self):
        return f"<Empresa {self.razon_social}>"
