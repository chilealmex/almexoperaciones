from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.contabilidad import bp
from app.contabilidad.forms import (
    AccionForm,
    ImportarMayorForm,
    ImportarProvisionesForm,
    PeriodoDifTcForm,
)
from app.extensions import db
from app.models.contabilidad import LineaDifTc, PeriodoDifTc, ProvisionIngreso
from app.utils.decorators import require_permission
from app.utils.dif_tipo_cambio import recalcular_periodo, totales_periodo
from app.utils.dif_tipo_cambio_excel import PlanillaInvalida as PlanillaInvalidaMayor
from app.utils.dif_tipo_cambio_excel import leer_mayor
from app.utils.exportar import CLP, FECHA, PORCENTAJE, col, responder_excel
from app.utils.provision_ingresos_excel import (
    MESES_NOMBRES,
    PlanillaInvalida,
    leer_provisiones,
    mes_legible,
    nombre_mes,
)

# Lo único editable desde la pantalla; el resto de las columnas viene del Excel.
CAMPOS_EDITABLES = ("reversa", "mes_reversa", "cbte_reversa", "saldo")


def _empresa_id():
    return current_user.empresa_id


def _parse_entero(valor):
    """Acepta lo que se ve en pantalla ('$1.234') y también un número pelado."""
    if valor is None:
        return None
    texto = str(valor).replace("$", "").replace(".", "").replace(" ", "").strip()
    if not texto:
        return None
    try:
        return int(round(float(texto.replace(",", "."))))
    except ValueError:
        return None


def _parse_decimal(valor):
    """Número con coma o punto decimal, como se escribe en pantalla. Vacío = None."""
    if valor is None:
        return None
    texto = str(valor).replace("$", "").replace(" ", "").strip()
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def _saldo_de(linea):
    """El saldo es lo que queda por reversar: la provisión menos la reversa."""
    return (linea.monto_provision or 0) - (linea.reversa or 0)


def _linea_cerrada(linea):
    """Saldo en $0 = provisión reversada por completo. Queda bloqueada.

    Un superadmin sí puede modificarla, para poder corregir un monto mal escrito.
    """
    return (linea.saldo or 0) == 0 and not current_user.es_superadmin


def _query_base():
    return ProvisionIngreso.query.filter_by(empresa_id=_empresa_id())


def _aplicar_filtros(query, args):
    texto = (args.get("texto") or "").strip()
    mes = (args.get("mes") or "").strip()
    anio = (args.get("anio") or "").strip()
    estado = (args.get("estado") or "").strip()
    if texto:
        comodin = f"%{texto}%"
        query = query.filter(
            db.or_(
                ProvisionIngreso.cliente.ilike(comodin),
                ProvisionIngreso.ot.ilike(comodin),
                ProvisionIngreso.cbte_prov.ilike(comodin),
                ProvisionIngreso.rut.ilike(comodin),
                ProvisionIngreso.centro_costos.ilike(comodin),
            )
        )
    # extract() en vez de strftime(): strftime solo existe en SQLite y en
    # PostgreSQL (producción) tira un error 500.
    if mes:
        try:
            query = query.filter(db.extract("month", ProvisionIngreso.mes_ano) == int(mes))
        except ValueError:
            pass
    if anio:
        try:
            query = query.filter(db.extract("year", ProvisionIngreso.mes_ano) == int(anio))
        except ValueError:
            pass
    # Una línea con saldo $0 ya está reversada por completo: se considera cerrada.
    if estado == "pendiente":
        query = query.filter(ProvisionIngreso.saldo > 0)
    elif estado == "cerrado":
        query = query.filter(ProvisionIngreso.saldo <= 0)
    return query


def _anios_disponibles(lineas):
    return sorted({l.mes_ano.year for l in lineas if l.mes_ano}, reverse=True)


def _meses_disponibles(lineas):
    """Los meses que realmente aparecen, con su nombre, ordenados de enero a diciembre."""
    numeros = sorted({l.mes_ano.month for l in lineas if l.mes_ano})
    return [(str(n), MESES_NOMBRES[n - 1]) for n in numeros]


