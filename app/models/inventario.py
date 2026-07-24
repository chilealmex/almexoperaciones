from datetime import datetime, timezone

from app.extensions import db


class CategoriaProducto(db.Model):
    __tablename__ = "categorias_producto"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)

    productos = db.relationship("Producto", back_populates="categoria")


class Producto(db.Model):
    __tablename__ = "productos"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    sku = db.Column(db.String(50), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)
    categoria_id = db.Column(
        db.Integer, db.ForeignKey("categorias_producto.id"), nullable=True
    )
    unidad_medida = db.Column(db.String(20), default="unidad", nullable=False)
    stock_minimo = db.Column(db.Integer, default=0, nullable=False)
    stock_actual = db.Column(db.Integer, default=0, nullable=False)
    precio_costo = db.Column(db.Integer, default=0, nullable=False)  # CLP, sin decimales
    precio_venta = db.Column(db.Integer, default=0, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    creado_en = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    categoria = db.relationship("CategoriaProducto", back_populates="productos")
    movimientos = db.relationship(
        "MovimientoInventario", back_populates="producto", order_by="desc(MovimientoInventario.fecha)"
    )

    @property
    def bajo_stock_minimo(self) -> bool:
        return self.stock_actual < self.stock_minimo

    def __repr__(self):
        return f"<Producto {self.sku} {self.nombre}>"


class MovimientoInventario(db.Model):
    __tablename__ = "movimientos_inventario"

    TIPOS = ("entrada", "salida", "ajuste")
    TIPOS_DOCUMENTO = ("factura", "guia_despacho", "nota_credito", "otro")

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    tipo_documento = db.Column(db.String(20), nullable=True)
    numero_documento = db.Column(db.String(50), nullable=True)
    motivo = db.Column(db.String(255), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    observaciones = db.Column(db.Text, nullable=True)
    creado_en = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    producto = db.relationship("Producto", back_populates="movimientos")
    usuario = db.relationship("Usuario")

    def __repr__(self):
        return f"<Movimiento {self.tipo} {self.cantidad} producto={self.producto_id}>"
