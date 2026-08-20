from datetime import date, datetime, timezone

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.contabilidad import bp
from app.contabilidad.forms import (
    AccionForm,
    ConciliacionSiiForm,
    ImportarMayorForm,
    ImportarProvisionesForm,
    NuevaProvisionForm,
    PeriodoDifTcForm,
)
from app.extensions import db
from app.models.contabilidad import (
    ConciliacionSii,
    ConciliacionSiiDocumento,
    ConciliacionSiiLibro,
    LineaDifTc,
    PeriodoDifTc,
    ProvisionIngreso,
    TipoCambioDifTc,
)
from app.utils.conciliacion_sii import COLUMNAS_MONTO as COLUMNAS_MONTO_CONCILIACION
from app.utils.conciliacion_sii import ESTADO_ETIQUETAS as ESTADO_ETIQUETAS_CONCILIACION
from app.utils.conciliacion_sii import ESTADOS as ESTADOS_CONCILIACION
from app.utils.conciliacion_sii import TIPOS_DOCUMENTO as TIPOS_DOCUMENTO_SII
from app.utils.conciliacion_sii import ArchivoInvalido, cruzar, leer_libro_defontana, leer_rcv_sii
from app.utils.decorators import require_permission
from app.utils.dif_tipo_cambio import recalcular_periodo, totales_periodo
from app.utils.dif_tipo_cambio_excel import PlanillaInvalida as PlanillaInvalidaMayor
from app.utils.dif_tipo_cambio_excel import leer_mayor
from app.utils.exportar import CLP, FECHA, PORCENTAJE, col, responder_excel, responder_plantilla_excel
from app.utils.provision_ingresos_excel import HOJA as HOJA_PROVISIONES
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


def estado_filtrado(args) -> str:
    """Qué estado se está mostrando; al entrar sin elegir nada, las pendientes.

    Lo cerrado ya no requiere trabajo, así que abrir la pantalla con todo el
    histórico cargado es lento y además entierra lo que falta por reversar.
    Para ver el resto está la opción "Todas", que viaja como estado=todas: si
    fuera un valor vacío no habría forma de distinguir "quiero verlas todas"
    de "recién llego a la pantalla".
    """
    estado = (args.get("estado") or "").strip()
    return estado or "pendiente"


def _aplicar_filtros(query, args):
    texto = (args.get("texto") or "").strip()
    mes = (args.get("mes") or "").strip()
    anio = (args.get("anio") or "").strip()
    estado = estado_filtrado(args)
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


def _anios_disponibles():
    """Los años que existen, preguntándoselo a la base.

    Antes se traían todas las líneas a memoria sólo para sacar esta lista; con
    muchos movimientos eso es cargar miles de filas para llenar un desplegable.
    """
    filas = db.session.query(db.extract("year", ProvisionIngreso.mes_ano)).filter_by(
        empresa_id=_empresa_id()
    ).distinct()
    return sorted({int(f[0]) for f in filas if f[0] is not None}, reverse=True)


def _meses_disponibles():
    """Los meses que realmente aparecen, con su nombre, ordenados de enero a diciembre."""
    filas = db.session.query(db.extract("month", ProvisionIngreso.mes_ano)).filter_by(
        empresa_id=_empresa_id()
    ).distinct()
    numeros = sorted({int(f[0]) for f in filas if f[0] is not None})
    return [(str(n), MESES_NOMBRES[n - 1]) for n in numeros]


@bp.route("/")
@require_permission("contabilidad", "ver")
def index():
    return redirect(url_for("contabilidad.provision_ingresos"))


@bp.route("/provision-ingresos")
@require_permission("contabilidad", "ver")
def provision_ingresos():
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
    # Cuántas quedan fuera de lo que se está viendo, para poder decirlo en
    # pantalla: si no, con el filtro por defecto parecería que se perdieron.
    total_lineas = _query_base().count()

    # Formulario vacío para cargar una línea a mano, con el mes y el año de hoy
    # ya puestos, que es lo que se va a usar casi siempre.
    hoy = date.today()
    nueva_form = NuevaProvisionForm(formdata=None, mes=hoy.month, anio=hoy.year)
    nueva_form.mes.choices = [(n, MESES_NOMBRES[n - 1]) for n in range(1, 13)]

    return render_template(
        "contabilidad/provision_ingresos.html",
        lineas=lineas,
        totales=totales,
        total_lineas=total_lineas,
        estado_actual=estado_filtrado(request.args),
        meses=_meses_disponibles(),
        anios=_anios_disponibles(),
        filtros=request.args,
        importar_form=ImportarProvisionesForm(),
        accion_form=AccionForm(),
        nueva_form=nueva_form,
        mes_legible=mes_legible,
        nombre_mes=nombre_mes,
    )