@bp.route("/")
@require_permission("contabilidad", "ver")
def index():
    return redirect(url_for("contabilidad.provision_ingresos"))


@bp.route("/provision-ingresos")
@require_permission("contabilidad", "ver")
def provision_ingresos():
    todas = _query_base().all()
    lineas = (
        _aplicar_filtros(_query_base(), request.args)
        .order_by(ProvisionIngreso.mes_ano.desc(), ProvisionIngreso.cbte_prov, ProvisionIngreso.ot)
        .all()
    )
    totales = {
        "provision": sum(l.monto_provision or 0 for l in lineas),
        "reversa": sum(l.reversa or 0 for l in lineas),
        "saldo": sum(l.saldo or 0 for l in lineas),
        "cerradas": sum(1 for l in lineas if (l.saldo or 0) <= 0),
        "pendientes": sum(1 for l in lineas if (l.saldo or 0) > 0),
    }
    return render_template(
        "contabilidad/provision_ingresos.html",
        lineas=lineas,
        totales=totales,
        meses=_meses_disponibles(todas),
        anios=_anios_disponibles(todas),
        filtros=request.args,
        importar_form=ImportarProvisionesForm(),
        accion_form=AccionForm(),
        mes_legible=mes_legible,
        nombre_mes=nombre_mes,
    )


@bp.route("/provision-ingresos/importar", methods=["POST"])
@require_permission("contabilidad", "editar")
def importar_provision_ingresos():
    form = ImportarProvisionesForm()
    if not form.validate_on_submit():
        flash("Elige un archivo Excel (.xlsx) para importar.", "warning")
        return redirect(url_for("contabilidad.provision_ingresos"))

    try:
        lineas = leer_provisiones(form.archivo.data)
    except PlanillaInvalida as error:
        flash(str(error), "danger")
        return redirect(url_for("contabilidad.provision_ingresos"))

    # Se agregan solo las líneas que no estaban. Las que ya existen se dejan
    # tal cual, para no pisar lo que se editó a mano en la aplicación.
    existentes = {(l.mes_ano, l.cbte_prov, l.ot) for l in _query_base().all()}
    nuevas = 0
    for linea in lineas:
        clave = (linea["mes_ano"], linea["cbte_prov"], linea["ot"])
        if clave in existentes:
            continue
        existentes.add(clave)
        registro = ProvisionIngreso(
            empresa_id=_empresa_id(),
            **{k: v for k, v in linea.items() if k != "fila"},
        )
        registro.saldo = _saldo_de(registro)
        db.session.add(registro)
        nuevas += 1
    db.session.commit()

    repetidas = len(lineas) - nuevas
    mensaje = f"Se agregaron {nuevas} línea(s) nueva(s)."
    if repetidas:
        mensaje += f" Se dejaron sin tocar {repetidas} que ya estaban cargadas."
    flash(mensaje, "success" if nuevas else "info")
    return redirect(url_for("contabilidad.provision_ingresos"))


@bp.route("/provision-ingresos/guardar", methods=["POST"])
@require_permission("contabilidad", "editar")
def guardar_provision_ingresos():
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)

    for linea in _query_base().all():
        prefijo = f"linea-{linea.id}-"
        if prefijo + "reversa" not in request.form:
            continue  # línea que no está en la página que se envió
        if _linea_cerrada(linea):
            continue  # ya quedó en $0: no se toca salvo que la reabra un superadmin
        linea.reversa = _parse_entero(request.form.get(prefijo + "reversa"))
        linea.mes_reversa = (request.form.get(prefijo + "mes_reversa") or "").strip() or None
        linea.cbte_reversa = (request.form.get(prefijo + "cbte_reversa") or "").strip() or None
        linea.saldo = _saldo_de(linea)
    db.session.commit()
    flash("Cambios guardados.", "success")
    return redirect(url_for("contabilidad.provision_ingresos", **request.args))


