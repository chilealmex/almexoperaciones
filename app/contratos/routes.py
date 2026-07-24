from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user

from app.contratos import bp
from app.contratos.forms import ClienteForm, ContratoForm
from app.extensions import db
from app.models.cliente import Cliente
from app.models.contrato import ContratoCliente
from app.utils.decorators import require_permission
from app.utils.storage import guardar_documento, listar_documentos


# --- Clientes ---


@bp.route("/clientes")
@require_permission("contratos", "ver")
def clientes():
    lista = Cliente.query.order_by(Cliente.razon_social).all()
    return render_template("contratos/clientes_lista.html", clientes=lista)


@bp.route("/clientes/nuevo", methods=["GET", "POST"])
@require_permission("contratos", "editar")
def nuevo_cliente():
    form = ClienteForm()
    if form.validate_on_submit():
        if Cliente.query.filter_by(rut=form.rut.data.strip()).first():
            flash("Ya existe un cliente con ese RUT.", "danger")
            return render_template("contratos/cliente_form.html", form=form, cliente=None)

        cliente = Cliente(
            empresa_id=current_user.empresa_id,
            rut=form.rut.data.strip(),
            razon_social=form.razon_social.data.strip(),
            giro=form.giro.data,
            direccion=form.direccion.data,
            comuna=form.comuna.data,
            ciudad=form.ciudad.data,
            telefono=form.telefono.data,
            email=form.email.data,
            contacto_nombre=form.contacto_nombre.data,
            activo=form.activo.data,
        )
        db.session.add(cliente)
        db.session.commit()
        flash("Cliente creado correctamente.", "success")
        return redirect(url_for("contratos.clientes"))

    return render_template("contratos/cliente_form.html", form=form, cliente=None)


