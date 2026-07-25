from datetime import date, datetime, timezone

from flask import render_template, redirect, url_for, flash, request, send_from_directory, current_app, abort
from flask_login import current_user

from app.arriendos import bp
from app.arriendos.forms import (
    ArriendoSalidaForm,
    ArriendoEntradaForm,
    ProveedorForm,
    DevolucionForm,
    PagoForm,
    FirmaClienteForm,
)
from app.extensions import db
from app.models.activo_fijo import ActivoFijo
from app.models.cliente import Cliente, Proveedor
from app.models.arriendo import (
    ArriendoSalida,
    FacturacionArriendoSalida,
    ArriendoEntrada,
    PagoArriendoEntrada,
)
from app.utils.decorators import require_permission
from app.utils.storage import guardar_documento, listar_documentos, guardar_firma_png


@bp.route("/")
@require_permission("contratos", "ver")
def index():
    salidas = ArriendoSalida.query.order_by(ArriendoSalida.fecha_inicio.desc()).all()
    entradas = ArriendoEntrada.query.order_by(ArriendoEntrada.fecha_termino).all()

    salidas_activas = [s for s in salidas if s.estado in ("activo", "atrasado")]
    entradas_vigentes = [e for e in entradas if e.estado in ("vigente", "por_vencer")]
    stats = {
        "salidas_activas": len(salidas_activas),
        "ingreso_por_periodo": sum(s.monto_periodo for s in salidas_activas),
        "entradas_vigentes": len(entradas_vigentes),
        "gasto_por_periodo": sum(e.monto_periodo for e in entradas_vigentes),
    }
    return render_template("arriendos/index.html", salidas=salidas, entradas=entradas, stats=stats)


# --- Arriendo de salida: la empresa arrienda A un cliente ---


def _cargar_opciones_salida(form):
    form.activo_fijo_id.choices = [
        (a.id, f"{a.codigo_activo} - {a.nombre}")
        for a in ActivoFijo.query.filter_by(es_arrendable=True, estado="activo").order_by(ActivoFijo.codigo_activo).all()
    ]
    form.cliente_id.choices = [
        (c.id, c.razon_social) for c in Cliente.query.filter_by(activo=True).order_by(Cliente.razon_social).all()
    ]


@bp.route("/salida/nuevo", methods=["GET", "POST"])
@require_permission("contratos", "editar")
def nuevo_arriendo_salida():
    form = ArriendoSalidaForm()
    _cargar_opciones_salida(form)

    if form.validate_on_submit():
        if form.fecha_termino_prevista.data <= form.fecha_inicio.data:
            flash("La fecha de término debe ser posterior a la fecha de inicio.", "danger")
            return render_template("arriendos/salida_form.html", form=form)

        activo = db.session.get(ActivoFijo, form.activo_fijo_id.data)
        if activo is None or not activo.es_arrendable:
            flash("El activo seleccionado no está disponible para arriendo.", "danger")
            return render_template("arriendos/salida_form.html", form=form)
        if activo.arrendado_actualmente:
            flash("Este activo ya está arrendado actualmente. Debes registrar su devolución antes de arrendarlo de nuevo.", "danger")
            return render_template("arriendos/salida_form.html", form=form)

        arriendo = ArriendoSalida(
            empresa_id=current_user.empresa_id,
            activo_fijo_id=form.activo_fijo_id.data,
            cliente_id=form.cliente_id.data,
            fecha_inicio=form.fecha_inicio.data,
            fecha_termino_prevista=form.fecha_termino_prevista.data,
            monto_periodo=form.monto_periodo.data,
            periodicidad=form.periodicidad.data,
            condiciones=form.condiciones.data,
        )
        db.session.add(arriendo)
        db.session.commit()
        flash("Arriendo de salida registrado correctamente.", "success")
        return redirect(url_for("arriendos.ver_arriendo_salida", arriendo_id=arriendo.id))

    return render_template("arriendos/salida_form.html", form=form)


@bp.route("/salida/<int:arriendo_id>")
@require_permission("contratos", "ver")
def ver_arriendo_salida(arriendo_id):
    arriendo = ArriendoSalida.query.get_or_404(arriendo_id)
    devolucion_form = DevolucionForm()
    pago_form = PagoForm()
    firma_form = FirmaClienteForm()
    documentos = listar_documentos("arriendo_salida", arriendo.id)
    return render_template(
        "arriendos/salida_ver.html",
        arriendo=arriendo,
        devolucion_form=devolucion_form,
        pago_form=pago_form,
        firma_form=firma_form,
        documentos=documentos,
    )


