from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.contabilidad import bp
from app.contabilidad.forms import AccionForm, ImportarProvisionesForm
from app.extensions import db
from app.models.contabilidad import ProvisionIngreso
from app.utils.decorators import require_permission
from app.utils.exportar import CLP, col, responder_excel
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
        db.session.add(
            ProvisionIngreso(
                empresa_id=_empresa_id(),
                **{k: v for k, v in linea.items() if k != "fila"},
            )
        )
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
        if prefijo + "saldo" not in request.form:
            continue  # línea que no está en la página que se envió
        linea.reversa = _parse_entero(request.form.get(prefijo + "reversa"))
        linea.mes_reversa = (request.form.get(prefijo + "mes_reversa") or "").strip() or None
        linea.cbte_reversa = (request.form.get(prefijo + "cbte_reversa") or "").strip() or None
        linea.saldo = _parse_entero(request.form.get(prefijo + "saldo")) or 0
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
