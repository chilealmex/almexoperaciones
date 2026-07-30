from datetime import date

from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user

from app.contratos import bp
from app.contratos.forms import ContratoForm, ContratoGeneradoForm
from app.extensions import db
from app.models.cliente import Cliente
from app.models.contrato import ContratoCliente
from app.models.contrato_generado import ContratoGenerado
from app.utils.decorators import require_permission
from app.utils.storage import guardar_documento, listar_documentos
from app.utils.graficos import widget_seguro
from app.utils.paneles import panel_contratos
from app.utils.exportar import responder_excel, col, CLP, ENTERO, FECHA

MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _fecha_en_palabras(fecha):
    return f"{fecha.day} de {MESES_ES[fecha.month - 1]} de {fecha.year}"


# --- Contratos ---
# Los clientes se gestionan en Datos maestros (app/datos_maestros); aquí solo
# se cargan como opciones para el formulario de contrato.


def _cargar_clientes(form):
    form.cliente_id.choices = [
        (c.id, f"{c.razon_social} — {c.rut}")
        for c in Cliente.query.filter_by(activo=True).order_by(Cliente.razon_social).all()
    ]


def _stats_contratos():
    lista = ContratoCliente.query.order_by(ContratoCliente.fecha_termino).all()
    vigentes = [c for c in lista if c.estado == "vigente"]
    return lista, {
        "vigentes": len(vigentes),
        "por_vencer": sum(1 for c in lista if c.estado == "por_vencer"),
        "vencidos": sum(1 for c in lista if c.estado == "vencido"),
        "monto_vigente": sum(c.monto for c in vigentes),
    }


@bp.route("/")
@require_permission("contratos", "ver")
def resumen():
    from app.models.arriendo import ArriendoSalida, ArriendoEntrada

    lista, stats = _stats_contratos()
    contratos_por_vencer = [c for c in lista if c.estado == "por_vencer"]

    salidas = ArriendoSalida.query.all()
    entradas = ArriendoEntrada.query.all()
    salidas_activas = [s for s in salidas if s.estado in ("activo", "atrasado")]
    entradas_vigentes = [e for e in entradas if e.estado in ("vigente", "por_vencer")]
    stats_arriendos = {
        "salidas_activas": len(salidas_activas),
        "ingreso_por_periodo": sum(s.monto_periodo for s in salidas_activas),
        "entradas_vigentes": len(entradas_vigentes),
        "gasto_por_periodo": sum(e.monto_periodo for e in entradas_vigentes),
    }
    arriendos_entrada_por_vencer = [e for e in entradas if e.estado == "por_vencer"]
    panel = widget_seguro(panel_contratos, nombre="resumen de contratos")
    return render_template(
        "contratos/resumen.html",
        stats=stats,
        stats_arriendos=stats_arriendos,
        contratos_por_vencer=contratos_por_vencer,
        arriendos_entrada_por_vencer=arriendos_entrada_por_vencer,
        panel=panel,
    )


@bp.route("/lista")
@require_permission("contratos", "ver")
def contratos():
    lista, stats = _stats_contratos()
    return render_template("contratos/lista.html", contratos=lista, stats=stats)


ESTADOS_LEGIBLES = {
    "vigente": "Vigente",
    "por_vencer": "Por vencer",
    "vencido": "Vencido",
    "terminado": "Terminado",
}


@bp.route("/lista.xlsx")
@require_permission("contratos", "ver")
def contratos_excel():
    """Informe en Excel de los contratos con clientes."""
    lista, _stats = _stats_contratos()
    hoy = date.today()

    columnas = [
        col("N° contrato", ancho=18, total="texto"),
        col("Cliente", ancho=38),
        col("RUT cliente", ancho=15),
        col("Objeto", ancho=48),
        col("Fecha inicio", ancho=14, formato=FECHA),
        col("Fecha término", ancho=14, formato=FECHA),
        col("Días restantes", ancho=15, formato=ENTERO),
        col("Estado", ancho=14),
        col("Monto", ancho=16, formato=CLP, total="suma"),
        col("Moneda", ancho=10),
        col("Periodicidad", ancho=14),
        col("Responsable", ancho=26),
        col("Notas", ancho=40),
    ]
    filas = [
        [
            c.numero_contrato,
            c.cliente.razon_social if c.cliente else "",
            c.cliente.rut if c.cliente else "",
            c.objeto,
            c.fecha_inicio,
            c.fecha_termino,
            (c.fecha_termino - hoy).days,
            ESTADOS_LEGIBLES.get(c.estado, c.estado),
            c.monto,
            c.moneda,
            c.periodicidad_pago,
            c.usuario_responsable.nombre_completo if c.usuario_responsable else "",
            c.notas or "",
        ]
        for c in lista
    ]

    return responder_excel("contratos", "Contratos con clientes", columnas, filas)


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