@bp.route("/provision-ingresos/<int:linea_id>/eliminar", methods=["POST"])
@require_permission("contabilidad", "editar")
def eliminar_provision_ingreso(linea_id):
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    linea = ProvisionIngreso.query.get_or_404(linea_id)
    if linea.empresa_id != _empresa_id():
        abort(404)
    db.session.delete(linea)
    db.session.commit()
    flash("Línea eliminada.", "success")
    return redirect(url_for("contabilidad.provision_ingresos"))


@bp.route("/provision-ingresos/exportar.xlsx")
@require_permission("contabilidad", "ver")
def exportar_provision_ingresos():
    lineas = (
        _aplicar_filtros(_query_base(), request.args)
        .order_by(ProvisionIngreso.mes_ano.desc(), ProvisionIngreso.cbte_prov, ProvisionIngreso.ot)
        .all()
    )
    columnas = [
        col("Mes", ancho=12),
        col("Año", ancho=8),
        col("Cbte Prov", ancho=12),
        col("OT", ancho=10),
        col("Monto Provisión", ancho=18, formato=CLP, total="suma"),
        col("Reversa", ancho=16, formato=CLP, total="suma"),
        col("Mes Reversa", ancho=18),
        col("Cbte Reversa", ancho=14),
        col("Cliente", ancho=38),
        col("Centro de Costos", ancho=20),
        col("Rut", ancho=14),
        col("Obs", ancho=24),
        col("Saldo", ancho=16, formato=CLP, total="suma"),
    ]
    filas = [
        [
            nombre_mes(l.mes_ano), l.mes_ano.year if l.mes_ano else None,
            l.cbte_prov, l.ot, l.monto_provision, l.reversa,
            l.mes_reversa, l.cbte_reversa, l.cliente, l.centro_costos, l.rut, l.obs, l.saldo,
        ]
        for l in lineas
    ]
    return responder_excel("provision-de-ingresos", "Provisión de Ingresos", columnas, filas)


# ===================== Dif TC PR/CL =====================


def _get_periodo_or_404(periodo_id):
    periodo = PeriodoDifTc.query.get_or_404(periodo_id)
    if periodo.empresa_id != _empresa_id():
        abort(404)
    return periodo


def _periodo_bloqueado(periodo):
    """Un período cerrado ya se contabilizó: solo un superadmin puede reabrirlo."""
    return periodo.estado == "cerrado" and not current_user.es_superadmin


def _form_periodo(obj=None):
    form = PeriodoDifTcForm(obj=obj)
    form.mes.choices = [(n, MESES_NOMBRES[n - 1]) for n in range(1, 13)]
    return form


@bp.route("/dif-tc")
@require_permission("contabilidad", "ver")
def dif_tc():
    periodos = (
        PeriodoDifTc.query.filter_by(empresa_id=_empresa_id())
        .order_by(PeriodoDifTc.anio.desc(), PeriodoDifTc.mes.desc())
        .all()
    )
    hoy = date.today()
    form = _form_periodo()
    if not form.is_submitted():
        form.anio.data, form.mes.data = hoy.year, hoy.month
    return render_template(
        "contabilidad/dif_tc_lista.html",
        periodos=periodos,
        resumenes={p.id: totales_periodo(p) for p in periodos},
        form=form,
        accion_form=AccionForm(),
        nombre_mes_numero=lambda n: MESES_NOMBRES[n - 1],
    )


@bp.route("/dif-tc/nuevo", methods=["POST"])
@require_permission("contabilidad", "editar")
def nuevo_periodo_dif_tc():
    form = _form_periodo()
    if not form.validate_on_submit():
        flash("Revisa el mes y el año del período.", "warning")
        return redirect(url_for("contabilidad.dif_tc"))

    existe = PeriodoDifTc.query.filter_by(
        empresa_id=_empresa_id(), anio=form.anio.data, mes=form.mes.data
    ).first()
    if existe:
        flash(f"Ya existe el período {MESES_NOMBRES[form.mes.data - 1]} {form.anio.data}.", "warning")
        return redirect(url_for("contabilidad.ver_periodo_dif_tc", periodo_id=existe.id))

    periodo = PeriodoDifTc(
        empresa_id=_empresa_id(), anio=form.anio.data, mes=form.mes.data,
        tipo_cambio=_parse_decimal(form.tipo_cambio.data) or 0, notas=form.notas.data or None,
    )
    db.session.add(periodo)
    db.session.commit()
    flash("Período creado. Ahora importa el mayor del mes.", "success")
    return redirect(url_for("contabilidad.ver_periodo_dif_tc", periodo_id=periodo.id))