@bp.route("/provision-ingresos/plantilla.xlsx")
@require_permission("contabilidad", "ver")
def plantilla_provision_ingresos():
    """Planilla vacía con las columnas que espera la importación, para llenar y subir."""
    return responder_plantilla_excel(
        "plantilla-provision-de-ingresos",
        HOJA_PROVISIONES,
        [
            "Mes", "Año", "Cbte Prov", "OT", "Monto Provisión", "Reversa", "Mes Reversa",
            "Cbte Reversa", "Cliente", "Centro de Costos", "Rut", "Obs", "Saldo",
        ],
        fila_ejemplo=[
            3, 2026, 67, 6095, 3700000, 3700000, "05.2026", 109,
            "CIA MINERA COLLAHUASI", "EMPNEGVTAVTAPRE", "89468900-5", "", 0,
        ],
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

    # La planilla manda: las líneas nuevas se agregan y las que ya estaban se
    # actualizan con lo que trae el archivo. Nada se elimina: una línea que ya
    # no venga en la planilla se queda como está.
    existentes = {(l.mes_ano, l.cbte_prov, l.ot): l for l in _query_base().all()}
    nuevas = actualizadas = 0
    for linea in lineas:
        datos = {k: v for k, v in linea.items() if k != "fila"}
        clave = (linea["mes_ano"], linea["cbte_prov"], linea["ot"])
        registro = existentes.get(clave)
        if registro is None:
            registro = ProvisionIngreso(empresa_id=_empresa_id(), **datos)
            existentes[clave] = registro
            db.session.add(registro)
            nuevas += 1
        else:
            for campo, valor in datos.items():
                setattr(registro, campo, valor)
            actualizadas += 1
        registro.saldo = _saldo_de(registro)
    db.session.commit()

    partes = []
    if nuevas:
        partes.append(f"{nuevas} línea(s) nueva(s)")
    if actualizadas:
        partes.append(f"{actualizadas} actualizada(s) con los datos de la planilla")
    mensaje = "Se cargaron " + " y ".join(partes) + "." if partes else "La planilla no traía líneas."
    flash(mensaje, "success" if partes else "info")
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


@bp.route("/provision-ingresos/nueva", methods=["POST"])
@require_permission("contabilidad", "editar")
def nueva_provision_ingreso():
    """Agrega una línea a mano, sin tener que armar y subir el Excel."""
    form = NuevaProvisionForm()
    form.mes.choices = [(n, MESES_NOMBRES[n - 1]) for n in range(1, 13)]

    if not form.validate_on_submit():
        for campo, errores in form.errors.items():
            etiqueta = getattr(form, campo).label.text
            flash(f"{etiqueta}: {errores[0]}", "danger")
        return redirect(url_for("contabilidad.provision_ingresos"))

    monto = _parse_entero(form.monto_provision.data)
    if monto is None:
        flash("El monto de la provisión no se entiende. Escríbelo como 1310000 o $1.310.000.", "danger")
        return redirect(url_for("contabilidad.provision_ingresos"))

    periodo = date(form.anio.data, form.mes.data, 1)
    cbte = form.cbte_prov.data.strip()
    ot = form.ot.data.strip()

    # La línea se identifica por período + comprobante + OT, igual que en la
    # planilla. Si ya existe se avisa en vez de reventar con el error de la
    # restricción de la base.
    if _query_base().filter_by(mes_ano=periodo, cbte_prov=cbte, ot=ot).first():
        flash(
            f"Ya existe una línea de {nombre_mes(periodo)} {periodo.year} "
            f"con el comprobante {cbte} y la OT {ot}.",
            "warning",
        )
        return redirect(url_for("contabilidad.provision_ingresos"))

    linea = ProvisionIngreso(
        empresa_id=_empresa_id(),
        mes_ano=periodo,
        cbte_prov=cbte,
        ot=ot,
        monto_provision=monto,
        cliente=(form.cliente.data or "").strip() or None,
        centro_costos=(form.centro_costos.data or "").strip() or None,
        rut=(form.rut.data or "").strip() or None,
        obs=(form.obs.data or "").strip() or None,
    )
    linea.saldo = _saldo_de(linea)  # sin reversa todavía, el saldo es la provisión entera
    db.session.add(linea)
    db.session.commit()
    flash(f"Línea agregada: OT {ot}, comprobante {cbte}.", "success")
    return redirect(url_for("contabilidad.provision_ingresos"))


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


MONEDAS_DIF_TC = ("USD", "EUR")


def _sembrar_tipos_cambio(periodo, valores=None):
    """Deja una fila por moneda en la tabla de cambio del período."""
    valores = {k.upper(): v for k, v in (valores or {}).items()}
    existentes = {tc.moneda for tc in periodo.tipos_cambio}
    for moneda in list(MONEDAS_DIF_TC) + [m for m in valores if m not in MONEDAS_DIF_TC]:
        if moneda in existentes:
            continue
        periodo.tipos_cambio.append(TipoCambioDifTc(moneda=moneda, valor=valores.get(moneda, 0) or 0))


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

    valores = {
        "USD": _parse_decimal(form.tipo_cambio_usd.data) or 0,
        "EUR": _parse_decimal(form.tipo_cambio_eur.data) or 0,
    }
    periodo = PeriodoDifTc(
        empresa_id=_empresa_id(), anio=form.anio.data, mes=form.mes.data,
        tipo_cambio=valores["USD"], notas=form.notas.data or None,
    )
    db.session.add(periodo)
    _sembrar_tipos_cambio(periodo, valores)
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
        lineas, tipos_cambio = leer_mayor(form.archivo.data)
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
    # La planilla trae los tipos de cambio del mes, así que mandan sobre lo que
    # hubiera. Las monedas que no vienen en el archivo se dejan como estaban.
    _sembrar_tipos_cambio(periodo, tipos_cambio)
    for tc in periodo.tipos_cambio:
        if tipos_cambio.get(tc.moneda) is not None:
            tc.valor = tipos_cambio[tc.moneda]
    db.session.flush()
    recalcular_periodo(periodo)
    db.session.commit()

    mensaje = f"Se cargaron {len(lineas)} línea(s) del mayor."
    if tipos_cambio:
        detalle = ", ".join(f"{m} {v}" for m, v in sorted(tipos_cambio.items()))
        mensaje += f" Tipos de cambio de la planilla: {detalle}."
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

    periodo.notas = (request.form.get("notas") or "").strip() or None

    for tc in periodo.tipos_cambio:
        valor = _parse_decimal(request.form.get(f"tc-{tc.id}-valor"))
        if valor is not None:
            tc.valor = valor
    nueva_moneda = (request.form.get("nueva_moneda") or "").strip().upper()
    nuevo_valor = _parse_decimal(request.form.get("nuevo_tipo_cambio"))
    if nueva_moneda and nueva_moneda not in {tc.moneda for tc in periodo.tipos_cambio}:
        periodo.tipos_cambio.append(TipoCambioDifTc(moneda=nueva_moneda, valor=nuevo_valor or 0))

    for linea in periodo.lineas:
        campo = f"linea-{linea.id}-mon_orig"
        if campo not in request.form:
            continue
        linea.mon_orig = _parse_decimal(request.form.get(campo))
        linea.tipo_moneda = (request.form.get(f"linea-{linea.id}-tipo_moneda") or "").strip().upper() or None
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
        col("TIPO MONEDA", ancho=13), col("Mon Orig", ancho=16),
        col("Valor en $", ancho=18, formato=CLP, total="suma"),
        col("Dif de cambio", ancho=18, formato=CLP, total="suma"),
        col("% Dif Variación", ancho=15, formato=PORCENTAJE),
    ]
    filas = [
        [
            l.cuenta, l.descripcion, l.fecha, l.tipo, l.numero, l.id_ficha, l.ficha,
            l.cargo, l.abono, l.saldo, l.codigo_doc, l.documento, l.vencimiento, l.numero_doc,
            l.tipo_mov, l.serie, l.numero_mov, l.moneda_ref, l.comentario, l.doc_pago,
            l.numero_doc_pago, l.serie_doc_pago, l.tipo_moneda, l.mon_orig,
            l.valor_clp, l.dif_cambio, l.pct_variacion,
        ]
        for l in periodo.lineas
    ]
    return responder_excel(
        f"dif-tc-{periodo.anio}-{periodo.mes:02d}",
        f"Dif TC {MESES_NOMBRES[periodo.mes - 1]} {periodo.anio}",
        columnas, filas,
        "Tipos de cambio aplicados: "
        + (", ".join(f"{tc.moneda} {tc.valor}" for tc in periodo.tipos_cambio) or "sin definir"),
    )


