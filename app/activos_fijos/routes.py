from datetime import date

from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user

from app.activos_fijos import bp
from app.activos_fijos.forms import ActivoFijoForm, BajaActivoForm
from app.extensions import db
from app.models.activo_fijo import ActivoFijo
from app.utils.decorators import require_permission
from app.utils.storage import guardar_documento, listar_documentos


@bp.route("/")
@require_permission("activos_fijos", "ver")
def activos():
    lista = ActivoFijo.query.order_by(ActivoFijo.codigo_activo).all()
    return render_template("activos_fijos/lista.html", activos=lista)


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
    if form.validate_on_submit():
        if ActivoFijo.query.filter_by(codigo_activo=form.codigo_activo.data.strip()).first():
            flash("Ya existe un activo con ese código.", "danger")
            return render_template("activos_fijos/form.html", form=form, activo=None)

        activo = ActivoFijo(
            empresa_id=current_user.empresa_id,
            codigo_activo=form.codigo_activo.data.strip(),
            nombre=form.nombre.data.strip(),
            descripcion=form.descripcion.data,
            categoria=form.categoria.data,
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
    if form.validate_on_submit():
        duplicado = ActivoFijo.query.filter(
            ActivoFijo.codigo_activo == form.codigo_activo.data.strip(), ActivoFijo.id != activo.id
        ).first()
        if duplicado:
            flash("Ya existe otro activo con ese código.", "danger")
            return render_template("activos_fijos/form.html", form=form, activo=activo)

        form.populate_obj(activo)
        activo.codigo_activo = form.codigo_activo.data.strip()
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
