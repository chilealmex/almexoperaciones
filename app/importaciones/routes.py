from datetime import date, datetime

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.importaciones import bp
from app.importaciones.forms import (
    AccionForm,
    CosteoImportacionForm,
    DinRegistroForm,
    ImportacionForm,
    ProveedorImportacionForm,
)
from app.models.importacion import DinRegistro, Importacion, ImportacionAsientoLinea, ProveedorImportacion
from app.models.costeo_importacion import (
    CosteoImportacion,
    CosteoImportacionProducto,
)
from app.utils import importaciones_calculo as calculo
from app.utils import costeo_importacion_calculo as costeo_calculo
from app.utils.decorators import require_permission
from app.utils.exportar import CLP, FECHA, col, responder_excel
from app.utils.formatting import format_clp

MESES_ES = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)


# --- Utilidades internas ---------------------------------------------------


def _empresa_id():
    return current_user.empresa_id


def _get_importacion_or_404(importacion_id):
    importacion = Importacion.query.get_or_404(importacion_id)
    if importacion.empresa_id != _empresa_id():
        abort(404)
    return importacion


def _parse_int(valor):
    if valor in (None, ""):
        return 0
    try:
        return int(round(float(str(valor).replace(",", "."))))
    except (TypeError, ValueError):
        return 0


def _parse_float(valor):
    if valor in (None, ""):
        return 0.0
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _parse_date(valor):
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def _crear_importacion_completa(**kwargs):
    """Crea la importación con sus 6 grupos de asientos y las cuentas de la plantilla."""
    importacion = Importacion(empresa_id=_empresa_id(), **kwargs)
    db.session.add(importacion)
    db.session.flush()
    calculo.sembrar_lineas_plantilla(importacion)
    calculo.recalcular(importacion)
    return importacion


def _agencias_disponibles():
    filas = (
        db.session.query(Importacion.agencia)
        .filter(Importacion.empresa_id == _empresa_id(), Importacion.agencia.isnot(None), Importacion.agencia != "")
        .distinct()
        .order_by(Importacion.agencia)
        .all()
    )
    return [f[0] for f in filas]


def _meses_disponibles(importaciones):
    claves = sorted({i.fecha_pei.strftime("%Y-%m") for i in importaciones if i.fecha_pei}, reverse=True)
    return [(clave, f"{MESES_ES[int(clave[5:7]) - 1]} {clave[:4]}") for clave in claves]


def _query_base():
    return Importacion.query.filter_by(empresa_id=_empresa_id())


def _aplicar_filtros_lista(query, args):
    texto = args.get("texto", "").strip()
    agencia = args.get("agencia", "").strip()
    mes = args.get("mes", "").strip()
    estado = args.get("estado", "").strip()
    if texto:
        comodin = f"%{texto}%"
        query = query.filter(
            db.or_(
                Importacion.proveedor_nombre.ilike(comodin),
                Importacion.pei.ilike(comodin),
                Importacion.oc.ilike(comodin),
            )
        )
    if agencia:
        query = query.filter(Importacion.agencia == agencia)
    if mes:
        query = query.filter(db.func.strftime("%Y-%m", Importacion.fecha_pei) == mes)
    if estado:
        query = query.filter(Importacion.estado == estado)
    return query


# --- Dashboard ---------------------------------------------------------


@bp.route("/")
@require_permission("importaciones", "ver")
def dashboard():
    importaciones = _query_base().all()

    total_importaciones = len(importaciones)
    monto_total = sum(i.monto or 0 for i in importaciones)
    favor_total = sum(i.saldo_signado for i in importaciones if i.saldo_signado >= 0)
    contra_total = sum(-i.saldo_signado for i in importaciones if i.saldo_signado < 0)
    alertas = [i for i in importaciones if (i.notas and i.notas.strip()) or calculo.tiene_descuadre(i)]

    por_mes = {}
    for i in importaciones:
        if not i.fecha_pei:
            continue
        clave = i.fecha_pei.strftime("%Y-%m")
        por_mes[clave] = por_mes.get(clave, 0) + (i.monto or 0)
    meses = sorted(por_mes)[-12:]
    grafico_mes = [
        {"etiqueta": f"{MESES_ES[int(m[5:7]) - 1][:3]} {m[:4]}", "valor": por_mes[m], "texto": format_clp(por_mes[m])}
        for m in meses
    ]

    por_agencia = {}
    for i in importaciones:
        if not i.agencia:
            continue
        por_agencia[i.agencia] = por_agencia.get(i.agencia, 0) + i.saldo_signado
    agencias_saldo = sorted(por_agencia.items(), key=lambda kv: abs(kv[1]), reverse=True)[:8]

    por_proveedor = {}
    for i in importaciones:
        if not i.proveedor_nombre:
            continue
        por_proveedor[i.proveedor_nombre] = por_proveedor.get(i.proveedor_nombre, 0) + (i.monto or 0)
    top_proveedores = sorted(por_proveedor.items(), key=lambda kv: kv[1], reverse=True)[:5]
    grafico_proveedores = [
        {"etiqueta": nombre, "valor": valor, "texto": format_clp(valor)} for nombre, valor in top_proveedores
    ]

    costeos_listos = (
        CosteoImportacion.query.filter_by(empresa_id=_empresa_id(), estado="listo")
        .order_by(CosteoImportacion.fecha_llegada.desc().nullslast())
        .all()
    )

    return render_template(
        "importaciones/dashboard.html",
        total_importaciones=total_importaciones,
        monto_total=monto_total,
        favor_total=favor_total,
        contra_total=contra_total,
        alertas=alertas,
        grafico_mes=grafico_mes,
        agencias_saldo=agencias_saldo,
        grafico_proveedores=grafico_proveedores,
        costeos_listos=costeos_listos,
    )