# --- Conciliación SII / Defontana ----------------------------------------
#
# Cada mes se comprueba que lo que el SII tiene registrado a nombre de la
# empresa esté contabilizado igual en Defontana. Los dos libros —compras y
# ventas— se cargan por separado, porque rara vez están listos el mismo día.

FILTROS_CONCILIACION = ("pendientes",) + ESTADOS_CONCILIACION

# MESES_NOMBRES es una tupla base 0; acá los meses se manejan como 1-12.
MESES_ELEGIBLES = [(numero, MESES_NOMBRES[numero - 1]) for numero in range(1, 13)]


def _nombre_de_mes(numero) -> str:
    return MESES_NOMBRES[numero - 1] if 1 <= (numero or 0) <= 12 else ""


def _conciliacion_or_404(conciliacion_id):
    return ConciliacionSii.query.filter_by(
        id=conciliacion_id, empresa_id=_empresa_id()
    ).first_or_404()


def _guardar_cruce(conciliacion, clave_libro, resultado, nombre_sii, nombre_defontana):
    """Reemplaza el cruce de un libro con el recién calculado.

    Se borra el anterior en vez de acumular: la conciliación se rehace varias
    veces en el mes a medida que se corrigen los asientos, y lo que interesa es
    la foto de ahora, no el historial de intentos.
    """
    libro = conciliacion.libro_por_clave(clave_libro)
    if libro is None:
        libro = ConciliacionSiiLibro(libro=clave_libro, cargas=0)
        conciliacion.libros.append(libro)
    else:
        for documento in list(libro.documentos):
            db.session.delete(documento)
        db.session.flush()

    libro.archivo_sii = (nombre_sii or "")[:255] or None
    libro.archivo_defontana = (nombre_defontana or "")[:255] or None
    libro.cargado_en = datetime.now(timezone.utc)
    libro.cargado_por_id = current_user.id
    libro.cargas = (libro.cargas or 0) + 1

    conteos = resultado["conteos"]
    libro.n_coincide = conteos["coincide"]
    libro.n_solo_sii = conteos["solo_sii"]
    libro.n_solo_defontana = conteos["solo_defontana"]
    libro.n_dif_monto = conteos["dif_monto"]
    libro.n_dif_datos = conteos["dif_datos"]

    totales = resultado["totales"]
    for campo in ("neto_sii", "neto_defontana", "exento_sii", "exento_defontana",
                  "iva_sii", "iva_defontana", "total_sii", "total_defontana"):
        setattr(libro, campo, totales[campo])

    for orden, fila in enumerate(resultado["filas"]):
        libro.documentos.append(ConciliacionSiiDocumento(
            tipo_doc=fila["tipo_doc"],
            tipo_doc_desc=fila["tipo_doc_desc"][:60],
            folio=fila["folio"][:40],
            fecha=(fila["fecha"] or "")[:20] or None,
            rut_sii=(fila["rut_sii"] or "")[:20] or None,
            contraparte_sii=(fila["contraparte_sii"] or "")[:200] or None,
            rut_defontana=(fila["rut_defontana"] or "")[:20] or None,
            contraparte_defontana=(fila["contraparte_defontana"] or "")[:200] or None,
            neto_sii=fila["neto_sii"], neto_defontana=fila["neto_defontana"],
            exento_sii=fila["exento_sii"], exento_defontana=fila["exento_defontana"],
            iva_sii=fila["iva_sii"], iva_defontana=fila["iva_defontana"],
            total_sii=fila["total_sii"], total_defontana=fila["total_defontana"],
            dif_neto=fila["dif_neto"], dif_exento=fila["dif_exento"],
            dif_iva=fila["dif_iva"], diferencia=fila["diferencia"],
            estado=fila["estado"],
            diferencia_descrita=(fila["diferencia_descrita"] or "")[:400] or None,
            orden=orden,
        ))
    return libro


