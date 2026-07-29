import csv
import io
from datetime import date, datetime, timezone

from flask import render_template, redirect, url_for, flash, request, abort, jsonify, make_response
from flask_login import current_user
from sqlalchemy import or_, and_

from app.inventario import bp
from app.inventario.forms import ProductoForm, MovimientoForm, ImportarCsvForm
from app.extensions import db
from app.models.inventario import Producto, CategoriaProducto, MovimientoInventario
from app.models.conteo_inventario import ItemConteoInventario
from app.utils.decorators import require_permission
from app.utils.storage import guardar_documento, listar_documentos
from app.utils.importar_conteo import importar_qms, importar_defontana
from app.utils.formatting import format_clp
from app.utils.graficos import COLOR, serie, widget_seguro
from app.utils.paneles import panel_inventario


def _cargar_categorias(form):
    form.categoria_id.choices = [(0, "— Sin categoría —")] + [
        (c.id, c.nombre) for c in CategoriaProducto.query.order_by(CategoriaProducto.nombre).all()
    ]


def _stats_inventario():
    lista = Producto.query.order_by(Producto.nombre).all()
    activos = [p for p in lista if p.activo]
    total_conteo = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id).count()
    items_conteo = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id).all()
    return lista, {
        "total_activos": len(activos),
        "bajo_stock": sum(1 for p in activos if p.bajo_stock_minimo),
        "valor_costo": sum(p.stock_actual * p.precio_costo for p in activos),
        "valor_venta": sum(p.stock_actual * p.precio_venta for p in activos),
        "total_conteo": total_conteo,
        "conteo_con_diferencia": sum(1 for i in items_conteo if i.tiene_diferencia),
        "conteo_pendientes": sum(1 for i in items_conteo if i.cantidad_fisica is None),
    }


@bp.route("/")
@require_permission("inventario", "ver")
def resumen():
    _lista, stats = _stats_inventario()
    panel = widget_seguro(panel_inventario, nombre="resumen de inventario")
    return render_template("inventario/resumen.html", stats=stats, panel=panel)


COLUMNAS_PRODUCTOS = {
    "sku": Producto.sku,
    "nombre": Producto.nombre,
    "stock": Producto.stock_actual,
    "stock_minimo": Producto.stock_minimo,
    "precio_costo": Producto.precio_costo,
    "precio_venta": Producto.precio_venta,
}

FILTROS_PRODUCTOS = ("todos", "bajo_stock", "sin_stock", "inactivos")


@bp.route("/productos")
@require_permission("inventario", "ver")
def productos():
    """Listado de productos con búsqueda, filtros por columna y orden por título."""
    consulta = Producto.query.outerjoin(CategoriaProducto, Producto.categoria_id == CategoriaProducto.id)

    q = (request.args.get("q") or "").strip()
    if q:
        patron = f"%{q}%"
        consulta = consulta.filter(or_(Producto.sku.ilike(patron), Producto.nombre.ilike(patron)))

    filtros_columna = {}
    for parametro, columna in (
        ("f_sku", Producto.sku),
        ("f_nombre", Producto.nombre),
        ("f_categoria", CategoriaProducto.nombre),
    ):
        texto = (request.args.get(parametro) or "").strip()
        filtros_columna[parametro] = texto
        if texto:
            consulta = consulta.filter(columna.ilike(f"%{texto}%"))

    filtro = request.args.get("filtro", "todos")
    if filtro not in FILTROS_PRODUCTOS:
        filtro = "todos"
    if filtro == "inactivos":
        consulta = consulta.filter(Producto.activo.is_(False))
    else:
        consulta = consulta.filter(Producto.activo.is_(True))
        if filtro == "bajo_stock":
            consulta = consulta.filter(Producto.stock_actual < Producto.stock_minimo)
        elif filtro == "sin_stock":
            consulta = consulta.filter(Producto.stock_actual <= 0)

    consulta, orden, direccion = _ordenar(consulta, request.args, COLUMNAS_PRODUCTOS, "nombre")
    lista = consulta.all()

    todos = Producto.query.all()
    activos = [p for p in todos if p.activo]
    conteos = {
        "todos": len(activos),
        "bajo_stock": sum(1 for p in activos if p.bajo_stock_minimo),
        "sin_stock": sum(1 for p in activos if p.stock_actual <= 0),
        "inactivos": len(todos) - len(activos),
    }
    resumen_filtro = {
        "articulos": len(lista),
        "unidades": sum(p.stock_actual for p in lista),
        "valor_costo": sum(p.stock_actual * p.precio_costo for p in lista),
        "valor_venta": sum(p.stock_actual * p.precio_venta for p in lista),
    }

    return render_template(
        "inventario/productos_lista.html",
        productos=lista,
        q=q,
        filtro=filtro,
        filtros_columna=filtros_columna,
        orden=orden,
        direccion=direccion,
        conteos=conteos,
        resumen_filtro=resumen_filtro,
    )


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