# --- Resumen (listado y CRUD de importaciones) --------------------------


@bp.route("/resumen")
@require_permission("importaciones", "ver")
def resumen():
    query = _aplicar_filtros_lista(_query_base(), request.args)
    importaciones = query.order_by(Importacion.fecha_pei.desc().nullslast(), Importacion.id.desc()).all()

    todas = _query_base().all()
    return render_template(
        "importaciones/resumen.html",
        importaciones=importaciones,
        agencias=_agencias_disponibles(),
        meses=_meses_disponibles(todas),
        estado_form=AccionForm(),
        filtros=request.args,
    )


@bp.route("/resumen/nueva", methods=["GET", "POST"])
@require_permission("importaciones", "editar")
def nueva_importacion():
    form = ImportacionForm()
    if form.validate_on_submit():
        importacion = _crear_importacion_completa(
            fecha_pei=form.fecha_pei.data,
            pei=form.pei.data.strip() if form.pei.data else None,
            imp=form.imp.data.strip() if form.imp.data else None,
            proveedor_nombre=form.proveedor_nombre.data.strip() if form.proveedor_nombre.data else None,
            oc=form.oc.data.strip() if form.oc.data else None,
            monto=form.monto.data or 0,
            agencia=form.agencia.data.strip() if form.agencia.data else None,
            tipo_saldo=form.tipo_saldo.data,
            saldo_agencia=form.saldo_agencia.data or 0,
            pais=form.pais.data.strip() if form.pais.data else None,
            tratado_tlc=form.tratado_tlc.data or None,
            estado=form.estado.data,
            notas=form.notas.data,
        )
        db.session.commit()
        flash("Importación creada correctamente.", "success")
        return redirect(url_for("importaciones.detalle", importacion_id=importacion.id))
    return render_template("importaciones/importacion_form.html", form=form, importacion=None, proveedores=_proveedores_catalogo())


@bp.route("/resumen/<int:importacion_id>/editar", methods=["GET", "POST"])
@require_permission("importaciones", "editar")
def editar_importacion(importacion_id):
    importacion = _get_importacion_or_404(importacion_id)
    form = ImportacionForm(obj=importacion)
    if form.validate_on_submit():
        importacion.fecha_pei = form.fecha_pei.data
        importacion.pei = form.pei.data.strip() if form.pei.data else None
        importacion.imp = form.imp.data.strip() if form.imp.data else None
        importacion.proveedor_nombre = form.proveedor_nombre.data.strip() if form.proveedor_nombre.data else None
        importacion.oc = form.oc.data.strip() if form.oc.data else None
        importacion.monto = form.monto.data or 0
        importacion.agencia = form.agencia.data.strip() if form.agencia.data else None
        importacion.tipo_saldo = form.tipo_saldo.data
        importacion.saldo_agencia = form.saldo_agencia.data or 0
        importacion.pais = form.pais.data.strip() if form.pais.data else None
        importacion.tratado_tlc = form.tratado_tlc.data or None
        importacion.estado = form.estado.data
        importacion.notas = form.notas.data
        calculo.recalcular(importacion)
        db.session.commit()
        flash("Importación actualizada correctamente.", "success")
        return redirect(url_for("importaciones.resumen"))
    return render_template(
        "importaciones/importacion_form.html", form=form, importacion=importacion, proveedores=_proveedores_catalogo()
    )


@bp.route("/resumen/<int:importacion_id>/estado", methods=["POST"])
@require_permission("importaciones", "editar")
def cambiar_estado(importacion_id):
    importacion = _get_importacion_or_404(importacion_id)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    nuevo_estado = request.form.get("estado", "")
    if nuevo_estado in ("pendiente", "costeando", "cerrado"):
        importacion.estado = nuevo_estado
        db.session.commit()
    return redirect(request.referrer or url_for("importaciones.resumen"))


@bp.route("/resumen/<int:importacion_id>/eliminar", methods=["POST"])
@require_permission("importaciones", "editar")
def eliminar_importacion(importacion_id):
    importacion = _get_importacion_or_404(importacion_id)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    db.session.delete(importacion)
    db.session.commit()
    flash("Importación eliminada.", "success")
    return redirect(url_for("importaciones.resumen"))


def _proveedores_catalogo():
    return ProveedorImportacion.query.filter_by(empresa_id=_empresa_id()).order_by(ProveedorImportacion.nombre).all()


# --- Detalle contable por PEI --------------------------------------------


