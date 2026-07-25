from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from sqlalchemy import or_

from app.inventario import bp
from app.inventario.forms import ProductoForm, MovimientoForm, ImportarCsvForm, ContarFisicoForm
from app.extensions import db
from app.models.inventario import Producto, CategoriaProducto, MovimientoInventario
from app.models.conteo_inventario import ItemConteoInventario
from app.utils.decorators import require_permission
from app.utils.storage import guardar_documento, listar_documentos
from app.utils.importar_conteo import importar_qms, importar_defontana


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


# --- Conteo físico (cruce QMS / Defontana) ---


@bp.route("/conteo")
@require_permission("inventario", "ver")
def conteo():
    q = request.args.get("q", "").strip()
    query = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id)
    if q:
        patron = f"%{q}%"
        query = query.filter(or_(ItemConteoInventario.codigo.ilike(patron), ItemConteoInventario.nombre.ilike(patron)))
    items = query.order_by(ItemConteoInventario.codigo).limit(500).all()
    total = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id).count()
    return render_template("inventario/conteo_lista.html", items=items, q=q, total=total)


@bp.route("/conteo/diferencias")
@require_permission("inventario", "ver")
def conteo_diferencias():
    todos = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id).order_by(ItemConteoInventario.codigo).all()
    items = [i for i in todos if i.tiene_diferencia]
    return render_template("inventario/conteo_diferencias.html", items=items)


@bp.route("/conteo/<int:item_id>/contar", methods=["GET", "POST"])
@require_permission("inventario", "editar")
def conteo_contar(item_id):
    item = ItemConteoInventario.query.filter_by(id=item_id, empresa_id=current_user.empresa_id).first_or_404()
    form = ContarFisicoForm(obj=item)
    if form.validate_on_submit():
        item.cantidad_fisica = form.cantidad_fisica.data
        item.contado_por_id = current_user.id
        from datetime import datetime, timezone

        item.contado_en = datetime.now(timezone.utc)
        db.session.commit()
        flash(f"Conteo de {item.codigo} registrado correctamente.", "success")
        return redirect(url_for("inventario.conteo", q=request.args.get("q", "")))

    return render_template("inventario/conteo_contar.html", form=form, item=item)


@bp.route("/conteo/importar", methods=["GET", "POST"])
@require_permission("inventario", "editar")
def conteo_importar():
    form_qms = ImportarCsvForm(prefix="qms")
    form_defontana = ImportarCsvForm(prefix="def")
    total_items = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id).count()
    return render_template(
        "inventario/conteo_importar.html", form_qms=form_qms, form_defontana=form_defontana, total_items=total_items
    )


@bp.route("/conteo/importar/qms", methods=["POST"])
@require_permission("inventario", "editar")
def conteo_importar_qms():
    form = ImportarCsvForm(prefix="qms")
    if form.validate_on_submit():
        try:
            resultado = importar_qms(form.archivo.data, current_user.empresa_id)
            flash(
                f"QMS importado: {resultado['total_codigos']} códigos "
                f"({resultado['creados']} nuevos, {resultado['actualizados']} actualizados).",
                "success",
            )
        except ValueError as e:
            flash(str(e), "danger")
    else:
        flash("Selecciona un archivo CSV válido.", "danger")
    return redirect(url_for("inventario.conteo_importar"))


@bp.route("/conteo/importar/defontana", methods=["POST"])
@require_permission("inventario", "editar")
def conteo_importar_defontana():
    form = ImportarCsvForm(prefix="def")
    if form.validate_on_submit():
        try:
            resultado = importar_defontana(form.archivo.data, current_user.empresa_id)
            flash(
                f"Defontana importado: {resultado['total_codigos']} códigos "
                f"({resultado['creados']} nuevos, {resultado['actualizados']} actualizados).",
                "success",
            )
        except ValueError as e:
            flash(str(e), "danger")
    else:
        flash("Selecciona un archivo CSV válido.", "danger")
    return redirect(url_for("inventario.conteo_importar"))