# --- Stock: cruce QMS / Defontana, conteo físico y diferencias en una sola vista ---

FILTROS_STOCK = ("todos", "diferencias", "sin_contar", "contados")


COLUMNAS_STOCK = {
    "codigo": ItemConteoInventario.codigo,
    "nombre": ItemConteoInventario.nombre,
    "cantidad_qms": ItemConteoInventario.cantidad_qms,
    "cantidad_defontana": ItemConteoInventario.cantidad_defontana,
    "cantidad_fisica": ItemConteoInventario.cantidad_fisica,
    "ubicacion": ItemConteoInventario.ubicacion,
    "linea_negocio": ItemConteoInventario.linea_negocio,
}


@bp.route("/stock")
@require_permission("inventario", "ver")
def stock():
    q = request.args.get("q", "").strip()
    filtro = request.args.get("filtro", "todos")
    if filtro not in FILTROS_STOCK:
        filtro = "todos"
    pagina = request.args.get("pagina", 1, type=int)

    base = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id)
    if q:
        patron = f"%{q}%"
        base = base.filter(
            or_(ItemConteoInventario.codigo.ilike(patron), ItemConteoInventario.nombre.ilike(patron))
        )

    base, filtros_columna = _filtros_de_columna(base, request.args)

    if filtro == "sin_contar":
        base = base.filter(ItemConteoInventario.cantidad_fisica.is_(None))
    elif filtro == "contados":
        base = base.filter(ItemConteoInventario.cantidad_fisica.isnot(None))
    elif filtro == "diferencias":
        # descuadre entre sistemas, o el físico contado no coincide con alguno de ellos
        base = base.filter(
            or_(
                ItemConteoInventario.cantidad_qms != ItemConteoInventario.cantidad_defontana,
                and_(
                    ItemConteoInventario.cantidad_fisica.isnot(None),
                    or_(
                        ItemConteoInventario.cantidad_fisica != ItemConteoInventario.cantidad_qms,
                        ItemConteoInventario.cantidad_fisica != ItemConteoInventario.cantidad_defontana,
                    ),
                ),
            )
        )

    base, orden, direccion = _ordenar(base, request.args, COLUMNAS_STOCK, "codigo")
    paginacion = base.paginate(page=max(1, pagina), per_page=100, error_out=False)

    todos = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id).all()
    resumen = {
        "total": len(todos),
        "con_diferencia": sum(1 for i in todos if i.tiene_diferencia),
        "sin_contar": sum(1 for i in todos if not i.contado),
        "contados": sum(1 for i in todos if i.contado),
    }
    return render_template(
        "inventario/stock.html",
        paginacion=paginacion,
        q=q,
        filtro=filtro,
        resumen=resumen,
        filtros_columna=filtros_columna,
        orden=orden,
        direccion=direccion,
    )


@bp.route("/stock/<int:item_id>/contar", methods=["POST"])
@require_permission("inventario", "editar")
def stock_contar(item_id):
    """Registra el conteo físico desde la misma fila del listado, sin recargar la página."""
    item = ItemConteoInventario.query.filter_by(
        id=item_id, empresa_id=current_user.empresa_id
    ).first_or_404()

    datos = request.get_json(silent=True) or {}
    valor = str(datos.get("cantidad", "")).strip()

    if valor == "":
        item.cantidad_fisica = None
        item.contado_por_id = None
        item.contado_en = None
    else:
        try:
            cantidad = int(valor)
        except ValueError:
            return jsonify({"ok": False, "error": "Ingresa un número entero."}), 400
        if cantidad < 0:
            return jsonify({"ok": False, "error": "La cantidad no puede ser negativa."}), 400
        item.cantidad_fisica = cantidad
        item.contado_por_id = current_user.id
        item.contado_en = datetime.now(timezone.utc)

    db.session.commit()
    return jsonify(
        {
            "ok": True,
            "contado": item.contado,
            "dif_qms": item.diferencia_fisica_qms,
            "dif_defontana": item.diferencia_fisica_defontana,
            "tiene_diferencia": item.tiene_diferencia,
        }
    )


# --- Ajuste de inventario: valorización QMS vs Defontana vs conteo físico ---