@bp.route("/detalle")
@require_permission("importaciones", "ver")
def detalle_index():
    pei_buscado = request.args.get("pei", "").strip()
    if pei_buscado:
        importacion = _query_base().filter_by(pei=pei_buscado).first()
        if importacion:
            return redirect(url_for("importaciones.detalle", importacion_id=importacion.id))
        flash(f'No existe una importación con PEI "{pei_buscado}". Créala primero en Resumen.', "warning")
    importaciones = _query_base().order_by(Importacion.fecha_pei.desc().nullslast(), Importacion.id.desc()).all()
    return render_template("importaciones/detalle_index.html", importaciones=importaciones)


def _construir_grupos(importacion):
    grupos = []
    for tipo in calculo.TIPOS_ASIENTO:
        lineas = importacion.lineas_de(tipo)
        debe, haber = calculo.totales_grupo(importacion, tipo)
        grupos.append(
            {
                "tipo": tipo,
                "etiqueta": calculo.ETIQUETAS_TIPO[tipo],
                "columnas": calculo.COLUMNAS_TIPO[tipo],
                "etiquetas_columna": calculo.ETIQUETAS_COLUMNA,
                "columnas_numericas": calculo.COLUMNAS_NUMERICAS,
                "columnas_fecha": calculo.COLUMNAS_FECHA,
                "lineas": lineas,
                "meta": importacion.meta_de(tipo),
                "tiene_cbte": tipo in calculo.TIENE_CBTE,
                "tiene_saldo_box": tipo in calculo.TIENE_SALDO_BOX,
                "tiene_din_calc": tipo in calculo.TIENE_DIN_CALC,
                "tiene_header_compartido": tipo in calculo.TIENE_HEADER_COMPARTIDO,
                "debe": debe,
                "haber": haber,
                "cuadrado": calculo.grupo_esta_cuadrado(importacion, tipo),
                "muestra_cuadratura": tipo in calculo.TIENE_HABER_CUADRA,
            }
        )
    return grupos


@bp.route("/detalle/<int:importacion_id>")
@require_permission("importaciones", "ver")
def detalle(importacion_id):
    importacion = _get_importacion_or_404(importacion_id)
    if not importacion.lineas:
        calculo.sembrar_lineas_plantilla(importacion)
        calculo.recalcular(importacion)
        db.session.commit()
    importaciones = _query_base().order_by(Importacion.fecha_pei.desc().nullslast(), Importacion.id.desc()).all()
    costeos_vinculados = CosteoImportacion.query.filter_by(importacion_id=importacion.id).all()
    return render_template(
        "importaciones/detalle.html",
        importacion=importacion,
        grupos=_construir_grupos(importacion),
        importaciones=importaciones,
        accion_form=AccionForm(),
        calculado_de=calculo.es_campo_calculado,
        costeos_vinculados=costeos_vinculados,
    )


def _asignar_campo_linea(linea, campo, valor):
    if campo in calculo.COLUMNAS_NUMERICAS:
        setattr(linea, campo, _parse_int(valor))
    elif campo in calculo.COLUMNAS_FECHA:
        setattr(linea, campo, _parse_date(valor))
    else:
        setattr(linea, campo, valor.strip() or None if valor else None)


def _actualizar_meta_grupo(meta, tipo, formulario):
    if tipo in calculo.TIENE_CBTE:
        meta.cbte = (formulario.get("meta-cbte") or "").strip() or None
    if tipo in calculo.TIENE_SALDO_BOX:
        meta.saldo_anterior_monto = _parse_int(formulario.get("meta-saldo_anterior_monto"))
        tipo_nuevo = formulario.get("meta-saldo_nuevo_tipo")
        meta.saldo_nuevo_tipo = tipo_nuevo if tipo_nuevo in ("a_favor", "en_contra") else "a_favor"
        meta.saldo_nuevo_cuenta = (formulario.get("meta-saldo_nuevo_cuenta") or "").strip() or None
        meta.saldo_nuevo_monto = _parse_int(formulario.get("meta-saldo_nuevo_monto"))
    if tipo in calculo.TIENE_DIN_CALC:
        meta.monto_usd = _parse_float(formulario.get("meta-monto_usd"))
        meta.tipo_cambio = _parse_float(formulario.get("meta-tipo_cambio"))
    if tipo in calculo.TIENE_HEADER_COMPARTIDO:
        meta.proveedor = (formulario.get("meta-proveedor") or "").strip() or None
        meta.fecha = _parse_date(formulario.get("meta-fecha"))
        meta.tipo_doc = (formulario.get("meta-tipo_doc") or "").strip() or None
        meta.n_doc = (formulario.get("meta-n_doc") or "").strip() or None


@bp.route("/detalle/<int:importacion_id>/grupo/<tipo>/guardar", methods=["POST"])
@require_permission("importaciones", "editar")
def guardar_grupo(importacion_id, tipo):
    importacion = _get_importacion_or_404(importacion_id)
    if tipo not in calculo.TIPOS_ASIENTO:
        abort(404)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)

    for linea in importacion.lineas_de(tipo):
        for campo in calculo.COLUMNAS_TIPO[tipo]:
            if calculo.es_campo_calculado(tipo, linea.rol, campo):
                continue
            nombre = f"linea-{linea.id}-{campo}"
            if nombre in request.form:
                _asignar_campo_linea(linea, campo, request.form.get(nombre, ""))

    meta = importacion.meta_de(tipo)
    if meta is not None:
        _actualizar_meta_grupo(meta, tipo, request.form)

    calculo.recalcular(importacion)
    db.session.commit()
    flash("Cambios guardados.", "success")
    return redirect(url_for("importaciones.detalle", importacion_id=importacion.id) + f"#grupo-{tipo}")


