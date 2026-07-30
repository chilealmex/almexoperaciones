from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user

from app.datos_maestros import bp
from app.datos_maestros.forms import ClienteForm, ProveedorForm, ImportarExcelForm
from app.extensions import db
from app.models.cliente import Cliente, Proveedor
from app.utils.decorators import require_permission
from app.utils.exportar import responder_excel, col, ENTERO
from app.utils.importar_maestros import (
    importar_clientes,
    importar_proveedores,
    COLUMNAS_CLIENTES,
    COLUMNAS_PROVEEDORES,
)


@bp.route("/")
@require_permission("datos_maestros", "ver")
def resumen():
    total_clientes = Cliente.query.filter_by(empresa_id=current_user.empresa_id).count()
    clientes_activos = Cliente.query.filter_by(empresa_id=current_user.empresa_id, activo=True).count()
    total_proveedores = Proveedor.query.filter_by(empresa_id=current_user.empresa_id).count()
    proveedores_activos = Proveedor.query.filter_by(empresa_id=current_user.empresa_id, activo=True).count()
    return render_template(
        "datos_maestros/resumen.html",
        total_clientes=total_clientes,
        clientes_activos=clientes_activos,
        total_proveedores=total_proveedores,
        proveedores_activos=proveedores_activos,
    )


# --- Clientes ---


@bp.route("/clientes")
@require_permission("datos_maestros", "ver")
def clientes():
    lista = Cliente.query.filter_by(empresa_id=current_user.empresa_id).order_by(Cliente.razon_social).all()
    return render_template("datos_maestros/clientes_lista.html", clientes=lista)


@bp.route("/clientes/nuevo", methods=["GET", "POST"])
@require_permission("datos_maestros", "editar")
def nuevo_cliente():
    form = ClienteForm()
    if form.validate_on_submit():
        if Cliente.query.filter_by(rut=form.rut.data.strip()).first():
            flash("Ya existe un cliente con ese RUT.", "danger")
            return render_template("datos_maestros/cliente_form.html", form=form, cliente=None)

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
        return redirect(url_for("datos_maestros.clientes"))

    return render_template("datos_maestros/cliente_form.html", form=form, cliente=None)