FILTROS_AJUSTE = ("todos", "dif_costo", "dif_unidad", "dif_stock", "sin_costo", "contados")

COLUMNAS_AJUSTE = {
    "codigo": ItemConteoInventario.codigo,
    "nombre": ItemConteoInventario.nombre,
    "unidad_qms": ItemConteoInventario.unidad_qms,
    "unidad_defontana": ItemConteoInventario.unidad_defontana,
    "categoria": ItemConteoInventario.categoria,
    "linea_negocio": ItemConteoInventario.linea_negocio,
    "costo_qms": ItemConteoInventario.costo_unitario_qms,
    "costo_defontana": ItemConteoInventario.costo_unitario_defontana,
    "cantidad_qms": ItemConteoInventario.cantidad_qms,
    "cantidad_defontana": ItemConteoInventario.cantidad_defontana,
    "cantidad_fisica": ItemConteoInventario.cantidad_fisica,
}

# Filtros de texto por columna: parámetro de la URL -> columna de la tabla
FILTROS_COLUMNA = {
    "f_codigo": ItemConteoInventario.codigo,
    "f_nombre": ItemConteoInventario.nombre,
    "f_unidad": ItemConteoInventario.unidad_qms,
    "f_categoria": ItemConteoInventario.categoria,
    "f_linea": ItemConteoInventario.linea_negocio,
    "f_ubicacion": ItemConteoInventario.ubicacion,
}


def _filtros_de_columna(consulta, args):
    """Aplica los filtros escritos bajo cada título de columna. Devuelve (consulta, valores)."""
    valores = {}
    for parametro, columna in FILTROS_COLUMNA.items():
        texto = (args.get(parametro) or "").strip()
        valores[parametro] = texto
        if texto:
            consulta = consulta.filter(columna.ilike(f"%{texto}%"))
    return consulta, valores


def _ordenar(consulta, args, columnas, por_defecto):
    """Ordena por la columna pedida en el encabezado; ignora columnas desconocidas."""
    orden = args.get("orden") or por_defecto
    if orden not in columnas:
        orden = por_defecto
    descendente = args.get("dir") == "desc"
    columna = columnas[orden]
    consulta = consulta.order_by(columna.desc() if descendente else columna.asc())
    return consulta, orden, ("desc" if descendente else "asc")


def _items_ajuste(args):
    """Items del cruce ya filtrados y ordenados según lo pedido en la vista."""
    consulta = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id)

    busqueda = (args.get("q") or "").strip()
    if busqueda:
        patron = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(ItemConteoInventario.codigo.ilike(patron), ItemConteoInventario.nombre.ilike(patron))
        )

    consulta, filtros_columna = _filtros_de_columna(consulta, args)
    consulta, orden, direccion = _ordenar(consulta, args, COLUMNAS_AJUSTE, "codigo")

    items = consulta.all()

    filtro = args.get("filtro", "todos")
    if filtro not in FILTROS_AJUSTE:
        filtro = "todos"
    if filtro == "dif_costo":
        items = [i for i in items if i.tiene_diferencia_costo]
    elif filtro == "dif_unidad":
        items = [i for i in items if not i.unidades_coinciden]
    elif filtro == "dif_stock":
        items = [i for i in items if i.diferencia_sistemas != 0]
    elif filtro == "sin_costo":
        items = [i for i in items if not i.tiene_costo]
    elif filtro == "contados":
        items = [i for i in items if i.contado]

    return items, busqueda, filtros_columna, filtro, orden, direccion


def _totales_ajuste(items):
    """Valorización agregada del conjunto filtrado."""
    contados = [i for i in items if i.contado]
    return {
        "articulos": len(items),
        "stock_qms": sum(i.cantidad_qms or 0 for i in items),
        "stock_defontana": sum(i.cantidad_defontana or 0 for i in items),
        "stock_fisico": sum(i.cantidad_fisica or 0 for i in contados),
        "valor_qms": sum(i.valor_qms for i in items),
        "valor_defontana": sum(i.valor_defontana for i in items),
        "valor_fisico": sum(i.valor_fisico or 0 for i in contados),
        "valor_qms_contados": sum(i.valor_qms for i in contados),
        "ajuste_fisico": sum(i.diferencia_valor_fisico or 0 for i in contados),
        "contados": len(contados),
        "dif_costo": sum(1 for i in items if i.tiene_diferencia_costo),
        "dif_unidad": sum(1 for i in items if not i.unidades_coinciden),
        "dif_stock": sum(1 for i in items if i.diferencia_sistemas != 0),
        "sin_costo": sum(1 for i in items if not i.tiene_costo),
    }


