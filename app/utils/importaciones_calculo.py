"""Lógica contable del módulo de Importaciones.

Reproduce, en el servidor, las fórmulas de la planilla de control de importaciones
que la empresa usaba manualmente: IVA de la factura de agencia, conversión de la
DIN desde dólares, cuadratura de la agencia, y el traspaso automático de la
diferencia de costeo al asiento de ajuste de existencias.

Los montos son pesos chilenos sin decimales (igual que el resto de la app), salvo
el monto en USD y el tipo de cambio de la DIN, que sí llevan decimales.
"""

TIPOS_ASIENTO = ("factura_agencia", "din", "cuadratura", "cuadratura_ups_dhl", "costeo", "ajuste")

ETIQUETAS_TIPO = {
    "factura_agencia": "Asiento factura agencia",
    "din": "Asiento DIN",
    "cuadratura": "Cuadratura agencia",
    "cuadratura_ups_dhl": "Cuadratura UPS/DHL",
    "costeo": "Asiento costeo importación",
    "ajuste": "Ajuste de existencias",
}

# Columnas visibles de cada grupo, en orden.
COLUMNAS_TIPO = {
    "factura_agencia": ("cuenta", "debe", "haber"),
    "din": ("cuenta", "debe", "haber"),
    "cuadratura": ("proveedor", "fecha", "tipo_doc", "n_doc", "cuenta", "debe", "haber"),
    "cuadratura_ups_dhl": ("proveedor", "fecha", "tipo_doc", "n_doc", "cuenta", "debe", "haber"),
    "costeo": ("proveedor", "fecha", "tipo_doc", "n_doc", "cuenta", "debe", "haber", "ecomex", "dif", "descripcion"),
    "ajuste": ("cbte_linea", "n_cuenta", "cuenta", "debe", "haber"),
}

ETIQUETAS_COLUMNA = {
    "proveedor": "Proveedor",
    "fecha": "Fecha",
    "tipo_doc": "Tipo doc",
    "n_doc": "N° doc",
    "cuenta": "Cuenta contable",
    "debe": "Debe",
    "haber": "Haber",
    "ecomex": "ECOMEX",
    "dif": "Dif",
    "descripcion": "Descripción",
    "cbte_linea": "Cbte",
    "n_cuenta": "N° cuenta",
}

COLUMNAS_NUMERICAS = {"debe", "haber", "ecomex", "dif"}
COLUMNAS_FECHA = {"fecha"}

TIENE_CBTE = {"factura_agencia", "din", "cuadratura", "cuadratura_ups_dhl", "ajuste"}
TIENE_SALDO_BOX = {"cuadratura", "cuadratura_ups_dhl"}
TIENE_HEADER_COMPARTIDO = {"factura_agencia", "din"}
TIENE_DIN_CALC = {"din"}
TIENE_HABER_CUADRA = {"factura_agencia", "din", "cuadratura", "cuadratura_ups_dhl"}  # se cuadran solos, costeo/ajuste no

HEADER_COMPARTIDO_DEFAULT = {
    "factura_agencia": {"proveedor": "", "tipo_doc": "FC"},
    "din": {"proveedor": "SERV NACIONAL ADUANA", "tipo_doc": "DIN"},
}