@bp.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
@require_permission("contratos", "editar")
def editar_cliente(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    form = ClienteForm(obj=cliente)
    if form.validate_on_submit():
        duplicado = Cliente.query.filter(
            Cliente.rut == form.rut.data.strip(), Cliente.id != cliente.id
        ).first()
        if duplicado:
            flash("Ya existe otro cliente con ese RUT.", "danger")
            return render_template("contratos/cliente_form.html", form=form, cliente=cliente)

        form.populate_obj(cliente)
        cliente.rut = form.rut.data.strip()
        db.session.commit()
        flash("Cliente actualizado correctamente.", "success")
        return redirect(url_for("contratos.clientes"))

    return render_template("contratos/cliente_form.html", form=form, cliente=cliente)


# --- Contratos ---


def _cargar_clientes(form):
    form.cliente_id.choices = [
        (c.id, c.razon_social) for c in Cliente.query.filter_by(activo=True).order_by(Cliente.razon_social).all()
    ]


@bp.route("/")
@require_permission("contratos", "ver")
def contratos():
    lista = ContratoCliente.query.order_by(ContratoCliente.fecha_termino).all()
    vigentes = [c for c in lista if c.estado == "vigente"]
    stats = {
        "vigentes": len(vigentes),
        "por_vencer": sum(1 for c in lista if c.estado == "por_vencer"),
        "vencidos": sum(1 for c in lista if c.estado == "vencido"),
        "monto_vigente": sum(c.monto for c in vigentes),
    }
    return render_template("contratos/lista.html", contratos=lista, stats=stats)


@bp.route("/nuevo", methods=["GET", "POST"])
@require_permission("contratos", "editar")
def nuevo_contrato():
    form = ContratoForm()
    _cargar_clientes(form)
    if form.validate_on_submit():
        if form.fecha_termino.data <= form.fecha_inicio.data:
            flash("La fecha de término debe ser posterior a la fecha de inicio.", "danger")
            return render_template("contratos/form.html", form=form, contrato=None)

        contrato = ContratoCliente(
            empresa_id=current_user.empresa_id,
            cliente_id=form.cliente_id.data,
            numero_contrato=form.numero_contrato.data.strip(),
            objeto=form.objeto.data.strip(),
            fecha_inicio=form.fecha_inicio.data,
            fecha_termino=form.fecha_termino.data,
            monto=form.monto.data,
            periodicidad_pago=form.periodicidad_pago.data,
            dias_alerta_vencimiento=form.dias_alerta_vencimiento.data,
            usuario_responsable_id=current_user.id,
            notas=form.notas.data,
        )
        db.session.add(contrato)
        db.session.commit()
        flash("Contrato creado correctamente.", "success")
        return redirect(url_for("contratos.contratos"))

    return render_template("contratos/form.html", form=form, contrato=None)


@bp.route("/<int:contrato_id>")
@require_permission("contratos", "ver")
def ver_contrato(contrato_id):
    contrato = ContratoCliente.query.get_or_404(contrato_id)
    documentos = listar_documentos("contrato_cliente", contrato.id)
    return render_template("contratos/ver.html", contrato=contrato, documentos=documentos)


@bp.route("/<int:contrato_id>/editar", methods=["GET", "POST"])
@require_permission("contratos", "editar")
def editar_contrato(contrato_id):
    contrato = ContratoCliente.query.get_or_404(contrato_id)
    form = ContratoForm(obj=contrato)
    _cargar_clientes(form)

    if form.validate_on_submit():
        if form.fecha_termino.data <= form.fecha_inicio.data:
            flash("La fecha de término debe ser posterior a la fecha de inicio.", "danger")
            return render_template("contratos/form.html", form=form, contrato=contrato)

        form.populate_obj(contrato)
        db.session.commit()
        flash("Contrato actualizado correctamente.", "success")
        return redirect(url_for("contratos.ver_contrato", contrato_id=contrato.id))

    return render_template("contratos/form.html", form=form, contrato=contrato)


@bp.route("/<int:contrato_id>/renovar", methods=["POST"])
@require_permission("contratos", "editar")
def renovar_contrato(contrato_id):
    original = ContratoCliente.query.get_or_404(contrato_id)
    nueva_fecha_inicio = original.fecha_termino
    duracion = original.fecha_termino - original.fecha_inicio
    nuevo = ContratoCliente(
        empresa_id=original.empresa_id,
        cliente_id=original.cliente_id,
        numero_contrato=f"{original.numero_contrato}-R",
        objeto=original.objeto,
        fecha_inicio=nueva_fecha_inicio,
        fecha_termino=nueva_fecha_inicio + duracion,
        monto=original.monto,
        periodicidad_pago=original.periodicidad_pago,
        dias_alerta_vencimiento=original.dias_alerta_vencimiento,
        usuario_responsable_id=current_user.id,
        contrato_anterior_id=original.id,
    )
    db.session.add(nuevo)
    db.session.commit()
    flash("Contrato renovado. Se creó un nuevo contrato vinculado al anterior.", "success")
    return redirect(url_for("contratos.ver_contrato", contrato_id=nuevo.id))


@bp.route("/<int:contrato_id>/terminar", methods=["POST"])
@require_permission("contratos", "editar")
def terminar_contrato(contrato_id):
    contrato = ContratoCliente.query.get_or_404(contrato_id)
    contrato.terminado_manualmente = True
    db.session.commit()
    flash("Contrato marcado como terminado.", "info")
    return redirect(url_for("contratos.ver_contrato", contrato_id=contrato.id))


@bp.route("/<int:contrato_id>/documentos", methods=["POST"])
@require_permission("contratos", "editar")
def subir_documento(contrato_id):
    contrato = ContratoCliente.query.get_or_404(contrato_id)
    archivo = request.files.get("archivo")
    if archivo and archivo.filename:
        guardar_documento("contrato_cliente", contrato.id, archivo, current_user.id)
        flash("Documento adjuntado correctamente.", "success")
    return redirect(url_for("contratos.ver_contrato", contrato_id=contrato.id))