@bp.route("/dif-tc/<int:periodo_id>")
@require_permission("contabilidad", "ver")
def ver_periodo_dif_tc(periodo_id):
    periodo = _get_periodo_or_404(periodo_id)
    return render_template(
        "contabilidad/dif_tc_ver.html",
        periodo=periodo,
        totales=totales_periodo(periodo),
        nombre_mes_numero=lambda n: MESES_NOMBRES[n - 1],
        importar_form=ImportarMayorForm(),
        accion_form=AccionForm(),
    )


@bp.route("/dif-tc/<int:periodo_id>/importar", methods=["POST"])
@require_permission("contabilidad", "editar")
def importar_mayor_dif_tc(periodo_id):
    periodo = _get_periodo_or_404(periodo_id)
    if _periodo_bloqueado(periodo):
        flash("Este período está cerrado. Solo un superadmin puede modificarlo.", "warning")
        return redirect(url_for("contabilidad.ver_periodo_dif_tc", periodo_id=periodo.id))

    form = ImportarMayorForm()
    if not form.validate_on_submit():
        flash("Elige un archivo Excel (.xlsx) para importar.", "warning")
        return redirect(url_for("contabilidad.ver_periodo_dif_tc", periodo_id=periodo.id))

    try:
        lineas, tipo_cambio = leer_mayor(form.archivo.data)
    except PlanillaInvalidaMayor as error:
        flash(str(error), "danger")
        return redirect(url_for("contabilidad.ver_periodo_dif_tc", periodo_id=periodo.id))

    # El mayor del mes reemplaza al del período: es una foto de la base contable
    # a esa fecha, no algo que se acumule. Los meses anteriores no se tocan.
    for linea in list(periodo.lineas):
        db.session.delete(linea)
    db.session.flush()
    for datos in lineas:
        periodo.lineas.append(LineaDifTc(**datos))
    if tipo_cambio and not periodo.tipo_cambio:
        periodo.tipo_cambio = tipo_cambio
    db.session.flush()
    recalcular_periodo(periodo)
    db.session.commit()

    mensaje = f"Se cargaron {len(lineas)} línea(s) del mayor."
    if tipo_cambio:
        mensaje += f" Tipo de cambio de la planilla: {tipo_cambio}."
    flash(mensaje, "success")
    return redirect(url_for("contabilidad.ver_periodo_dif_tc", periodo_id=periodo.id))


@bp.route("/dif-tc/<int:periodo_id>/guardar", methods=["POST"])
@require_permission("contabilidad", "editar")
def guardar_periodo_dif_tc(periodo_id):
    periodo = _get_periodo_or_404(periodo_id)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    if _periodo_bloqueado(periodo):
        flash("Este período está cerrado. Solo un superadmin puede modificarlo.", "warning")
        return redirect(url_for("contabilidad.ver_periodo_dif_tc", periodo_id=periodo.id))

    tipo_cambio = _parse_decimal(request.form.get("tipo_cambio"))
    if tipo_cambio is not None:
        periodo.tipo_cambio = tipo_cambio
    periodo.notas = (request.form.get("notas") or "").strip() or None

    for linea in periodo.lineas:
        campo = f"linea-{linea.id}-mon_orig"
        if campo not in request.form:
            continue
        linea.mon_orig = _parse_decimal(request.form.get(campo))
    recalcular_periodo(periodo)
    db.session.commit()
    flash("Cambios guardados.", "success")
    return redirect(url_for("contabilidad.ver_periodo_dif_tc", periodo_id=periodo.id))