# Plantilla de líneas por defecto de cada grupo: cuentas contables fijas que se
# crean automáticamente al abrir una importación nueva.
ROW_TEMPLATES = {
    "factura_agencia": [
        {"rol": "fa_l1", "cuenta": "EX. EN TRANSITO"},
        {"rol": "fa_l2", "cuenta": "EX. EN TRANSITO"},
        {"rol": "fa_l3", "cuenta": "EX. EN TRANSITO"},
        {"rol": "fa_iva", "cuenta": "IVA CF"},
        {"rol": "fa_provnac", "cuenta": "PROVEEDOR NACIONAL"},
    ],
    "din": [
        {"rol": "din_facturaporrecibir", "cuenta": "FACTURA POR RECIBIR"},
        {"rol": "din_monto", "cuenta": "DIN"},
        {"rol": "din_provnac", "cuenta": "PROV NACIONAL (TESORERIA)"},
    ],
    "cuadratura": [
        {"rol": "cua_provnac_ini", "tipo_doc": "FC", "cuenta": "PROVEEDOR NACIONAL"},
        {"rol": "cua_anticipo", "tipo_doc": "SALDO ANTERIOR", "cuenta": "ANTICIPO AGENCIA"},
        {"rol": "cua_deudores", "tipo_doc": "SALDO NUEVO", "cuenta": "DEUDORES VARIOS"},
        {
            "rol": "cua_facturaporrecibir",
            "proveedor": "SERV NACIONAL ADUANA",
            "tipo_doc": "DIN",
            "cuenta": "FACTURA POR RECIBIR",
        },
        {"rol": "cua_provnac_tesoreria", "cuenta": "PROV NACIONAL (TESORERIA)"},
        {
            "rol": "cua_advalorem",
            "proveedor": "SERV NACIONAL ADUANA",
            "tipo_doc": "AD VALOREM",
            "cuenta": "EX. EN TRANSITO",
        },
        {"rol": "cua_provnac_final", "tipo_doc": "FC", "cuenta": "PROVEEDOR NACIONAL"},
    ],
    "cuadratura_ups_dhl": [
        {"rol": "cud_provnac", "cuenta": "PROVEEDOR NACIONAL"},
        {"rol": "cud_facturaporrecibir", "cuenta": "FACTURA POR RECIBIR"},
        {"rol": "cud_provnac_tesoreria", "cuenta": "PROV NACIONAL (TESORERIA)"},
        {"rol": "cud_extransito", "cuenta": "EX. EN TRANSITO"},
        {"rol": "cud_provnac_final", "cuenta": "PROVEEDOR NACIONAL"},
    ],
    "costeo": [
        {
            "rol": "costeo_valor",
            "tipo_doc": "PEI",
            "cuenta": "EX. EN TRANSITO",
            "descripcion": "VALOR COSTEO / ADQUISICIONES",
        },
        {"rol": "costeo_invoice", "cuenta": "EX. EN TRANSITO", "descripcion": "INVOICE"},
        {"rol": "costeo_seguro", "cuenta": "EX. EN TRANSITO", "descripcion": "SEGURO CERT"},
        {"rol": "costeo_fleteintl", "cuenta": "EX. EN TRANSITO", "descripcion": "FLETE INTERNACIONAL"},
        {"rol": "costeo_crating", "cuenta": "EX. EN TRANSITO", "descripcion": "CRATING / EMBALAJE"},
        {"rol": "costeo_advalorem", "cuenta": "EX. EN TRANSITO", "descripcion": "6% AD VALOREM"},
        {"rol": "costeo_almacenaje", "cuenta": "EX. EN TRANSITO", "descripcion": "ALMACENAJE"},
        {"rol": "costeo_desconsolidacion", "cuenta": "EX. EN TRANSITO", "descripcion": "DESCONSOLIDACIÓN"},
        {"rol": "costeo_habilitacion", "cuenta": "EX. EN TRANSITO", "descripcion": "HABILITACIÓN"},
        {"rol": "costeo_fletenacional", "cuenta": "EX. EN TRANSITO", "descripcion": "FLETE NACIONAL"},
        {"rol": "costeo_gastosagencia", "cuenta": "EX. EN TRANSITO", "descripcion": "GASTOS AGENCIA"},
        {"rol": "costeo_cargoterminal", "cuenta": "EX. EN TRANSITO", "descripcion": "CARGO TERMINAL"},
    ],
    "ajuste": [
        {"rol": "aj_extransito", "cuenta": "EX. EN TRANSITO"},
        {"rol": "aj_ajuste", "cuenta": "AJUSTE EXISTENCIAS DEL PERIODO"},
    ],
}

# Campos que el usuario no edita a mano: los calcula recalcular().
CAMPOS_CALCULADOS = {
    "factura_agencia": {"fa_iva": ("debe",), "fa_provnac": ("haber",)},
    "din": {"din_facturaporrecibir": ("debe",), "din_monto": ("debe",), "din_provnac": ("haber",)},
    "cuadratura": {
        "cua_provnac_ini": ("debe",),
        "cua_anticipo": ("haber",),
        "cua_facturaporrecibir": ("haber",),
        "cua_provnac_tesoreria": ("debe",),
    },
    "ajuste": {"aj_extransito": ("debe", "haber"), "aj_ajuste": ("debe", "haber")},
    "costeo": {"costeo_valor": ("proveedor", "fecha", "tipo_doc", "n_doc", "debe")},
}