@bp.route("/salida/<int:arriendo_id>/documentos", methods=["POST"])
@require_permission("contratos", "editar")
def subir_documento_salida(arriendo_id):
    arriendo = ArriendoSalida.query.get_or_404(arriendo_id)
    archivo = request.files.get("archivo")
    if archivo and archivo.filename:
        guardar_documento("arriendo_salida", arriendo.id, archivo, current_user.id)
        flash("Documento adjuntado correctamente.", "success")
    return redirect(url_for("arriendos.ver_arriendo_salida", arriendo_id=arriendo.id))


@bp.route("/salida/<int:arriendo_id>/firmar", methods=["POST"])
@require_permission("contratos", "editar")
def firmar_arriendo_salida(arriendo_id):
    arriendo = ArriendoSalida.query.get_or_404(arriendo_id)
    form = FirmaClienteForm()
    if form.validate_on_submit():
        try:
            ruta = guardar_firma_png("arriendo_salida", arriendo.id, form.firma_imagen.data)
        except ValueError:
            flash("No se pudo procesar la firma. Intenta dibujarla nuevamente.", "danger")
            return redirect(url_for("arriendos.ver_arriendo_salida", arriendo_id=arriendo.id))

        arriendo.firma_cliente_nombre = form.firma_cliente_nombre.data.strip()
        arriendo.firma_cliente_ruta = ruta
        arriendo.firma_cliente_en = datetime.now(timezone.utc)
        arriendo.firma_cliente_ip = request.remote_addr
        db.session.commit()
        flash("Firma registrada correctamente. Esta firma es una confirmación en pantalla, no una firma electrónica avanzada con validez legal plena.", "success")
    else:
        flash("Debes ingresar el nombre de quien firma y dibujar la firma.", "danger")
    return redirect(url_for("arriendos.ver_arriendo_salida", arriendo_id=arriendo.id))


@bp.route("/salida/<int:arriendo_id>/firma-imagen")
@require_permission("contratos", "ver")
def ver_firma_salida(arriendo_id):
    arriendo = ArriendoSalida.query.get_or_404(arriendo_id)
    if not arriendo.firma_cliente_ruta:
        abort(404)
    if current_app.config["STORAGE_BACKEND"] == "r2":
        from app.utils.storage import _r2_client

        url = _r2_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": current_app.config["R2_BUCKET"], "Key": arriendo.firma_cliente_ruta},
            ExpiresIn=300,
        )
        return redirect(url)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], arriendo.firma_cliente_ruta)


@bp.route("/salida/<int:arriendo_id>/devolver", methods=["POST"])
@require_permission("contratos", "editar")
def devolver_arriendo_salida(arriendo_id):
    arriendo = ArriendoSalida.query.get_or_404(arriendo_id)
    form = DevolucionForm()
    if form.validate_on_submit():
        if form.fecha_devolucion_real.data < arriendo.fecha_inicio:
            flash("La fecha de devolución no puede ser anterior al inicio del arriendo.", "danger")
        else:
            arriendo.fecha_devolucion_real = form.fecha_devolucion_real.data
            db.session.commit()
            flash("Devolución registrada correctamente.", "success")
    return redirect(url_for("arriendos.ver_arriendo_salida", arriendo_id=arriendo.id))


@bp.route("/salida/<int:arriendo_id>/facturacion", methods=["POST"])
@require_permission("contratos", "editar")
def nueva_facturacion_salida(arriendo_id):
    arriendo = ArriendoSalida.query.get_or_404(arriendo_id)
    form = PagoForm()
    if form.validate_on_submit():
        facturacion = FacturacionArriendoSalida(
            arriendo_salida_id=arriendo.id,
            periodo=form.periodo.data.strip(),
            monto=form.monto.data,
            numero_documento=form.numero_documento.data,
        )
        db.session.add(facturacion)
        db.session.commit()
        flash("Cobro registrado correctamente.", "success")
    return redirect(url_for("arriendos.ver_arriendo_salida", arriendo_id=arriendo.id))


@bp.route("/salida/facturacion/<int:facturacion_id>/pagar", methods=["POST"])
@require_permission("contratos", "editar")
def marcar_facturacion_pagada(facturacion_id):
    facturacion = FacturacionArriendoSalida.query.get_or_404(facturacion_id)
    facturacion.estado_pago = "pagado"
    facturacion.fecha_pago = date.today()
    db.session.commit()
    flash("Cobro marcado como pagado.", "success")
    return redirect(url_for("arriendos.ver_arriendo_salida", arriendo_id=facturacion.arriendo_salida_id))


# --- Proveedores (para arriendo de entrada) ---


@bp.route("/proveedores")
@require_permission("contratos", "ver")
def proveedores():
    lista = Proveedor.query.order_by(Proveedor.razon_social).all()
    return render_template("arriendos/proveedores_lista.html", proveedores=lista)


