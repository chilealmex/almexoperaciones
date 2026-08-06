"""Lógica de cálculo del costeo detallado por producto.

Reproduce, celda por celda, la planilla de costeo de importaciones: cada línea
de producto se prorratea según su participación en el valor EXW total, y ese
mismo porcentaje reparte el flete, el seguro, el crating y los gastos internos
entre todos los productos. El resultado es el costo unitario final CLP —
"cuánto costó realmente puesto en bodega" cada producto — no solo su precio
de fábrica.
"""

DOCUMENTO_ROLES = (
    {"rol": "inv1", "etiqueta": "Invoice 1"},
    {"rol": "inv2", "etiqueta": "Invoice 2"},
    {"rol": "inv3", "etiqueta": "Invoice 3"},
    {"rol": "inv4", "etiqueta": "Invoice 4"},
    {"rol": "seguro", "etiqueta": "Seguro Cert"},
    {"rol": "flete_intl", "etiqueta": "Flete Internacional"},
    {"rol": "crating_usd", "etiqueta": "Crating USD"},
    {"rol": "crating_eur", "etiqueta": "Crating EUR"},
    {"rol": "ad_valorem", "etiqueta": "Ad Valorem"},
)
# El Ad Valorem va en la tabla de documentos, como en la planilla, pero queda
# fuera del CIF: en el Excel la fila TOTAL CIF viene antes que la de Ad Valorem.
ROL_AD_VALOREM = "ad_valorem"
ROLES_INVOICE = ("inv1", "inv2", "inv3", "inv4")

GASTO_INTERNO_ROLES = (
    {"rol": "almacenaje", "etiqueta": "Almacenaje"},
    {"rol": "desconsolidacion", "etiqueta": "Desconsolidación (vaciar contenedor)"},
    {"rol": "habilitacion", "etiqueta": "Habilitación (papeleo)"},
    {"rol": "flete_nacional", "etiqueta": "Flete Nacional"},
    {"rol": "gastos_agencia", "etiqueta": "Gastos Agencia"},
    {"rol": "cargo_terminal", "etiqueta": "Cargo Terminal (manejo carga/grúas)"},
)


def _num(valor):
    try:
        return float(valor) if valor is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _clp(valor):
    return int(round(valor))


def sembrar_lineas_fijas(costeo):
    """Crea las 8 líneas de documentos y las 6 de gastos internos, si faltan."""
    from app.extensions import db
    from app.models.costeo_importacion import CosteoImportacionDocumento, CosteoImportacionGastoInterno

    roles_doc_existentes = {d.rol for d in costeo.documentos}
    for orden, plantilla in enumerate(DOCUMENTO_ROLES):
        if plantilla["rol"] in roles_doc_existentes:
            continue
        db.session.add(
            CosteoImportacionDocumento(
                costeo=costeo, rol=plantilla["rol"], orden=orden,
                moneda="EUR" if plantilla["rol"] == "crating_eur" else "USD",
            )
        )

    roles_gasto_existentes = {g.rol for g in costeo.gastos_internos}
    for orden, plantilla in enumerate(GASTO_INTERNO_ROLES):
        if plantilla["rol"] in roles_gasto_existentes:
            continue
        db.session.add(CosteoImportacionGastoInterno(costeo=costeo, rol=plantilla["rol"], orden=orden))


def totales_documentos(costeo):
    """Agregados de la tabla de documentos (equivalentes a la fila 30 de la planilla)."""
    exw_moneda = sum(_num(costeo.documento_por_rol(r).valor_total_inv) for r in ROLES_INVOICE if costeo.documento_por_rol(r))
    exw_clp = sum(_num(costeo.documento_por_rol(r).valor_clp) for r in ROLES_INVOICE if costeo.documento_por_rol(r))

    crating_usd = costeo.documento_por_rol("crating_usd")
    crating_eur = costeo.documento_por_rol("crating_eur")
    crating_clp = _num(crating_usd.valor_clp if crating_usd else 0) + _num(crating_eur.valor_clp if crating_eur else 0)

    flete = costeo.documento_por_rol("flete_intl")
    flete_clp = _num(flete.valor_clp if flete else 0)

    seguro = costeo.documento_por_rol("seguro")
    seguro_clp = _num(seguro.valor_clp if seguro else 0)

    cif_clp = exw_clp + crating_clp + flete_clp + seguro_clp
    gastos_internos_clp = sum(_num(g.valor_clp) for g in costeo.gastos_internos)

    doc_ad_valorem = costeo.documento_por_rol(ROL_AD_VALOREM)
    ad_valorem_clp = _num(doc_ad_valorem.valor_clp if doc_ad_valorem else 0)

    return {
        "exw_moneda": exw_moneda,
        "exw_clp": exw_clp,
        "crating_clp": crating_clp,
        "flete_clp": flete_clp,
        "seguro_clp": seguro_clp,
        "cif_clp": cif_clp,
        "gastos_internos_clp": gastos_internos_clp,
        "ad_valorem_clp": ad_valorem_clp,
        "costo_total_clp": cif_clp + ad_valorem_clp + gastos_internos_clp,
    }