def es_campo_calculado(tipo, rol, campo):
    if tipo == "costeo" and campo == "dif":
        return True  # la diferencia por línea siempre se calcula, tenga rol o no
    if tipo == "costeo" and campo == "descripcion" and rol:
        return True  # la descripción de una cuenta de la plantilla no se edita a mano
    roles = CAMPOS_CALCULADOS.get(tipo, {})
    return campo in roles.get(rol, ())


def _num(valor):
    try:
        return float(valor) if valor is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _clp(valor):
    """Redondea a peso entero, como el resto de los montos CLP de la app."""
    return int(round(valor))


def sembrar_lineas_plantilla(importacion):
    """Crea las líneas fijas de la plantilla en los grupos que todavía no tienen ninguna."""
    from app.extensions import db
    from app.models.importacion import ImportacionAsientoLinea, ImportacionGrupoMeta

    tipos_existentes = {linea.tipo for linea in importacion.lineas}
    for tipo in TIPOS_ASIENTO:
        if importacion.meta_de(tipo) is None:
            db.session.add(ImportacionGrupoMeta(importacion=importacion, tipo=tipo))
        if tipo in tipos_existentes:
            continue
        for orden, plantilla in enumerate(ROW_TEMPLATES.get(tipo, [])):
            db.session.add(_fila_desde_plantilla(importacion, tipo, plantilla, orden))


def agregar_lineas_faltantes(importacion, tipo):
    """Agrega las cuentas de la plantilla que todavía no existan en ese grupo (no duplica)."""
    from app.extensions import db

    existentes = {linea.rol for linea in importacion.lineas_de(tipo) if linea.rol}
    plantilla = ROW_TEMPLATES.get(tipo, [])
    orden_base = len(importacion.lineas_de(tipo))
    agregadas = 0
    for plantilla_fila in plantilla:
        if plantilla_fila["rol"] in existentes:
            continue
        db.session.add(_fila_desde_plantilla(importacion, tipo, plantilla_fila, orden_base + agregadas))
        agregadas += 1
    return agregadas


def _fila_desde_plantilla(importacion, tipo, plantilla, orden):
    from app.models.importacion import ImportacionAsientoLinea

    return ImportacionAsientoLinea(
        importacion=importacion,
        tipo=tipo,
        rol=plantilla["rol"],
        orden=orden,
        proveedor=plantilla.get("proveedor"),
        tipo_doc=plantilla.get("tipo_doc"),
        cuenta=plantilla.get("cuenta"),
        descripcion=plantilla.get("descripcion"),
    )


def _por_rol(importacion, tipo, rol):
    return importacion.linea_por_rol(tipo, rol)