# --- Generador de contratos de arriendo (plantilla Shaw Almex) ---


def _preparar_form_generado(form):
    form.cliente_id.choices = [
        (c.id, f"{c.razon_social} — {c.rut}")
        for c in Cliente.query.filter_by(activo=True).order_by(Cliente.razon_social).all()
    ]


def _guardar_datos_generado(form, contrato):
    contrato.cliente_id = form.cliente_id.data
    contrato.fecha_contrato = form.fecha_contrato.data
    contrato.correo_arrendador = form.correo_arrendador.data or None
    contrato.representante_nombre = form.representante_nombre.data.strip()
    contrato.representante_cedula = form.representante_cedula.data.strip()
    contrato.arrendatario_domicilio = form.arrendatario_domicilio.data.strip()
    contrato.arrendatario_correo = form.arrendatario_correo.data.strip()
    contrato.fiador_tipo = form.fiador_tipo.data
    contrato.fiador_nombre = form.fiador_nombre.data.strip()
    contrato.fiador_rut = form.fiador_rut.data.strip()
    contrato.fiador_domicilio = form.fiador_domicilio.data or None
    contrato.fiador_correo = form.fiador_correo.data or None
    contrato.fiador_representante = form.fiador_representante.data or None
    contrato.cotizacion_numero = form.cotizacion_numero.data.strip()
    contrato.cotizacion_fecha = form.cotizacion_fecha.data
    contrato.planta_ubicacion = form.planta_ubicacion.data.strip()
    contrato.deducible_uf = form.deducible_uf.data


@bp.route("/generados")
@require_permission("contratos", "ver")
def generados():
    lista = (
        ContratoGenerado.query.filter_by(empresa_id=current_user.empresa_id)
        .order_by(ContratoGenerado.creado_en.desc())
        .all()
    )
    return render_template("contratos/generados_lista.html", contratos=lista)


@bp.route("/generados/nuevo", methods=["GET", "POST"])
@require_permission("contratos", "editar")
def nuevo_generado():
    form = ContratoGeneradoForm()
    _preparar_form_generado(form)
    if not form.cliente_id.choices:
        flash("Primero debes crear un cliente en Datos maestros.", "warning")
        return redirect(url_for("datos_maestros.clientes"))

    if form.validate_on_submit():
        if form.fiador_tipo.data == "empresa" and not form.fiador_representante.data:
            flash("Si el fiador es una empresa, debes indicar su representante legal.", "danger")
            return render_template("contratos/generado_form.html", form=form, contrato=None)

        contrato = ContratoGenerado(empresa_id=current_user.empresa_id, creado_por_id=current_user.id)
        _guardar_datos_generado(form, contrato)
        db.session.add(contrato)
        db.session.commit()
        flash("Contrato generado correctamente. Revísalo y usa Imprimir para obtener el PDF.", "success")
        return redirect(url_for("contratos.ver_generado", contrato_id=contrato.id))

    return render_template("contratos/generado_form.html", form=form, contrato=None)


@bp.route("/generados/<int:contrato_id>/editar", methods=["GET", "POST"])
@require_permission("contratos", "editar")
def editar_generado(contrato_id):
    contrato = ContratoGenerado.query.filter_by(
        id=contrato_id, empresa_id=current_user.empresa_id
    ).first_or_404()
    form = ContratoGeneradoForm(obj=contrato)
    _preparar_form_generado(form)

    if form.validate_on_submit():
        if form.fiador_tipo.data == "empresa" and not form.fiador_representante.data:
            flash("Si el fiador es una empresa, debes indicar su representante legal.", "danger")
            return render_template("contratos/generado_form.html", form=form, contrato=contrato)

        _guardar_datos_generado(form, contrato)
        db.session.commit()
        flash("Contrato actualizado correctamente.", "success")
        return redirect(url_for("contratos.ver_generado", contrato_id=contrato.id))

    return render_template("contratos/generado_form.html", form=form, contrato=contrato)


@bp.route("/generados/<int:contrato_id>")
@require_permission("contratos", "ver")
def ver_generado(contrato_id):
    contrato = ContratoGenerado.query.filter_by(
        id=contrato_id, empresa_id=current_user.empresa_id
    ).first_or_404()
    return render_template(
        "contratos/generado_documento.html",
        c=contrato,
        fecha_contrato_palabras=_fecha_en_palabras(contrato.fecha_contrato),
        cotizacion_fecha_palabras=_fecha_en_palabras(contrato.cotizacion_fecha),
    )