@bp.route("/conciliacion-sii")
@require_permission("contabilidad", "ver")
def conciliacion_sii():
    conciliaciones = (
        ConciliacionSii.query.filter_by(empresa_id=_empresa_id())
        .order_by(ConciliacionSii.anio.desc(), ConciliacionSii.mes.desc())
        .all()
    )
    hoy = date.today()
    form = ConciliacionSiiForm(anio=hoy.year, mes=hoy.month)
    form.mes.choices = MESES_ELEGIBLES
    return render_template(
        "contabilidad/conciliacion_sii.html",
        conciliaciones=conciliaciones,
        form=form,
        accion=AccionForm(),
        meses=MESES_NOMBRES,
    )


@bp.route("/conciliacion-sii/cargar", methods=["POST"])
@require_permission("contabilidad", "editar")
def cargar_conciliacion_sii():
    form = ConciliacionSiiForm()
    form.mes.choices = MESES_ELEGIBLES
    if not form.validate_on_submit():
        for errores in form.errors.values():
            for error in errores:
                flash(error, "danger")
        return redirect(url_for("contabilidad.conciliacion_sii"))

    pares = {
        "compra": (form.sii_compra.data, form.defontana_compra.data),
        "venta": (form.sii_venta.data, form.defontana_venta.data),
    }
    if not any(archivo_sii or archivo_defo for archivo_sii, archivo_defo in pares.values()):
        flash("Elige al menos un par de archivos para cruzar.", "warning")
        return redirect(url_for("contabilidad.conciliacion_sii"))

    conciliacion = ConciliacionSii.query.filter_by(
        empresa_id=_empresa_id(), anio=form.anio.data, mes=form.mes.data
    ).first()
    if conciliacion is None:
        conciliacion = ConciliacionSii(
            empresa_id=_empresa_id(), anio=form.anio.data, mes=form.mes.data
        )
        db.session.add(conciliacion)
        db.session.flush()

    mensajes, avisos = [], []
    for clave, (archivo_sii, archivo_defo) in pares.items():
        etiqueta = "Compras" if clave == "compra" else "Ventas"
        if not archivo_sii and not archivo_defo:
            continue
        if not archivo_sii or not archivo_defo:
            falta = "el RCV del SII" if not archivo_sii else "el libro de Defontana"
            avisos.append(f"{etiqueta}: falta {falta}, así que no se cruzó.")
            continue
        try:
            documentos_sii = leer_rcv_sii(archivo_sii, clave)
            documentos_defo = leer_libro_defontana(archivo_defo)
        except ArchivoInvalido as error:
            avisos.append(f"{etiqueta}: {error}")
            continue

        resultado = cruzar(documentos_sii, documentos_defo, clave)
        _guardar_cruce(conciliacion, clave, resultado, archivo_sii.filename, archivo_defo.filename)
        conteos = resultado["conteos"]
        mensajes.append(
            f"{etiqueta}: {len(resultado['filas'])} documentos · "
            f"{conteos['coincide']} coinciden · {conteos['solo_sii']} solo en el SII · "
            f"{conteos['solo_defontana']} solo en Defontana · "
            f"{conteos['dif_monto']} con diferencia de monto · "
            f"{conteos['dif_datos']} con diferencia de datos"
        )

    if not mensajes:
        db.session.rollback()
        for aviso in avisos or ["No se pudo cruzar nada con los archivos entregados."]:
            flash(aviso, "danger")
        return redirect(url_for("contabilidad.conciliacion_sii"))

    db.session.commit()
    flash(" ".join(mensajes), "success")
    for aviso in avisos:
        flash(aviso, "warning")
    return redirect(url_for("contabilidad.conciliacion_sii"))