@bp.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
@require_permission("datos_maestros", "editar")
def editar_cliente(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    form = ClienteForm(obj=cliente)
    if form.validate_on_submit():
        duplicado = Cliente.query.filter(
            Cliente.rut == form.rut.data.strip(), Cliente.id != cliente.id
        ).first()
        if duplicado:
            flash("Ya existe otro cliente con ese RUT.", "danger")
            return render_template("datos_maestros/cliente_form.html", form=form, cliente=cliente)

        form.populate_obj(cliente)
        cliente.rut = form.rut.data.strip()
        db.session.commit()
        flash("Cliente actualizado correctamente.", "success")
        return redirect(url_for("datos_maestros.clientes"))

    return render_template("datos_maestros/cliente_form.html", form=form, cliente=cliente)


@bp.route("/clientes.xlsx")
@require_permission("datos_maestros", "ver")
def clientes_excel():
    """Informe en Excel de la cartera de clientes."""
    lista = Cliente.query.filter_by(empresa_id=current_user.empresa_id).order_by(Cliente.razon_social).all()

    columnas = [
        col("RUT", ancho=15, total="texto"),
        col("Razón social", ancho=40),
        col("Giro", ancho=32),
        col("Dirección", ancho=36),
        col("Comuna", ancho=20),
        col("Ciudad", ancho=20),
        col("Teléfono", ancho=16),
        col("Email", ancho=30),
        col("Contacto", ancho=26),
        col("Estado", ancho=12),
        col("Contratos vigentes", ancho=18, formato=ENTERO, total="suma"),
    ]
    filas = [
        [
            c.rut,
            c.razon_social,
            c.giro or "",
            c.direccion or "",
            c.comuna or "",
            c.ciudad or "",
            c.telefono or "",
            c.email or "",
            c.contacto_nombre or "",
            "Activo" if c.activo else "Inactivo",
            sum(1 for contrato in c.contratos if contrato.estado in ("vigente", "por_vencer")),
        ]
        for c in lista
    ]

    return responder_excel("clientes", "Clientes", columnas, filas)


# --- Proveedores ---


@bp.route("/proveedores")
@require_permission("datos_maestros", "ver")
def proveedores():
    lista = Proveedor.query.filter_by(empresa_id=current_user.empresa_id).order_by(Proveedor.razon_social).all()
    return render_template("datos_maestros/proveedores_lista.html", proveedores=lista)


@bp.route("/proveedores/nuevo", methods=["GET", "POST"])
@require_permission("datos_maestros", "editar")
def nuevo_proveedor():
    form = ProveedorForm()
    if form.validate_on_submit():
        if Proveedor.query.filter_by(rut=form.rut.data.strip()).first():
            flash("Ya existe un proveedor con ese RUT.", "danger")
            return render_template("datos_maestros/proveedor_form.html", form=form, proveedor=None)

        proveedor = Proveedor(
            empresa_id=current_user.empresa_id,
            rut=form.rut.data.strip(),
            razon_social=form.razon_social.data.strip(),
            giro=form.giro.data,
            direccion=form.direccion.data,
            telefono=form.telefono.data,
            email=form.email.data,
            contacto_nombre=form.contacto_nombre.data,
            activo=form.activo.data,
        )
        db.session.add(proveedor)
        db.session.commit()
        flash("Proveedor creado correctamente.", "success")
        return redirect(url_for("datos_maestros.proveedores"))

    return render_template("datos_maestros/proveedor_form.html", form=form, proveedor=None)


@bp.route("/proveedores/<int:proveedor_id>/editar", methods=["GET", "POST"])
@require_permission("datos_maestros", "editar")
def editar_proveedor(proveedor_id):
    proveedor = Proveedor.query.get_or_404(proveedor_id)
    form = ProveedorForm(obj=proveedor)
    if form.validate_on_submit():
        duplicado = Proveedor.query.filter(
            Proveedor.rut == form.rut.data.strip(), Proveedor.id != proveedor.id
        ).first()
        if duplicado:
            flash("Ya existe otro proveedor con ese RUT.", "danger")
            return render_template("datos_maestros/proveedor_form.html", form=form, proveedor=proveedor)

        form.populate_obj(proveedor)
        proveedor.rut = form.rut.data.strip()
        db.session.commit()
        flash("Proveedor actualizado correctamente.", "success")
        return redirect(url_for("datos_maestros.proveedores"))

    return render_template("datos_maestros/proveedor_form.html", form=form, proveedor=proveedor)


@bp.route("/proveedores.xlsx")
@require_permission("datos_maestros", "ver")
def proveedores_excel():
    """Informe en Excel del registro de proveedores."""
    lista = Proveedor.query.filter_by(empresa_id=current_user.empresa_id).order_by(Proveedor.razon_social).all()

    columnas = [
        col("RUT", ancho=15, total="texto"),
        col("Razón social", ancho=40),
        col("Giro", ancho=32),
        col("Dirección", ancho=36),
        col("Teléfono", ancho=16),
        col("Email", ancho=30),
        col("Contacto", ancho=26),
        col("Estado", ancho=12),
        col("Arriendos vigentes", ancho=18, formato=ENTERO, total="suma"),
    ]
    filas = [
        [
            p.rut,
            p.razon_social,
            p.giro or "",
            p.direccion or "",
            p.telefono or "",
            p.email or "",
            p.contacto_nombre or "",
            "Activo" if p.activo else "Inactivo",
            sum(1 for a in p.arriendos_entrada if a.estado in ("vigente", "por_vencer")),
        ]
        for p in lista
    ]

    return responder_excel("proveedores", "Proveedores", columnas, filas)


# --- Importar ---


@bp.route("/importar")
@require_permission("datos_maestros", "editar")
def importar():
    form_clientes = ImportarExcelForm(prefix="cli")
    form_proveedores = ImportarExcelForm(prefix="prov")
    return render_template(
        "datos_maestros/importar.html", form_clientes=form_clientes, form_proveedores=form_proveedores
    )


@bp.route("/clientes/plantilla.xlsx")
@require_permission("datos_maestros", "ver")
def clientes_plantilla():
    columnas = [col(nombre, ancho=20) for nombre in COLUMNAS_CLIENTES]
    return responder_excel(
        "plantilla-clientes", "Plantilla de clientes", columnas, [],
        "Completa una fila por cliente y súbela en Datos maestros > Importar. 'Activo' acepta Sí/No.",
    )


@bp.route("/proveedores/plantilla.xlsx")
@require_permission("datos_maestros", "ver")
def proveedores_plantilla():
    columnas = [col(nombre, ancho=20) for nombre in COLUMNAS_PROVEEDORES]
    return responder_excel(
        "plantilla-proveedores", "Plantilla de proveedores", columnas, [],
        "Completa una fila por proveedor y súbela en Datos maestros > Importar. 'Activo' acepta Sí/No.",
    )


@bp.route("/clientes/importar", methods=["POST"])
@require_permission("datos_maestros", "editar")
def importar_clientes_excel():
    form = ImportarExcelForm(prefix="cli")
    if form.validate_on_submit():
        try:
            resultado = importar_clientes(form.archivo.data, current_user.empresa_id)
            mensaje = f"Clientes importados: {resultado['creados']} nuevos, {resultado['actualizados']} actualizados."
            if resultado["invalidos"]:
                mensaje += f" Se omitieron {len(resultado['invalidos'])} fila(s) con RUT inválido o sin razón social."
            flash(mensaje, "success" if not resultado["invalidos"] else "warning")
        except ValueError as e:
            flash(str(e), "danger")
    else:
        flash("Selecciona un archivo Excel (.xlsx) válido.", "danger")
    return redirect(url_for("datos_maestros.importar"))


@bp.route("/proveedores/importar", methods=["POST"])
@require_permission("datos_maestros", "editar")
def importar_proveedores_excel():
    form = ImportarExcelForm(prefix="prov")
    if form.validate_on_submit():
        try:
            resultado = importar_proveedores(form.archivo.data, current_user.empresa_id)
            mensaje = f"Proveedores importados: {resultado['creados']} nuevos, {resultado['actualizados']} actualizados."
            if resultado["invalidos"]:
                mensaje += f" Se omitieron {len(resultado['invalidos'])} fila(s) con RUT inválido o sin razón social."
            flash(mensaje, "success" if not resultado["invalidos"] else "warning")
        except ValueError as e:
            flash(str(e), "danger")
    else:
        flash("Selecciona un archivo Excel (.xlsx) válido.", "danger")
    return redirect(url_for("datos_maestros.importar"))