@bp.route("/dif-tc/<int:periodo_id>/estado", methods=["POST"])
@require_permission("contabilidad", "editar")
def cambiar_estado_dif_tc(periodo_id):
    periodo = _get_periodo_or_404(periodo_id)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)

    nuevo = request.form.get("estado")
    if nuevo not in ("en_proceso", "cerrado"):
        abort(400)
    if periodo.estado == "cerrado" and not current_user.es_superadmin:
        flash("Solo un superadmin puede reabrir un período cerrado.", "warning")
        return redirect(url_for("contabilidad.ver_periodo_dif_tc", periodo_id=periodo.id))

    periodo.estado = nuevo
    db.session.commit()
    flash("Período cerrado." if nuevo == "cerrado" else "Período reabierto.", "success")
    return redirect(url_for("contabilidad.ver_periodo_dif_tc", periodo_id=periodo.id))


@bp.route("/dif-tc/<int:periodo_id>/eliminar", methods=["POST"])
@require_permission("contabilidad", "editar")
def eliminar_periodo_dif_tc(periodo_id):
    periodo = _get_periodo_or_404(periodo_id)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    if _periodo_bloqueado(periodo):
        flash("Este período está cerrado. Solo un superadmin puede eliminarlo.", "warning")
        return redirect(url_for("contabilidad.ver_periodo_dif_tc", periodo_id=periodo.id))
    db.session.delete(periodo)
    db.session.commit()
    flash("Período eliminado.", "success")
    return redirect(url_for("contabilidad.dif_tc"))


@bp.route("/dif-tc/<int:periodo_id>/exportar.xlsx")
@require_permission("contabilidad", "ver")
def exportar_periodo_dif_tc(periodo_id):
    periodo = _get_periodo_or_404(periodo_id)
    columnas = [
        col("Cuenta", ancho=14), col("Descripción", ancho=32), col("Fecha", ancho=12, formato=FECHA),
        col("Tipo", ancho=12), col("Número", ancho=10), col("ID Ficha", ancho=10), col("Ficha", ancho=32),
        col("Cargo ($)", ancho=16, formato=CLP, total="suma"),
        col("Abono ($)", ancho=16, formato=CLP, total="suma"),
        col("Saldo ($)", ancho=16, formato=CLP, total="suma"),
        col("Código Doc.", ancho=16), col("Documento", ancho=24), col("Vencimiento", ancho=13),
        col("Número Doc.", ancho=13), col("Tipo Mov.", ancho=12), col("Serie", ancho=12),
        col("Número Mov.", ancho=13), col("Moneda Ref.", ancho=12), col("Comentario", ancho=36),
        col("Doc. Pago", ancho=12), col("Número Doc. Pago", ancho=16), col("Serie Doc. Pago.", ancho=16),
        col("Mon Orig", ancho=16),
        col("Valor en $", ancho=18, formato=CLP, total="suma"),
        col("Dif de cambio", ancho=18, formato=CLP, total="suma"),
        col("% Dif Variación", ancho=15, formato=PORCENTAJE),
    ]
    filas = [
        [
            l.cuenta, l.descripcion, l.fecha, l.tipo, l.numero, l.id_ficha, l.ficha,
            l.cargo, l.abono, l.saldo, l.codigo_doc, l.documento, l.vencimiento, l.numero_doc,
            l.tipo_mov, l.serie, l.numero_mov, l.moneda_ref, l.comentario, l.doc_pago,
            l.numero_doc_pago, l.serie_doc_pago, l.mon_orig, l.valor_clp, l.dif_cambio, l.pct_variacion,
        ]
        for l in periodo.lineas
    ]
    return responder_excel(
        f"dif-tc-{periodo.anio}-{periodo.mes:02d}",
        f"Dif TC {MESES_NOMBRES[periodo.mes - 1]} {periodo.anio}",
        columnas, filas,
        f"Tipo de cambio aplicado: {periodo.tipo_cambio}",
    )