@bp.route("/ajuste")
@require_permission("inventario", "ver")
def ajuste():
    """Compara costo, unidad de medida y valorización entre QMS, Defontana y el conteo físico."""
    items, busqueda, filtros_columna, filtro, orden, direccion = _items_ajuste(request.args)
    totales = _totales_ajuste(items)

    pagina = max(1, request.args.get("pagina", 1, type=int))
    por_pagina = 100
    total_paginas = max(1, (len(items) + por_pagina - 1) // por_pagina)
    pagina = min(pagina, total_paginas)
    visibles = items[(pagina - 1) * por_pagina : pagina * por_pagina]

    # Artículos donde la diferencia de valorización pesa más
    top_diferencias = sorted(items, key=lambda i: abs(i.diferencia_valor_sistemas), reverse=True)[:8]
    grafico_top = [
        serie(
            (i.nombre or i.codigo)[:38],
            abs(i.diferencia_valor_sistemas),
            COLOR["rojo"] if i.diferencia_valor_sistemas > 0 else COLOR["azul"],
            texto=format_clp(i.diferencia_valor_sistemas),
        )
        for i in top_diferencias
        if i.diferencia_valor_sistemas
    ]

    grafico_valorizacion = [
        serie("Valor QMS", totales["valor_qms"], COLOR["azul"], texto=format_clp(totales["valor_qms"])),
        serie("Valor Defontana", totales["valor_defontana"], COLOR["azul_claro"], texto=format_clp(totales["valor_defontana"])),
        serie("Valor físico contado", totales["valor_fisico"], COLOR["verde"], texto=format_clp(totales["valor_fisico"])),
    ]

    sin_diferencia = totales["articulos"] - totales["dif_costo"] - totales["dif_unidad"] - totales["sin_costo"]
    grafico_calidad = [
        serie("Costo y unidad coinciden", max(0, sin_diferencia), COLOR["verde"]),
        serie("Diferencia de costo", totales["dif_costo"], COLOR["ambar"]),
        serie("Diferencia de unidad", totales["dif_unidad"], COLOR["rojo"]),
        serie("Sin costo cargado", totales["sin_costo"], COLOR["gris"]),
    ]

    return render_template(
        "inventario/ajuste.html",
        items=visibles,
        totales=totales,
        q=busqueda,
        filtro=filtro,
        filtros_columna=filtros_columna,
        orden=orden,
        direccion=direccion,
        pagina=pagina,
        total_paginas=total_paginas,
        grafico_top=grafico_top,
        grafico_valorizacion=grafico_valorizacion,
        grafico_calidad=grafico_calidad,
    )


@bp.route("/ajuste.csv")
@require_permission("inventario", "ver")
def ajuste_csv():
    """Exporta el ajuste con los mismos filtros aplicados en pantalla."""
    items, _q, _fc, _filtro, _orden, _dir = _items_ajuste(request.args)

    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow([
        "Código", "Descripción", "Unidad QMS", "Unidad Defontana", "Unidades coinciden",
        "Costo unitario QMS", "Costo unitario Defontana", "Diferencia costo unitario",
        "Stock QMS", "Stock Defontana", "Stock físico",
        "Valor QMS", "Valor Defontana", "Diferencia valorización",
        "Ajuste físico vs QMS", "Categoría", "Línea de negocio", "Ubicación",
    ])
    for i in items:
        escritor.writerow([
            i.codigo, i.nombre or "", i.unidad_qms or "", i.unidad_defontana or "",
            "sí" if i.unidades_coinciden else "no",
            i.costo_unitario_qms if i.costo_unitario_qms is not None else "",
            i.costo_unitario_defontana if i.costo_unitario_defontana is not None else "",
            i.diferencia_costo_unitario if i.diferencia_costo_unitario is not None else "",
            i.cantidad_qms, i.cantidad_defontana,
            i.cantidad_fisica if i.contado else "",
            i.valor_qms, i.valor_defontana, i.diferencia_valor_sistemas,
            i.diferencia_valor_fisico if i.contado else "",
            i.categoria or "", i.linea_negocio or "", i.ubicacion or "",
        ])

    respuesta = make_response(salida.getvalue().encode("utf-8-sig"))
    respuesta.headers["Content-Type"] = "text/csv; charset=utf-8"
    respuesta.headers["Content-Disposition"] = (
        f"attachment; filename=ajuste-inventario-{date.today().isoformat()}.csv"
    )
    return respuesta


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
