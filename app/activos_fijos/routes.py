from datetime import date

from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user

from app.activos_fijos import bp
from app.activos_fijos.forms import ActivoFijoForm, BajaActivoForm, CategoriaActivoForm
from app.extensions import db
from app.models.activo_fijo import ActivoFijo, CategoriaActivo
from app.utils.decorators import require_permission
from app.utils.storage import guardar_documento, listar_documentos
from app.utils.graficos import widget_seguro
from app.utils.paneles import panel_activos


def _stats_activos():
    lista = ActivoFijo.query.order_by(ActivoFijo.codigo_activo).all()
    activos_vigentes = [a for a in lista if a.estado == "activo"]
    return lista, {
        "total_activos": len(activos_vigentes),
        "valor_libro_total": sum(a.valor_libro for a in activos_vigentes),
        "depreciacion_mensual_total": sum(a.depreciacion_mensual for a in activos_vigentes),
        "arrendados": sum(1 for a in activos_vigentes if a.es_arrendable and a.arrendado_actualmente),
    }


def _cargar_categorias(form, valor_actual=None):
    nombres = [
        c.nombre
        for c in CategoriaActivo.query.filter_by(empresa_id=current_user.empresa_id, activa=True)
        .order_by(CategoriaActivo.nombre)
        .all()
    ]
    if valor_actual and valor_actual not in nombres:
        nombres.append(valor_actual)  # categoría histórica que ya no está activa
    form.categoria.choices = [("", "— Sin categoría —")] + [(n, n) for n in nombres]


@bp.route("/")
@require_permission("activos_fijos", "ver")
def resumen():
    _lista, stats = _stats_activos()
    panel = widget_seguro(panel_activos, nombre="resumen de activos fijos")
    return render_template("activos_fijos/resumen.html", stats=stats, panel=panel)


@bp.route("/lista")
@require_permission("activos_fijos", "ver")
def activos():
    lista, stats = _stats_activos()
    return render_template("activos_fijos/lista.html", activos=lista, stats=stats)


@bp.route("/depreciacion")
@require_permission("activos_fijos", "ver")
def depreciacion():
    activos_activos = (
        ActivoFijo.query.filter_by(estado="activo").order_by(ActivoFijo.codigo_activo).all()
    )
    filas = [a for a in activos_activos if a.depreciacion_mensual > 0]
    total_arriendo = sum(a.depreciacion_mensual for a in filas if a.centro_costo == "Arriendo")
    total_administracion = sum(
        a.depreciacion_mensual for a in filas if a.centro_costo == "Administración"
    )
    return render_template(
        "activos_fijos/depreciacion.html",
        activos=filas,
        total_arriendo=total_arriendo,
        total_administracion=total_administracion,
    )


@bp.route("/nuevo", methods=["GET", "POST"])
@require_permission("activos_fijos", "editar")
def nuevo_activo():
    form = ActivoFijoForm()
    _cargar_categorias(form)
    if form.validate_on_submit():
        if ActivoFijo.query.filter_by(codigo_activo=form.codigo_activo.data.strip()).first():
            flash("Ya existe un activo con ese código.", "danger")
            return render_template("activos_fijos/form.html", form=form, activo=None)

        activo = ActivoFijo(
            empresa_id=current_user.empresa_id,
            codigo_activo=form.codigo_activo.data.strip(),
            nombre=form.nombre.data.strip(),
            descripcion=form.descripcion.data,
            categoria=form.categoria.data or None,
            fecha_compra=form.fecha_compra.data,
            valor_compra=form.valor_compra.data,
            valor_residual=form.valor_residual.data,
            vida_util_meses=form.vida_util_meses.data,
            ubicacion=form.ubicacion.data,
            numero_factura_compra=form.numero_factura_compra.data,
            es_arrendable=form.es_arrendable.data,
            responsable_id=current_user.id,
        )
        db.session.add(activo)
        db.session.commit()
        flash("Activo fijo creado correctamente.", "success")
        return redirect(url_for("activos_fijos.activos"))

    return render_template("activos_fijos/form.html", form=form, activo=None)


@bp.route("/<int:activo_id>")
@require_permission("activos_fijos", "ver")
def ver_activo(activo_id):
    activo = ActivoFijo.query.get_or_404(activo_id)
    documentos = listar_documentos("activo_fijo", activo.id)
    baja_form = BajaActivoForm()
    return render_template("activos_fijos/ver.html", activo=activo, documentos=documentos, baja_form=baja_form)


@bp.route("/<int:activo_id>/editar", methods=["GET", "POST"])
@require_permission("activos_fijos", "editar")
def editar_activo(activo_id):
    activo = ActivoFijo.query.get_or_404(activo_id)
    form = ActivoFijoForm(obj=activo)
    _cargar_categorias(form, valor_actual=activo.categoria)
    if form.validate_on_submit():
        duplicado = ActivoFijo.query.filter(
            ActivoFijo.codigo_activo == form.codigo_activo.data.strip(), ActivoFijo.id != activo.id
        ).first()
        if duplicado:
            flash("Ya existe otro activo con ese código.", "danger")
            return render_template("activos_fijos/form.html", form=form, activo=activo)

        form.populate_obj(activo)
        activo.codigo_activo = form.codigo_activo.data.strip()
        activo.categoria = form.categoria.data or None
        db.session.commit()
        flash("Activo fijo actualizado correctamente.", "success")
        return redirect(url_for("activos_fijos.ver_activo", activo_id=activo.id))

    return render_template("activos_fijos/form.html", form=form, activo=activo)