def recalcular(importacion):
    """Recalcula todos los campos automáticos de una importación.

    Debe llamarse después de cualquier cambio a sus líneas, metadatos de grupo,
    o al monto/fecha/PEI de la importación, antes de hacer commit.
    """
    # --- Asiento factura agencia: IVA CF = 19% de las 3 primeras líneas ---
    fa_l1 = _por_rol(importacion, "factura_agencia", "fa_l1")
    fa_l2 = _por_rol(importacion, "factura_agencia", "fa_l2")
    fa_l3 = _por_rol(importacion, "factura_agencia", "fa_l3")
    fa_iva = _por_rol(importacion, "factura_agencia", "fa_iva")
    fa_provnac = _por_rol(importacion, "factura_agencia", "fa_provnac")
    fa_base = sum(_num(l.debe) for l in (fa_l1, fa_l2, fa_l3) if l)
    if fa_iva:
        fa_iva.debe = _clp(fa_base * 0.19)
    if fa_provnac:
        fa_provnac.haber = _clp(fa_base + _num(fa_iva.debe if fa_iva else 0))

    # --- Asiento DIN: monto DIN (CLP) = USD × tipo de cambio; factura por recibir = DIN / 0.19 ---
    din_fpr = _por_rol(importacion, "din", "din_facturaporrecibir")
    din_monto = _por_rol(importacion, "din", "din_monto")
    din_provnac = _por_rol(importacion, "din", "din_provnac")
    meta_din = importacion.meta_de("din")
    monto_usd = _num(meta_din.monto_usd) if meta_din else 0
    tipo_cambio = _num(meta_din.tipo_cambio) if meta_din else 0
    if din_monto:
        din_monto.debe = _clp(monto_usd * tipo_cambio)
    if din_fpr:
        din_fpr.debe = _clp(_num(din_monto.debe) / 0.19) if din_monto and din_monto.debe else 0
    if din_provnac:
        din_provnac.haber = _clp(_num(din_fpr.debe if din_fpr else 0) + _num(din_monto.debe if din_monto else 0))

    # --- Cuadratura agencia: se arma con los totales de factura agencia, DIN y el saldo anterior ---
    cua_provnac_ini = _por_rol(importacion, "cuadratura", "cua_provnac_ini")
    cua_anticipo = _por_rol(importacion, "cuadratura", "cua_anticipo")
    cua_fpr = _por_rol(importacion, "cuadratura", "cua_facturaporrecibir")
    cua_pnt = _por_rol(importacion, "cuadratura", "cua_provnac_tesoreria")
    meta_cua = importacion.meta_de("cuadratura")
    if cua_provnac_ini:
        cua_provnac_ini.debe = _num(fa_provnac.haber) if fa_provnac else 0
    if cua_anticipo:
        cua_anticipo.haber = _clp(_num(meta_cua.saldo_anterior_monto) if meta_cua else 0)
    if cua_fpr:
        cua_fpr.haber = _num(din_fpr.debe) if din_fpr else 0
    if cua_pnt:
        cua_pnt.debe = _num(din_provnac.haber) if din_provnac else 0

    # --- Costeo importación: NO es un asiento que cuadra, es una comparación ---
    # Línea "Valor costeo" (el monto guía) vs. la suma de costos del resto de líneas.
    # La diferencia es lo único que se contabiliza, en el ajuste de existencias.
    costeo_valor_linea = _por_rol(importacion, "costeo", "costeo_valor")
    if costeo_valor_linea:
        costeo_valor_linea.proveedor = importacion.proveedor_nombre or ""
        costeo_valor_linea.fecha = importacion.fecha_pei
        costeo_valor_linea.tipo_doc = "PEI"
        costeo_valor_linea.n_doc = importacion.pei or ""
        costeo_valor_linea.debe = _clp(_num(importacion.monto))

    filas_costeo = importacion.lineas_de("costeo")
    valor_costeo = sum(_num(f.debe) for f in filas_costeo)
    suma_costos = sum(_num(f.haber) for f in filas_costeo)
    diferencia = _clp(valor_costeo - suma_costos)
    importacion.costeo_valor = _clp(valor_costeo)
    importacion.costeo_suma = _clp(suma_costos)
    importacion.costeo_diferencia = diferencia

    descripcion_por_rol = {
        plantilla["rol"]: plantilla["descripcion"]
        for plantilla in ROW_TEMPLATES["costeo"]
        if "descripcion" in plantilla
    }
    for fila in filas_costeo:
        fila.dif = _clp(_num(fila.haber) - _num(fila.ecomex))
        if fila.rol and fila.rol in descripcion_por_rol:
            fila.descripcion = descripcion_por_rol[fila.rol]

    # --- Ajuste de existencias: recibe la diferencia de costeo automáticamente ---
    aj_ext = _por_rol(importacion, "ajuste", "aj_extransito")
    aj_adj = _por_rol(importacion, "ajuste", "aj_ajuste")
    if aj_ext and aj_adj:
        if diferencia >= 0:
            aj_ext.debe, aj_ext.haber = diferencia, 0
            aj_adj.debe, aj_adj.haber = 0, diferencia
        else:
            aj_ext.debe, aj_ext.haber = 0, abs(diferencia)
            aj_adj.debe, aj_adj.haber = abs(diferencia), 0


def totales_grupo(importacion, tipo):
    filas = importacion.lineas_de(tipo)
    debe = sum(_num(f.debe) for f in filas)
    haber = sum(_num(f.haber) for f in filas)
    return _clp(debe), _clp(haber)


def grupo_esta_cuadrado(importacion, tipo):
    if tipo not in TIENE_HABER_CUADRA:
        return True
    filas = importacion.lineas_de(tipo)
    if not filas:
        return True
    debe, haber = totales_grupo(importacion, tipo)
    return debe == haber


def tiene_descuadre(importacion):
    return any(not grupo_esta_cuadrado(importacion, tipo) for tipo in TIENE_HABER_CUADRA)


def monto_descuadre(importacion):
    total = 0
    for tipo in TIENE_HABER_CUADRA:
        if not importacion.lineas_de(tipo):
            continue
        debe, haber = totales_grupo(importacion, tipo)
        if debe != haber:
            total += abs(debe - haber)
    return total


def neto_linea(linea):
    """Debe − Haber, usado para mostrar el costeo horizontal y la matriz comparativa."""
    return _num(linea.debe) - _num(linea.haber)