def _documentos_filtrados(libro, args):
    """Documentos del libro con la búsqueda y el filtro de estado aplicados."""
    busqueda = (args.get("q") or "").strip()
    filtro = args.get("filtro") or ""
    if filtro not in FILTROS_CONCILIACION:
        filtro = ""

    consulta = ConciliacionSiiDocumento.query.filter_by(libro_id=libro.id)
    if busqueda:
        patron = f"%{busqueda}%"
        consulta = consulta.filter(db.or_(
            ConciliacionSiiDocumento.folio.ilike(patron),
            ConciliacionSiiDocumento.rut_sii.ilike(patron),
            ConciliacionSiiDocumento.rut_defontana.ilike(patron),
            ConciliacionSiiDocumento.contraparte_sii.ilike(patron),
            ConciliacionSiiDocumento.contraparte_defontana.ilike(patron),
        ))
    if filtro == "pendientes":
        consulta = consulta.filter(ConciliacionSiiDocumento.estado != "coincide")
    elif filtro:
        consulta = consulta.filter(ConciliacionSiiDocumento.estado == filtro)

    tipo = (args.get("tipo") or "").strip()
    if tipo:
        consulta = consulta.filter(ConciliacionSiiDocumento.tipo_doc == tipo)

    documentos = consulta.order_by(ConciliacionSiiDocumento.orden).all()
    return documentos, busqueda, filtro, tipo