@bp.route("/<int:activo_id>/baja", methods=["POST"])
@require_permission("activos_fijos", "editar")
def dar_de_baja(activo_id):
    activo = ActivoFijo.query.get_or_404(activo_id)
    form = BajaActivoForm()
    if activo.arrendado_actualmente:
        flash("No se puede dar de baja un activo que está arrendado actualmente.", "danger")
        return redirect(url_for("activos_fijos.ver_activo", activo_id=activo.id))

    if form.validate_on_submit():
        activo.estado = form.estado.data
        activo.motivo_baja = form.motivo_baja.data
        activo.fecha_baja = date.today()
        db.session.commit()
        flash("Activo dado de baja correctamente.", "info")
    else:
        flash("Debes indicar el motivo de la baja.", "danger")

    return redirect(url_for("activos_fijos.ver_activo", activo_id=activo.id))


@bp.route("/<int:activo_id>/documentos", methods=["POST"])
@require_permission("activos_fijos", "editar")
def subir_documento(activo_id):
    activo = ActivoFijo.query.get_or_404(activo_id)
    archivo = request.files.get("archivo")
    if archivo and archivo.filename:
        guardar_documento("activo_fijo", activo.id, archivo, current_user.id)
        flash("Documento adjuntado correctamente.", "success")
    return redirect(url_for("activos_fijos.ver_activo", activo_id=activo.id))


# --- Categorías de activo (parametrizables) ---


@bp.route("/categorias")
@require_permission("activos_fijos", "ver")
def categorias():
    lista = (
        CategoriaActivo.query.filter_by(empresa_id=current_user.empresa_id)
        .order_by(CategoriaActivo.nombre)
        .all()
    )
    conteo_uso = {
        c.nombre: ActivoFijo.query.filter_by(empresa_id=current_user.empresa_id, categoria=c.nombre).count()
        for c in lista
    }
    return render_template("activos_fijos/categorias.html", categorias=lista, conteo_uso=conteo_uso)


@bp.route("/categorias/nueva", methods=["GET", "POST"])
@require_permission("activos_fijos", "editar")
def nueva_categoria():
    form = CategoriaActivoForm()
    if form.validate_on_submit():
        nombre = form.nombre.data.strip()
        existe = CategoriaActivo.query.filter_by(empresa_id=current_user.empresa_id, nombre=nombre).first()
        if existe:
            flash("Ya existe una categoría con ese nombre.", "danger")
            return render_template("activos_fijos/categoria_form.html", form=form, categoria=None)

        categoria = CategoriaActivo(
            empresa_id=current_user.empresa_id,
            nombre=nombre,
            descripcion=form.descripcion.data,
            activa=form.activa.data,
        )
        db.session.add(categoria)
        db.session.commit()
        flash("Categoría creada correctamente.", "success")
        return redirect(url_for("activos_fijos.categorias"))

    return render_template("activos_fijos/categoria_form.html", form=form, categoria=None)


@bp.route("/categorias/<int:categoria_id>/editar", methods=["GET", "POST"])
@require_permission("activos_fijos", "editar")
def editar_categoria(categoria_id):
    categoria = CategoriaActivo.query.filter_by(
        id=categoria_id, empresa_id=current_user.empresa_id
    ).first_or_404()
    form = CategoriaActivoForm(obj=categoria)

    if form.validate_on_submit():
        nombre = form.nombre.data.strip()
        duplicada = CategoriaActivo.query.filter(
            CategoriaActivo.empresa_id == current_user.empresa_id,
            CategoriaActivo.nombre == nombre,
            CategoriaActivo.id != categoria.id,
        ).first()
        if duplicada:
            flash("Ya existe otra categoría con ese nombre.", "danger")
            return render_template("activos_fijos/categoria_form.html", form=form, categoria=categoria)

        nombre_anterior = categoria.nombre
        categoria.nombre = nombre
        categoria.descripcion = form.descripcion.data
        categoria.activa = form.activa.data

        if nombre_anterior != nombre:
            # mantener consistencia en los activos que ya usaban el nombre anterior
            ActivoFijo.query.filter_by(empresa_id=current_user.empresa_id, categoria=nombre_anterior).update(
                {"categoria": nombre}
            )
        db.session.commit()
        flash("Categoría actualizada correctamente.", "success")
        return redirect(url_for("activos_fijos.categorias"))

    return render_template("activos_fijos/categoria_form.html", form=form, categoria=categoria)


@bp.route("/categorias/<int:categoria_id>/eliminar", methods=["POST"])
@require_permission("activos_fijos", "editar")
def eliminar_categoria(categoria_id):
    categoria = CategoriaActivo.query.filter_by(
        id=categoria_id, empresa_id=current_user.empresa_id
    ).first_or_404()
    en_uso = ActivoFijo.query.filter_by(
        empresa_id=current_user.empresa_id, categoria=categoria.nombre
    ).count()
    if en_uso:
        flash(
            f"No se puede eliminar: hay {en_uso} activo(s) usando esta categoría. Puedes desactivarla en su lugar.",
            "danger",
        )
    else:
        db.session.delete(categoria)
        db.session.commit()
        flash("Categoría eliminada correctamente.", "info")
    return redirect(url_for("activos_fijos.categorias"))