@bp.route("/detalle/<int:importacion_id>/grupo/<tipo>/agregar-linea", methods=["POST"])
@require_permission("importaciones", "editar")
def agregar_linea(importacion_id, tipo):
    importacion = _get_importacion_or_404(importacion_id)
    if tipo not in calculo.TIPOS_ASIENTO:
        abort(404)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    orden = len(importacion.lineas_de(tipo))
    db.session.add(ImportacionAsientoLinea(importacion=importacion, tipo=tipo, orden=orden))
    db.session.commit()
    return redirect(url_for("importaciones.detalle", importacion_id=importacion.id) + f"#grupo-{tipo}")


@bp.route("/detalle/<int:importacion_id>/grupo/<tipo>/completar-plantilla", methods=["POST"])
@require_permission("importaciones", "editar")
def completar_plantilla(importacion_id, tipo):
    importacion = _get_importacion_or_404(importacion_id)
    if tipo not in calculo.TIPOS_ASIENTO:
        abort(404)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    agregadas = calculo.agregar_lineas_faltantes(importacion, tipo)
    calculo.recalcular(importacion)
    db.session.commit()
    if agregadas:
        flash(f"Se agregaron {agregadas} línea(s) de la plantilla.", "success")
    else:
        flash("Ya están todas las cuentas contables de la plantilla.", "info")
    return redirect(url_for("importaciones.detalle", importacion_id=importacion.id) + f"#grupo-{tipo}")


# Rol del asiento "Costeo importación" (Detalle por PEI) <- de dónde sale su monto
# en el Costeo por producto vinculado. "gasto" son los 6 gastos internos fijos;
# el resto se lee de los totales agregados de la tabla de documentos.
MAPA_COSTEO_PRODUCTO_A_ASIENTO = {
    "costeo_invoice": ("total", "exw_clp"),
    "costeo_seguro": ("total", "seguro_clp"),
    "costeo_fleteintl": ("total", "flete_clp"),
    "costeo_crating": ("total", "crating_clp"),
    "costeo_almacenaje": ("gasto", "almacenaje"),
    "costeo_desconsolidacion": ("gasto", "desconsolidacion"),
    "costeo_habilitacion": ("gasto", "habilitacion"),
    "costeo_fletenacional": ("gasto", "flete_nacional"),
    "costeo_gastosagencia": ("gasto", "gastos_agencia"),
    "costeo_cargoterminal": ("gasto", "cargo_terminal"),
}


@bp.route("/detalle/<int:importacion_id>/grupo/costeo/traer-costeo-producto", methods=["POST"])
@require_permission("importaciones", "editar")
def traer_costeo_producto(importacion_id):
    importacion = _get_importacion_or_404(importacion_id)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)

    costeo_producto = CosteoImportacion.query.filter_by(importacion_id=importacion.id).first()
    if not costeo_producto:
        flash("Esta importación no tiene un Costeo vinculado.", "warning")
        return redirect(url_for("importaciones.detalle", importacion_id=importacion.id) + "#grupo-costeo")

    totales = costeo_calculo.totales_documentos(costeo_producto)
    ad_valorem_total = sum(p.ad_valorem_clp or 0 for p in costeo_producto.productos)

    actualizadas = 0
    for rol, (origen, clave) in MAPA_COSTEO_PRODUCTO_A_ASIENTO.items():
        linea = importacion.linea_por_rol("costeo", rol)
        if not linea:
            continue
        if origen == "total":
            linea.haber = totales[clave]
        else:
            gasto = costeo_producto.gasto_por_rol(clave)
            linea.haber = gasto.valor_clp if gasto else 0
        actualizadas += 1

    linea_advalorem = importacion.linea_por_rol("costeo", "costeo_advalorem")
    if linea_advalorem:
        linea_advalorem.haber = ad_valorem_total
        actualizadas += 1

    calculo.recalcular(importacion)
    db.session.commit()
    flash(f"Se trajeron {actualizadas} monto(s) desde el Costeo.", "success")
    return redirect(url_for("importaciones.detalle", importacion_id=importacion.id) + "#grupo-costeo")


@bp.route("/detalle/linea/<int:linea_id>/eliminar", methods=["POST"])
@require_permission("importaciones", "editar")
def eliminar_linea(linea_id):
    linea = ImportacionAsientoLinea.query.get_or_404(linea_id)
    importacion = _get_importacion_or_404(linea.importacion_id)
    tipo = linea.tipo
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    db.session.delete(linea)
    db.session.flush()
    calculo.recalcular(importacion)
    db.session.commit()
    return redirect(url_for("importaciones.detalle", importacion_id=importacion.id) + f"#grupo-{tipo}")


# --- Agencias (vista derivada) --------------------------------------------


