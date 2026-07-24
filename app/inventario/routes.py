from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user

from app.inventario import bp
from app.inventario.forms import ProductoForm, MovimientoForm
from app.extensions import db
from app.models.inventario import Producto, CategoriaProducto, MovimientoInventario
from app.utils.decorators import require_permission
from app.utils.storage import guardar_documento, listar_documentos


def _cargar_categorias(form):
    form.categoria_id.choices = [(0, "— Sin categoría —")] + [
        (c.id, c.nombre) for c in CategoriaProducto.query.order_by(CategoriaProducto.nombre).all()
    ]


@bp.route("/")
@require_permission("inventario", "ver")
def productos():
    lista = Producto.query.order_by(Producto.nombre).all()
    activos = [p for p in lista if p.activo]
    stats = {
        "total_activos": len(activos),
        "bajo_stock": sum(1 for p in activos if p.bajo_stock_minimo),
        "valor_costo": sum(p.stock_actual * p.precio_costo for p in activos),
        "valor_venta": sum(p.stock_actual * p.precio_venta for p in activos),
    }
    return render_template("inventario/productos_lista.html", productos=lista, stats=stats)


@bp.route("/productos/nuevo", methods=["GET", "POST"])
@require_permission("inventario", "editar")
def nuevo_producto():
    form = ProductoForm()
    _cargar_categorias(form)
    if form.validate_on_submit():
        if Producto.query.filter_by(sku=form.sku.data.strip()).first():
            flash("Ya existe un producto con ese SKU.", "danger")
            return render_template("inventario/producto_form.html", form=form, producto=None)

        producto = Producto(
            empresa_id=current_user.empresa_id,
            sku=form.sku.data.strip(),
            nombre=form.nombre.data.strip(),
            descripcion=form.descripcion.data,
            categoria_id=form.categoria_id.data or None,
            unidad_medida=form.unidad_medida.data.strip(),
            stock_minimo=form.stock_minimo.data,
            precio_costo=form.precio_costo.data,
            precio_venta=form.precio_venta.data,
            activo=form.activo.data,
        )
        db.session.add(producto)
        db.session.commit()
        flash("Producto creado correctamente.", "success")
        return redirect(url_for("inventario.productos"))

    return render_template("inventario/producto_form.html", form=form, producto=None)


@bp.route("/productos/<int:producto_id>/editar", methods=["GET", "POST"])
@require_permission("inventario", "editar")
def editar_producto(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    form = ProductoForm(obj=producto)
    _cargar_categorias(form)
    if request.method == "GET":
        form.categoria_id.data = producto.categoria_id or 0

    if form.validate_on_submit():
        duplicado = Producto.query.filter(
            Producto.sku == form.sku.data.strip(), Producto.id != producto.id
        ).first()
        if duplicado:
            flash("Ya existe otro producto con ese SKU.", "danger")
            return render_template("inventario/producto_form.html", form=form, producto=producto)

        producto.sku = form.sku.data.strip()
        producto.nombre = form.nombre.data.strip()
        producto.descripcion = form.descripcion.data
        producto.categoria_id = form.categoria_id.data or None
        producto.unidad_medida = form.unidad_medida.data.strip()
        producto.stock_minimo = form.stock_minimo.data
        producto.precio_costo = form.precio_costo.data
        producto.precio_venta = form.precio_venta.data
        producto.activo = form.activo.data
        db.session.commit()
        flash("Producto actualizado correctamente.", "success")
        return redirect(url_for("inventario.productos"))

    return render_template("inventario/producto_form.html", form=form, producto=producto)


@bp.route("/productos/<int:producto_id>")
@require_permission("inventario", "ver")
def ver_producto(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    return render_template("inventario/producto_ver.html", producto=producto)


@bp.route("/productos/<int:producto_id>/movimiento", methods=["GET", "POST"])
@require_permission("inventario", "editar")
def nuevo_movimiento(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    form = MovimientoForm()

    if form.validate_on_submit():
        tipo = form.tipo.data
        cantidad = form.cantidad.data

        if tipo in ("entrada", "salida") and cantidad < 1:
            flash("La cantidad debe ser mayor a cero.", "danger")
            return render_template("inventario/movimiento_form.html", form=form, producto=producto)

        if tipo == "salida" and cantidad > producto.stock_actual:
            flash(
                f"No hay stock suficiente. Stock actual: {producto.stock_actual}.", "danger"
            )
            return render_template("inventario/movimiento_form.html", form=form, producto=producto)

        movimiento = MovimientoInventario(
            empresa_id=current_user.empresa_id,
            producto_id=producto.id,
            tipo=tipo,
            cantidad=cantidad,
            tipo_documento=form.tipo_documento.data or None,
            numero_documento=form.numero_documento.data,
            motivo=form.motivo.data,
            usuario_id=current_user.id,
            observaciones=form.observaciones.data,
        )
        db.session.add(movimiento)

        if tipo == "entrada":
            producto.stock_actual += cantidad
        elif tipo == "salida":
            producto.stock_actual -= cantidad
        else:  # ajuste: la cantidad ingresada es el nuevo stock absoluto
            producto.stock_actual = cantidad

        db.session.flush()

        if form.archivo.data:
            guardar_documento("movimiento_inventario", movimiento.id, form.archivo.data, current_user.id)

        db.session.commit()
        flash("Movimiento registrado correctamente.", "success")
        return redirect(url_for("inventario.ver_producto", producto_id=producto.id))

    return render_template("inventario/movimiento_form.html", form=form, producto=producto)


@bp.route("/movimientos")
@require_permission("inventario", "ver")
def movimientos():
    lista = MovimientoInventario.query.order_by(MovimientoInventario.fecha.desc()).limit(200).all()
    return render_template("inventario/movimientos_lista.html", movimientos=lista)