@bp.route("/proveedores/nuevo", methods=["GET", "POST"])
@require_permission("contratos", "editar")
def nuevo_proveedor():
    form = ProveedorForm()
    if form.validate_on_submit():
        if Proveedor.query.filter_by(rut=form.rut.data.strip()).first():
            flash("Ya existe un proveedor con ese RUT.", "danger")
            return render_template("arriendos/proveedor_form.html", form=form)

        proveedor = Proveedor(
            empresa_id=current_user.empresa_id,
            rut=form.rut.data.strip(),
            razon_social=form.razon_social.data.strip(),
            giro=form.giro.data,
            direccion=form.direccion.data,
            telefono=form.telefono.data,
            email=form.email.data,
            contacto_nombre=form.contacto_nombre.data,
        )
        db.session.add(proveedor)
        db.session.commit()
        flash("Proveedor creado correctamente.", "success")
        return redirect(url_for("arriendos.proveedores"))

    return render_template("arriendos/proveedor_form.html", form=form)


# --- Arriendo de entrada: la empresa arrienda DE un proveedor ---


def _cargar_opciones_entrada(form):
    form.proveedor_id.choices = [
        (p.id, p.razon_social) for p in Proveedor.query.filter_by(activo=True).order_by(Proveedor.razon_social).all()
    ]


@bp.route("/entrada/nuevo", methods=["GET", "POST"])
@require_permission("contratos", "editar")
def nuevo_arriendo_entrada():
    form = ArriendoEntradaForm()
    _cargar_opciones_entrada(form)

    if form.validate_on_submit():
        if form.fecha_termino.data <= form.fecha_inicio.data:
            flash("La fecha de término debe ser posterior a la fecha de inicio.", "danger")
            return render_template("arriendos/entrada_form.html", form=form)

        arriendo = ArriendoEntrada(
            empresa_id=current_user.empresa_id,
            proveedor_id=form.proveedor_id.data,
            descripcion_activo=form.descripcion_activo.data.strip(),
            numero_contrato=form.numero_contrato.data,
            fecha_inicio=form.fecha_inicio.data,
            fecha_termino=form.fecha_termino.data,
            monto_periodo=form.monto_periodo.data,
            periodicidad=form.periodicidad.data,
            dias_alerta_vencimiento=form.dias_alerta_vencimiento.data,
            ubicacion_uso=form.ubicacion_uso.data,
            responsable_id=current_user.id,
        )
        db.session.add(arriendo)
        db.session.commit()
        flash("Arriendo de entrada registrado correctamente.", "success")
        return redirect(url_for("arriendos.ver_arriendo_entrada", arriendo_id=arriendo.id))

    return render_template("arriendos/entrada_form.html", form=form)


@bp.route("/entrada/<int:arriendo_id>")
@require_permission("contratos", "ver")
def ver_arriendo_entrada(arriendo_id):
    arriendo = ArriendoEntrada.query.get_or_404(arriendo_id)
    pago_form = PagoForm()
    return render_template("arriendos/entrada_ver.html", arriendo=arriendo, pago_form=pago_form)


@bp.route("/entrada/<int:arriendo_id>/terminar", methods=["POST"])
@require_permission("contratos", "editar")
def terminar_arriendo_entrada(arriendo_id):
    arriendo = ArriendoEntrada.query.get_or_404(arriendo_id)
    arriendo.terminado_manualmente = True
    db.session.commit()
    flash("Arriendo de entrada marcado como terminado.", "info")
    return redirect(url_for("arriendos.ver_arriendo_entrada", arriendo_id=arriendo.id))


@bp.route("/entrada/<int:arriendo_id>/pago", methods=["POST"])
@require_permission("contratos", "editar")
def nuevo_pago_entrada(arriendo_id):
    arriendo = ArriendoEntrada.query.get_or_404(arriendo_id)
    form = PagoForm()
    if form.validate_on_submit():
        pago = PagoArriendoEntrada(
            arriendo_entrada_id=arriendo.id,
            periodo=form.periodo.data.strip(),
            monto=form.monto.data,
            fecha_pago_programada=date.today(),
            numero_documento=form.numero_documento.data,
        )
        db.session.add(pago)
        db.session.commit()
        flash("Pago programado registrado correctamente.", "success")
    return redirect(url_for("arriendos.ver_arriendo_entrada", arriendo_id=arriendo.id))


@bp.route("/entrada/pago/<int:pago_id>/pagar", methods=["POST"])
@require_permission("contratos", "editar")
def marcar_pago_realizado(pago_id):
    pago = PagoArriendoEntrada.query.get_or_404(pago_id)
    pago.estado_pago = "pagado"
    pago.fecha_pago_real = date.today()
    db.session.commit()
    flash("Pago marcado como realizado.", "success")
    return redirect(url_for("arriendos.ver_arriendo_entrada", arriendo_id=pago.arriendo_entrada_id))