@bp.route("/agencias")
@require_permission("importaciones", "ver")
def agencias():
    query = _aplicar_filtros_lista(_query_base(), request.args)
    importaciones = query.order_by(Importacion.fecha_pei.desc().nullslast()).all()

    grupos = {}
    for i in importaciones:
        clave = i.agencia or "Sin agencia"
        grupos.setdefault(clave, []).append(i)

    bloques = []
    for agencia_nombre in sorted(grupos):
        lista = grupos[agencia_nombre]
        saldo_total = sum(i.saldo_signado for i in lista)
        bloques.append({"agencia": agencia_nombre, "importaciones": lista, "saldo_total": saldo_total})
    bloques.sort(key=lambda b: abs(b["saldo_total"]), reverse=True)

    todas = _query_base().all()
    return render_template(
        "importaciones/agencias.html",
        bloques=bloques,
        agencias=_agencias_disponibles(),
        meses=_meses_disponibles(todas),
        filtros=request.args,
    )


# --- Proveedores (catálogo) ------------------------------------------------


@bp.route("/proveedores")
@require_permission("importaciones", "ver")
def proveedores():
    texto = request.args.get("texto", "").strip()
    query = ProveedorImportacion.query.filter_by(empresa_id=_empresa_id())
    if texto:
        comodin = f"%{texto}%"
        query = query.filter(db.or_(ProveedorImportacion.nombre.ilike(comodin), ProveedorImportacion.rut.ilike(comodin)))
    lista = query.order_by(ProveedorImportacion.nombre).all()
    return render_template("importaciones/proveedores_lista.html", proveedores=lista, filtros=request.args)


@bp.route("/proveedores/nuevo", methods=["GET", "POST"])
@require_permission("importaciones", "editar")
def nuevo_proveedor():
    form = ProveedorImportacionForm()
    if form.validate_on_submit():
        proveedor = ProveedorImportacion(
            empresa_id=_empresa_id(),
            rut=form.rut.data.strip() if form.rut.data else None,
            nombre=form.nombre.data.strip(),
            pais=form.pais.data.strip() if form.pais.data else None,
            tratado_tlc=form.tratado_tlc.data or None,
        )
        db.session.add(proveedor)
        db.session.commit()
        flash("Proveedor creado correctamente.", "success")
        return redirect(url_for("importaciones.proveedores"))
    return render_template("importaciones/proveedor_form.html", form=form, proveedor=None)


@bp.route("/proveedores/<int:proveedor_id>/editar", methods=["GET", "POST"])
@require_permission("importaciones", "editar")
def editar_proveedor(proveedor_id):
    proveedor = ProveedorImportacion.query.get_or_404(proveedor_id)
    if proveedor.empresa_id != _empresa_id():
        abort(404)
    form = ProveedorImportacionForm(obj=proveedor)
    if form.validate_on_submit():
        proveedor.rut = form.rut.data.strip() if form.rut.data else None
        proveedor.nombre = form.nombre.data.strip()
        proveedor.pais = form.pais.data.strip() if form.pais.data else None
        proveedor.tratado_tlc = form.tratado_tlc.data or None
        db.session.commit()
        flash("Proveedor actualizado correctamente.", "success")
        return redirect(url_for("importaciones.proveedores"))
    return render_template("importaciones/proveedor_form.html", form=form, proveedor=proveedor)


@bp.route("/proveedores/<int:proveedor_id>/eliminar", methods=["POST"])
@require_permission("importaciones", "editar")
def eliminar_proveedor(proveedor_id):
    proveedor = ProveedorImportacion.query.get_or_404(proveedor_id)
    if proveedor.empresa_id != _empresa_id():
        abort(404)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    db.session.delete(proveedor)
    db.session.commit()
    flash("Proveedor eliminado.", "success")
    return redirect(url_for("importaciones.proveedores"))


# --- Control DIN -------------------------------------------------------


@bp.route("/din")
@require_permission("importaciones", "ver")
def din():
    query = DinRegistro.query.filter_by(empresa_id=_empresa_id())
    texto = request.args.get("texto", "").strip()
    agencia = request.args.get("agencia", "").strip()
    mes = request.args.get("mes", "").strip()
    estado = request.args.get("estado", "").strip()
    if texto:
        comodin = f"%{texto}%"
        query = query.filter(
            db.or_(
                DinRegistro.oc.ilike(comodin),
                DinRegistro.proveedor.ilike(comodin),
                DinRegistro.folio.ilike(comodin),
                DinRegistro.n_invoice.ilike(comodin),
            )
        )
    if agencia:
        query = query.filter(DinRegistro.agencia == agencia)
    if mes:
        query = query.filter(db.func.strftime("%Y-%m", DinRegistro.fecha_pago) == mes)
    if estado:
        query = query.filter(DinRegistro.estado == estado)

    registros = query.order_by(DinRegistro.fecha_pago.desc().nullslast(), DinRegistro.id.desc()).all()

    todos = DinRegistro.query.filter_by(empresa_id=_empresa_id()).all()
    agencias_din = sorted({r.agencia for r in todos if r.agencia})
    meses_din = sorted({r.fecha_pago.strftime("%Y-%m") for r in todos if r.fecha_pago}, reverse=True)
    meses_din = [(clave, f"{MESES_ES[int(clave[5:7]) - 1]} {clave[:4]}") for clave in meses_din]

    kpi_pagado = sum(r.total_pagado or 0 for r in registros)
    kpi_doc_agencia = sum(r.monto_doc_agencia or 0 for r in registros)
    kpi_advalorem = sum(r.advalorem or 0 for r in registros)
    kpi_revision = sum(1 for r in registros if r.estado == "revision")

    return render_template(
        "importaciones/din_lista.html",
        registros=registros,
        agencias=agencias_din,
        meses=meses_din,
        filtros=request.args,
        kpi_pagado=kpi_pagado,
        kpi_doc_agencia=kpi_doc_agencia,
        kpi_advalorem=kpi_advalorem,
        kpi_revision=kpi_revision,
        accion_form=AccionForm(),
    )