def _totales_de_documentos(documentos):
    """Suma cada columna de plata de lo que se está viendo en pantalla."""
    return {
        campo: sum(getattr(d, campo) or 0 for d in documentos)
        for campo, _etiqueta in COLUMNAS_MONTO_CONCILIACION
    }


def _libro_or_404(conciliacion, clave):
    libro = conciliacion.libro_por_clave(clave)
    if libro is None:
        abort(404)
    return libro


@bp.route("/conciliacion-sii/<int:conciliacion_id>/<clave>")
@require_permission("contabilidad", "ver")
def ver_libro_conciliacion_sii(conciliacion_id, clave):
    if clave not in ("compra", "venta"):
        abort(404)
    conciliacion = _conciliacion_or_404(conciliacion_id)
    libro = _libro_or_404(conciliacion, clave)

    documentos, busqueda, filtro, tipo = _documentos_filtrados(libro, request.args)
    tipos = sorted({d.tipo_doc for d in libro.documentos}, key=lambda t: t.zfill(4))

    return render_template(
        "contabilidad/conciliacion_sii_libro.html",
        conciliacion=conciliacion,
        libro=libro,
        documentos=documentos,
        totales=_totales_de_documentos(documentos),
        columnas_monto=COLUMNAS_MONTO_CONCILIACION,
        etiquetas_estado=ESTADO_ETIQUETAS_CONCILIACION,
        tipos=tipos,
        tipos_desc=TIPOS_DOCUMENTO_SII,
        q=busqueda,
        filtro=filtro,
        tipo=tipo,
        mes_nombre=_nombre_de_mes(conciliacion.mes),
    )


@bp.route("/conciliacion-sii/<int:conciliacion_id>/<clave>.xlsx")
@require_permission("contabilidad", "ver")
def exportar_libro_conciliacion_sii(conciliacion_id, clave):
    if clave not in ("compra", "venta"):
        abort(404)
    conciliacion = _conciliacion_or_404(conciliacion_id)
    libro = _libro_or_404(conciliacion, clave)
    documentos, _q, _filtro, _tipo = _documentos_filtrados(libro, request.args)

    columnas = [
        col("Estado", ancho=20, total="texto"),
        col("Tipo Doc.", ancho=28),
        col("Folio", ancho=12),
        col("En qué se diferencia", ancho=60),
        col("Fecha", ancho=12),
        col("RUT (SII)", ancho=15),
        col("Razón social (SII)", ancho=34),
        col("RUT (Defontana)", ancho=15),
        col("Razón social (Defontana)", ancho=34),
    ]
    columnas += [col(etiqueta, ancho=16, formato=CLP, total="suma")
                 for _campo, etiqueta in COLUMNAS_MONTO_CONCILIACION]

    filas = []
    for documento in documentos:
        fila = [
            ESTADO_ETIQUETAS_CONCILIACION.get(documento.estado, documento.estado),
            documento.tipo_doc_desc or documento.tipo_doc,
            documento.folio,
            documento.diferencia_descrita or "",
            documento.fecha or "",
            documento.rut_sii or "",
            documento.contraparte_sii or "",
            documento.rut_defontana or "",
            documento.contraparte_defontana or "",
        ]
        fila += [getattr(documento, campo) or 0 for campo, _e in COLUMNAS_MONTO_CONCILIACION]
        filas.append(fila)

    etiqueta = "Compras" if clave == "compra" else "Ventas"
    periodo = f"{_nombre_de_mes(conciliacion.mes)} {conciliacion.anio}"
    return responder_excel(
        f"conciliacion-sii-{clave}-{conciliacion.anio}-{conciliacion.mes:02d}",
        f"Conciliación SII / Defontana — {etiqueta}",
        columnas,
        filas,
        periodo,
    )


@bp.route("/conciliacion-sii/<int:conciliacion_id>/eliminar", methods=["POST"])
@require_permission("contabilidad", "editar")
def eliminar_conciliacion_sii(conciliacion_id):
    conciliacion = _conciliacion_or_404(conciliacion_id)
    if not AccionForm().validate_on_submit():
        abort(400)
    etiqueta = f"{_nombre_de_mes(conciliacion.mes)} {conciliacion.anio}"
    db.session.delete(conciliacion)
    db.session.commit()
    flash(f"Se eliminó la conciliación de {etiqueta}.", "success")
    return redirect(url_for("contabilidad.conciliacion_sii"))