def recalcular(costeo):
    """Recalcula los documentos, y el prorrateo de cada línea de producto.

    Debe llamarse después de cualquier cambio a los documentos, gastos internos,
    líneas de producto o la tasa de ad valorem, antes de hacer commit.
    """
    for plantilla in DOCUMENTO_ROLES:
        doc = costeo.documento_por_rol(plantilla["rol"])
        if not doc:
            continue
        doc.valor_clp = _clp(_num(doc.valor_tc) * _num(doc.valor_total_inv))

    totales = totales_documentos(costeo)
    exw_total_moneda = sum(_num(p.valor_unitario_tc) * _num(p.cantidad) for p in costeo.productos)

    # Si se cargó el Ad Valorem como documento (el monto real de la DIN), ese
    # total se reparte solo entre los productos que sí lo pagan, en proporción
    # a lo que pesa cada uno; así se distribuye completo y no queda un resto.
    peso_afecto = sum(
        _num(p.valor_unitario_tc) * _num(p.cantidad)
        for p in costeo.productos
        if p.tiene_ad_valorem == "SI"
    )

    for producto in costeo.productos:
        exw_moneda = _num(producto.valor_unitario_tc) * _num(producto.cantidad)
        porcentaje = (exw_moneda / exw_total_moneda) if exw_total_moneda else 0.0

        exw_clp = totales["exw_clp"] * porcentaje
        crating_clp = totales["crating_clp"] * porcentaje
        flete_clp = totales["flete_clp"] * porcentaje
        seguro_clp = totales["seguro_clp"] * porcentaje
        cif_clp = exw_clp + crating_clp + flete_clp + seguro_clp
        if producto.tiene_ad_valorem != "SI":
            ad_valorem_clp = 0.0
        elif producto.ad_valorem_manual_clp is not None:
            # Monto escrito a mano en la línea: manda sobre todo lo demás.
            ad_valorem_clp = _num(producto.ad_valorem_manual_clp)
        elif totales["ad_valorem_clp"]:
            proporcion = (exw_moneda / peso_afecto) if peso_afecto else 0.0
            ad_valorem_clp = totales["ad_valorem_clp"] * proporcion
        else:
            ad_valorem_clp = cif_clp * _num(costeo.tasa_ad_valorem)
        gastos_internos_clp = totales["gastos_internos_clp"] * porcentaje
        costo_total_clp = cif_clp + ad_valorem_clp + gastos_internos_clp

        cantidad = _num(producto.cantidad)
        costo_unitario_inicial = (exw_clp / cantidad) if cantidad else 0.0
        costo_unitario_final = (costo_total_clp / cantidad) if cantidad else 0.0
        impacto_pct = (costo_unitario_final / costo_unitario_inicial - 1) if costo_unitario_inicial else 0.0

        producto.exw_moneda = round(exw_moneda, 2)
        producto.porcentaje = porcentaje
        producto.exw_clp = _clp(exw_clp)
        producto.crating_clp = _clp(crating_clp)
        producto.flete_clp = _clp(flete_clp)
        producto.seguro_clp = _clp(seguro_clp)
        producto.cif_clp = _clp(cif_clp)
        producto.ad_valorem_clp = _clp(ad_valorem_clp)
        producto.gastos_internos_clp = _clp(gastos_internos_clp)
        producto.costo_total_clp = _clp(costo_total_clp)
        producto.costo_unitario_inicial_clp = _clp(costo_unitario_inicial)
        producto.costo_unitario_final_clp = _clp(costo_unitario_final)
        producto.impacto_pct = impacto_pct


def diferencia_cuadratura(costeo, totales=None):
    """Diferencia entre el EXW total de los documentos y la suma de EXW de los productos.

    Si no da $0, algo quedó sin prorratear: falta cargar un producto, o el monto
    de algún invoice no coincide con lo que realmente se repartió.

    'totales' se puede pasar ya calculado para no repetir el recorrido cuando
    quien llama ya los tiene (por ejemplo, el listado de costeos).
    """
    totales = totales if totales is not None else totales_documentos(costeo)
    suma_productos = sum(_num(p.exw_moneda) for p in costeo.productos)
    return round(totales["exw_moneda"] - suma_productos, 2)