@bp.route("/din/nueva", methods=["GET", "POST"])
@require_permission("importaciones", "editar")
def nueva_din():
    form = DinRegistroForm()
    if form.validate_on_submit():
        registro = DinRegistro(empresa_id=_empresa_id())
        form.populate_obj(registro)
        db.session.add(registro)
        db.session.commit()
        flash("Registro de DIN creado correctamente.", "success")
        return redirect(url_for("importaciones.din"))
    return render_template("importaciones/din_form.html", form=form, registro=None)


@bp.route("/din/<int:din_id>/editar", methods=["GET", "POST"])
@require_permission("importaciones", "editar")
def editar_din(din_id):
    registro = DinRegistro.query.get_or_404(din_id)
    if registro.empresa_id != _empresa_id():
        abort(404)
    form = DinRegistroForm(obj=registro)
    if form.validate_on_submit():
        form.populate_obj(registro)
        db.session.commit()
        flash("Registro de DIN actualizado correctamente.", "success")
        return redirect(url_for("importaciones.din"))
    return render_template("importaciones/din_form.html", form=form, registro=registro)


@bp.route("/din/<int:din_id>/eliminar", methods=["POST"])
@require_permission("importaciones", "editar")
def eliminar_din(din_id):
    registro = DinRegistro.query.get_or_404(din_id)
    if registro.empresa_id != _empresa_id():
        abort(404)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    db.session.delete(registro)
    db.session.commit()
    flash("Registro de DIN eliminado.", "success")
    return redirect(url_for("importaciones.din"))


@bp.route("/din.xlsx")
@require_permission("importaciones", "ver")
def din_excel():
    query = DinRegistro.query.filter_by(empresa_id=_empresa_id())
    registros = query.order_by(DinRegistro.fecha_pago.desc().nullslast()).all()

    columnas = [
        col("N°", ancho=10),
        col("OC", ancho=12),
        col("Agencia", ancho=18),
        col("N° Doc Agencia", ancho=16),
        col("Monto Doc Agencia", ancho=16, formato=CLP, total="suma"),
        col("Proveedor/Cliente", ancho=28),
        col("N° Invoice", ancho=16),
        col("Estado", ancho=12),
        col("RUT", ancho=14),
        col("Razón social", ancho=26),
        col("Form.", ancho=8),
        col("Folio", ancho=14),
        col("Fecha pago", ancho=14, formato=FECHA),
        col("Vcto", ancho=14, formato=FECHA),
        col("Advalorem", ancho=14, formato=CLP, total="suma"),
        col("Total pagado", ancho=14, formato=CLP, total="suma"),
    ]
    filas = [
        [
            r.numero or "",
            r.oc or "",
            r.agencia or "",
            r.n_doc_agencia or "",
            r.monto_doc_agencia or 0,
            r.proveedor or "",
            r.n_invoice or "",
            dict([("pendiente", "Pendiente"), ("revision", "Revisión"), ("pagado", "Pagado")]).get(r.estado, r.estado),
            r.rut or "",
            r.razon_social or "",
            r.formulario or "",
            r.folio or "",
            datetime.combine(r.fecha_pago, datetime.min.time()) if r.fecha_pago else None,
            datetime.combine(r.vcto, datetime.min.time()) if r.vcto else None,
            r.advalorem or 0,
            r.total_pagado or 0,
        ]
        for r in registros
    ]

    return responder_excel("control-din", "Control de DIN", columnas, filas)


# --- Costeo detallado (prorrateo por producto) ---------------------------


def _get_costeo_or_404(costeo_id):
    costeo = CosteoImportacion.query.get_or_404(costeo_id)
    if costeo.empresa_id != _empresa_id():
        abort(404)
    return costeo


def _opciones_importacion_para_costeo():
    lista = _query_base().order_by(Importacion.fecha_pei.desc().nullslast()).all()
    return [(0, "— Sin vincular —")] + [
        (i.id, f"PEI {i.pei or i.id} — {i.proveedor_nombre or 'Sin proveedor'}") for i in lista
    ]


def _poblar_costeo_desde_form(costeo, form):
    costeo.n_importacion = form.n_importacion.data.strip() if form.n_importacion.data else None
    costeo.fecha_llegada = form.fecha_llegada.data
    costeo.guia_despacho = form.guia_despacho.data.strip() if form.guia_despacho.data else None
    costeo.proveedor = form.proveedor.data.strip() if form.proveedor.data else None
    costeo.modo_venta = form.modo_venta.data.strip() if form.modo_venta.data else None
    costeo.purchase_order = form.purchase_order.data.strip() if form.purchase_order.data else None
    costeo.orden_trabajo = form.orden_trabajo.data.strip() if form.orden_trabajo.data else None
    costeo.responsable_costeo = form.responsable_costeo.data.strip() if form.responsable_costeo.data else None
    costeo.tipo_flete_proyectado = (
        form.tipo_flete_proyectado.data.strip() if form.tipo_flete_proyectado.data else None
    )
    costeo.solicitud_compra = form.solicitud_compra.data.strip() if form.solicitud_compra.data else None
    costeo.tasa_ad_valorem = (form.tasa_ad_valorem.data or 0) / 100
    costeo.estado = form.estado.data
    costeo.importacion_id = form.importacion_id.data or None

    costeo.din_agencia = form.din_agencia.data.strip() if form.din_agencia.data else None
    costeo.din_n_doc_agencia = form.din_n_doc_agencia.data.strip() if form.din_n_doc_agencia.data else None
    costeo.din_monto_doc_agencia = form.din_monto_doc_agencia.data
    costeo.din_n_invoice = form.din_n_invoice.data.strip() if form.din_n_invoice.data else None
    costeo.din_estado = form.din_estado.data or None
    costeo.din_rut = form.din_rut.data.strip() if form.din_rut.data else None
    costeo.din_razon_social = form.din_razon_social.data.strip() if form.din_razon_social.data else None
    costeo.din_formulario = form.din_formulario.data.strip() if form.din_formulario.data else None
    costeo.din_folio = form.din_folio.data.strip() if form.din_folio.data else None
    costeo.din_fecha_pago = form.din_fecha_pago.data
    costeo.din_vcto = form.din_vcto.data
    costeo.din_advalorem_clp = form.din_advalorem_clp.data
    costeo.din_total_pagado = form.din_total_pagado.data


@bp.route("/costeo-detallado")
@require_permission("importaciones", "ver")
def costeo_detallado_lista():
    lista = (
        CosteoImportacion.query.filter_by(empresa_id=_empresa_id())
        .order_by(CosteoImportacion.fecha_llegada.desc().nullslast(), CosteoImportacion.id.desc())
        .all()
    )
    resumen = []
    for costeo in lista:
        totales = costeo_calculo.totales_documentos(costeo)
        resumen.append(
            {
                "costeo": costeo,
                "costo_total_clp": totales["costo_total_clp"],
                "cantidad_productos": len(costeo.productos),
                "cuadrado": abs(costeo_calculo.diferencia_cuadratura(costeo)) < 0.01,
            }
        )
    return render_template("importaciones/costeo_detallado_lista.html", resumen=resumen, accion_form=AccionForm())


@bp.route("/costeo-detallado/nueva", methods=["GET", "POST"])
@require_permission("importaciones", "editar")
def nuevo_costeo_detallado():
    form = CosteoImportacionForm()
    form.importacion_id.choices = _opciones_importacion_para_costeo()
    if form.validate_on_submit():
        costeo = CosteoImportacion(empresa_id=_empresa_id())
        _poblar_costeo_desde_form(costeo, form)
        db.session.add(costeo)
        db.session.flush()
        costeo_calculo.sembrar_lineas_fijas(costeo)
        db.session.commit()
        flash("Costeo creado correctamente.", "success")
        return redirect(url_for("importaciones.ver_costeo_detallado", costeo_id=costeo.id))
    return render_template("importaciones/costeo_detallado_form.html", form=form, costeo=None)


@bp.route("/costeo-detallado/<int:costeo_id>/editar", methods=["GET", "POST"])
@require_permission("importaciones", "editar")
def editar_costeo_detallado(costeo_id):
    costeo = _get_costeo_or_404(costeo_id)
    form = CosteoImportacionForm(obj=costeo)
    form.importacion_id.choices = _opciones_importacion_para_costeo()
    if request.method == "GET":
        form.tasa_ad_valorem.data = (costeo.tasa_ad_valorem or 0) * 100
        form.importacion_id.data = costeo.importacion_id or 0
    if form.validate_on_submit():
        _poblar_costeo_desde_form(costeo, form)
        costeo_calculo.recalcular(costeo)
        db.session.commit()
        flash("Datos generales actualizados.", "success")
        return redirect(url_for("importaciones.ver_costeo_detallado", costeo_id=costeo.id))
    return render_template("importaciones/costeo_detallado_form.html", form=form, costeo=costeo)


@bp.route("/costeo-detallado/<int:costeo_id>/estado", methods=["POST"])
@require_permission("importaciones", "editar")
def cambiar_estado_costeo(costeo_id):
    costeo = _get_costeo_or_404(costeo_id)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    nuevo_estado = request.form.get("estado", "")
    if nuevo_estado in ("en_proceso", "listo", "contabilizado"):
        costeo.estado = nuevo_estado
        db.session.commit()
    return redirect(request.referrer or url_for("importaciones.costeo_detallado_lista"))


@bp.route("/costeo-detallado/<int:costeo_id>/eliminar", methods=["POST"])
@require_permission("importaciones", "editar")
def eliminar_costeo_detallado(costeo_id):
    costeo = _get_costeo_or_404(costeo_id)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    db.session.delete(costeo)
    db.session.commit()
    flash("Costeo eliminado.", "success")
    return redirect(url_for("importaciones.costeo_detallado_lista"))


@bp.route("/costeo-detallado/<int:costeo_id>")
@require_permission("importaciones", "ver")
def ver_costeo_detallado(costeo_id):
    costeo = _get_costeo_or_404(costeo_id)
    if not costeo.documentos or not costeo.gastos_internos:
        costeo_calculo.sembrar_lineas_fijas(costeo)
        costeo_calculo.recalcular(costeo)
        db.session.commit()
    totales = costeo_calculo.totales_documentos(costeo)
    diferencia = costeo_calculo.diferencia_cuadratura(costeo)
    return render_template(
        "importaciones/costeo_detallado_ver.html",
        costeo=costeo,
        totales=totales,
        diferencia=diferencia,
        documento_roles=costeo_calculo.DOCUMENTO_ROLES,
        gasto_roles=costeo_calculo.GASTO_INTERNO_ROLES,
        accion_form=AccionForm(),
    )


@bp.route("/costeo-detallado/<int:costeo_id>/documentos/guardar", methods=["POST"])
@require_permission("importaciones", "editar")
def guardar_documentos_costeo(costeo_id):
    costeo = _get_costeo_or_404(costeo_id)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    for plantilla in costeo_calculo.DOCUMENTO_ROLES:
        doc = costeo.documento_por_rol(plantilla["rol"])
        if not doc:
            continue
        prefijo = f"doc-{doc.id}-"
        doc.moneda = request.form.get(prefijo + "moneda", doc.moneda) or "USD"
        doc.nro_doc = (request.form.get(prefijo + "nro_doc") or "").strip() or None
        if plantilla["es_directo"]:
            doc.valor_clp = _parse_int(request.form.get(prefijo + "valor_clp"))
        else:
            doc.valor_tc = _parse_float(request.form.get(prefijo + "valor_tc"))
            doc.valor_total_inv = _parse_float(request.form.get(prefijo + "valor_total_inv"))
    costeo_calculo.recalcular(costeo)
    db.session.commit()
    flash("Documentos guardados.", "success")
    return redirect(url_for("importaciones.ver_costeo_detallado", costeo_id=costeo.id) + "#documentos")


@bp.route("/costeo-detallado/<int:costeo_id>/gastos/guardar", methods=["POST"])
@require_permission("importaciones", "editar")
def guardar_gastos_costeo(costeo_id):
    costeo = _get_costeo_or_404(costeo_id)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    for gasto in costeo.gastos_internos:
        prefijo = f"gasto-{gasto.id}-"
        gasto.nro_doc = (request.form.get(prefijo + "nro_doc") or "").strip() or None
        gasto.valor_clp = _parse_int(request.form.get(prefijo + "valor_clp"))
    costeo_calculo.recalcular(costeo)
    db.session.commit()
    flash("Gastos internos guardados.", "success")
    return redirect(url_for("importaciones.ver_costeo_detallado", costeo_id=costeo.id) + "#gastos")


@bp.route("/costeo-detallado/<int:costeo_id>/productos/guardar", methods=["POST"])
@require_permission("importaciones", "editar")
def guardar_productos_costeo(costeo_id):
    costeo = _get_costeo_or_404(costeo_id)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    for producto in costeo.productos:
        prefijo = f"prod-{producto.id}-"
        if prefijo + "producto" not in request.form:
            continue
        producto.producto = (request.form.get(prefijo + "producto") or "").strip() or None
        producto.codigo = (request.form.get(prefijo + "codigo") or "").strip() or None
        producto.valor_unitario_tc = _parse_float(request.form.get(prefijo + "valor_unitario_tc"))
        producto.cantidad = _parse_float(request.form.get(prefijo + "cantidad"))
        producto.unidad_tc = request.form.get(prefijo + "unidad_tc") or "USD"
        producto.activo_fijo = request.form.get(prefijo + "activo_fijo") or "NO"
        producto.tiene_ad_valorem = request.form.get(prefijo + "tiene_ad_valorem") or "NO"
    costeo_calculo.recalcular(costeo)
    db.session.commit()
    flash("Productos guardados.", "success")
    return redirect(url_for("importaciones.ver_costeo_detallado", costeo_id=costeo.id) + "#productos")


@bp.route("/costeo-detallado/<int:costeo_id>/productos/agregar", methods=["POST"])
@require_permission("importaciones", "editar")
def agregar_producto_costeo(costeo_id):
    costeo = _get_costeo_or_404(costeo_id)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    orden = len(costeo.productos)
    db.session.add(
        CosteoImportacionProducto(
            costeo=costeo, orden=orden, unidad_tc="USD", activo_fijo="NO", tiene_ad_valorem="SI"
        )
    )
    db.session.commit()
    return redirect(url_for("importaciones.ver_costeo_detallado", costeo_id=costeo.id) + "#productos")


@bp.route("/costeo-detallado/producto/<int:producto_id>/eliminar", methods=["POST"])
@require_permission("importaciones", "editar")
def eliminar_producto_costeo(producto_id):
    producto = CosteoImportacionProducto.query.get_or_404(producto_id)
    costeo = _get_costeo_or_404(producto.costeo_id)
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    db.session.delete(producto)
    db.session.flush()
    costeo_calculo.recalcular(costeo)
    db.session.commit()
    return redirect(url_for("importaciones.ver_costeo_detallado", costeo_id=costeo.id) + "#productos")
