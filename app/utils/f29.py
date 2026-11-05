"""La propuesta del F29, armada con el Libro Mayor.

El F29 se llena con lo que las cuentas de impuestos movieron en el mes, y esas
cuentas están en el Libro Mayor. Lo que el formulario separa en códigos
distintos —las facturas del giro, las de importación, las notas de crédito— el
mayor lo separa por el tipo del asiento ("Cpra_FCA", "Cpra_DI", "Cpra_NCC"),
así que alcanza con agrupar por ahí.

Comprobado contra el F29 de septiembre de 2026 (folio 9383590556) y el mayor
de la cuenta de IVA crédito fiscal del mismo mes:

    código 519  113 documentos     mayor  112 FCA + 1 FCEDIESEL = 113
    código 520  9.167.806          mayor  8.990.287 + 177.520 = 9.167.807
    código 527  1 nota de crédito  mayor  1 NCC
    código 528  27.574             mayor  27.574
    código 534  3 formularios      mayor  3 DI
    código 535  19.203.138         mayor  19.203.138
    código 537  28.343.370         mayor  el traspaso del mes, 28.343.370

El peso de diferencia del 520 es el redondeo del IVA documento por documento.
"""

# Los códigos del formulario, con la glosa tal como la escribe el SII. Salen
# del F29 de septiembre de 2026: no están puestos de memoria.
GLOSAS = {
    "503": "CANTIDAD FACTURAS EMITIDAS",
    "502": "DÉBITOS FACTURAS EMITIDAS",
    "509": "CANT. DCTOS. NOTAS DE CRÉDITOS EMITIDAS",
    "510": "DÉBITOS NOTAS DE CRÉDITOS EMITIDAS",
    "538": "TOTAL DÉBITOS",
    "519": "CANT. DE DCTOS. FACT. RECIB. DEL GIRO",
    "520": "CRÉDITO REC. Y REINT./FACT. DEL GIRO",
    "527": "CANT. NOTAS DE CRÉDITO RECIBIDAS",
    "528": "CRÉDITO RECUP. Y REINT NOTAS DE CRÉD",
    "534": "CANT. FORM. PAGO IMP. DEL GIRO",
    "535": "CRÉD, RECUP. Y REINT. PAGO IMP. DEL GIRO",
    "537": "TOTAL CRÉDITOS",
    "089": "IMP. DETERM. IVA",
    "048": "RET. IMP. ÚNICO TRAB. ART. 74 N 1 LIR",
    "151": "RETENCION TASA LEY 21.133 SOBRE RENTAS",
    "062": "PPM NETO DETERMINADO",
    "595": "SUB TOTAL IMP. DETERMINADO ANVERSO",
    "547": "TOTAL DETERMINADO",
    "091": "TOTAL A PAGAR DENTRO DEL PLAZO LEGAL",
}

# Qué cuenta del mayor alimenta cada parte del formulario.
CONCEPTOS = {
    "iva_debito": "IVA débito fiscal",
    "iva_credito": "IVA crédito fiscal",
    "iva_retenido": "IVA retenido por pagar",
    "impuesto_unico": "Retención impuesto único a los trabajadores",
    "honorarios": "Retención sobre honorarios",
    "ppm": "Pagos provisionales mensuales",
}

# Las dos que no pueden faltar: sin ellas no hay débitos ni créditos que
# declarar.
CONCEPTOS_IVA = ("iva_debito", "iva_credito")


def _normalizar(nombre) -> str:
    return "".join(c for c in str(nombre or "").upper() if c.isalnum())


def concepto_de_cuenta(nombre) -> str:
    """A qué parte del F29 aporta la cuenta, según su nombre.

    Se reconoce por el nombre y no por el código, porque el código del plan de
    cuentas cambia de una empresa a otra y el nombre no.
    """
    n = _normalizar(nombre)
    if "IVA" in n:
        if "RETENIDO" in n:
            return "iva_retenido"
        if "DEBITO" in n:
            return "iva_debito"
        if "CREDITO" in n:
            return "iva_credito"
        return ""
    if "PPM" in n or "PAGOPROVISIONAL" in n or "PAGOSPROVISIONALES" in n:
        return "ppm"
    if "HONORARIO" in n:
        return "honorarios"
    if "IMPUESTOUNICO" in n or ("UNICO" in n and "TRABAJADOR" in n):
        return "impuesto_unico"
    return ""


def familia_de_tipo(tipo) -> str:
    """Qué clase de documento es el asiento, por el tipo que le puso Defontana.

    El tipo viene como "Cpra_FCA", "Cpra_DI", "Cpra_NCC", "Vta_FVA". Lo que
    importa es lo que va después del guion bajo, porque el formulario declara
    por separado las notas de crédito y los documentos de importación.
    """
    sufijo = str(tipo or "").split("_")[-1].upper()
    if sufijo.startswith("DI"):
        return "importacion"
    if sufijo.startswith("NC"):
        return "nota_credito"
    return "documento"


def _grupos(cuenta) -> dict:
    """Lo que movió la cuenta en el mes, juntado por clase de documento.

    Las líneas que no nombran documento —el traspaso del saldo a IVA por
    pagar, la apertura— quedan aparte: no son nada que el formulario declare,
    y sumarlas al crédito del mes lo dejaría al doble.
    """
    grupos = {}
    for movimiento in cuenta.get("movimientos", ()):
        documentos = movimiento.get("documentos") or 0
        familia = familia_de_tipo(movimiento.get("tipo")) if documentos else "sin_documento"
        grupo = grupos.setdefault(
            familia, {"monto": 0, "documentos": 0, "lineas": 0, "tipos": []}
        )
        neto = (movimiento.get("debe") or 0) - (movimiento.get("haber") or 0)
        grupo["monto"] += neto * (cuenta.get("signo") or 1)
        grupo["documentos"] += documentos
        grupo["lineas"] += movimiento.get("lineas") or 0
        grupo["tipos"].append(movimiento.get("tipo"))
    # Una nota de crédito mueve la cuenta al revés que una factura, y el
    # formulario la pide en positivo para restarla después.
    if "nota_credito" in grupos:
        grupos["nota_credito"]["monto"] = -grupos["nota_credito"]["monto"]
    return grupos


def _lado_declarado(cuenta) -> int:
    """Lo retenido o provisionado en el mes, que es un solo lado de la cuenta.

    En estas cuentas el otro lado es el pago del mes anterior: el impuesto
    único retenido en septiembre queda al haber, y el pago de agosto al debe.
    Restarlos daría casi cero y no es lo que se declara.
    """
    debe = sum(m.get("debe") or 0 for m in cuenta.get("movimientos", ()))
    haber = sum(m.get("haber") or 0 for m in cuenta.get("movimientos", ()))
    return haber if (cuenta.get("signo") or 1) < 0 else debe


def propuesta_f29(cuentas) -> dict:
    """La propuesta del F29 con las cuentas del mayor de un mes.

    Devuelve las líneas del formulario con su código, de dónde salió cada una
    y qué falta para que esté completa. No inventa códigos: lo que no se pudo
    sacar del F29 de referencia queda dicho como tal.
    """
    por_concepto = {}
    for cuenta in cuentas:
        por_concepto.setdefault(cuenta.get("concepto") or "", []).append(cuenta)

    lineas, avisos = [], []

    def poner(codigo, valor, de, clase="monto"):
        lineas.append({"codigo": codigo, "glosa": GLOSAS[codigo], "valor": valor,
                       "de": de, "clase": clase})

    def grupos_de(concepto):
        juntos = {}
        for cuenta in por_concepto.get(concepto, ()):
            for familia, grupo in _grupos(cuenta).items():
                destino = juntos.setdefault(
                    familia, {"monto": 0, "documentos": 0, "lineas": 0, "tipos": []}
                )
                destino["monto"] += grupo["monto"]
                destino["documentos"] += grupo["documentos"]
                destino["lineas"] += grupo["lineas"]
                destino["tipos"] += grupo["tipos"]
        return juntos

    vacio = {"monto": 0, "documentos": 0, "lineas": 0, "tipos": []}

    # --- Débitos: lo que se vendió -------------------------------------
    debito = grupos_de("iva_debito")
    facturas = debito.get("documento", vacio)
    notas_v = debito.get("nota_credito", vacio)
    nombre_debito = _nombres(por_concepto.get("iva_debito"))
    poner("503", facturas["documentos"], nombre_debito, "cantidad")
    poner("502", facturas["monto"], nombre_debito)
    poner("509", notas_v["documentos"], nombre_debito, "cantidad")
    poner("510", notas_v["monto"], nombre_debito)
    total_debitos = facturas["monto"] - notas_v["monto"]
    poner("538", total_debitos, "código 502 − código 510", "total")

    # --- Créditos: lo que se compró ------------------------------------
    credito = grupos_de("iva_credito")
    recibidas = credito.get("documento", vacio)
    notas_c = credito.get("nota_credito", vacio)
    importacion = credito.get("importacion", vacio)
    nombre_credito = _nombres(por_concepto.get("iva_credito"))
    poner("519", recibidas["documentos"], nombre_credito, "cantidad")
    poner("520", recibidas["monto"], nombre_credito)
    poner("527", notas_c["documentos"], nombre_credito, "cantidad")
    poner("528", notas_c["monto"], nombre_credito)
    poner("534", importacion["documentos"], nombre_credito, "cantidad")
    poner("535", importacion["monto"], nombre_credito)
    total_creditos = recibidas["monto"] - notas_c["monto"] + importacion["monto"]
    poner("537", total_creditos, "código 520 − código 528 + código 535", "total")

    # El traspaso del mes lleva el saldo de la cuenta a IVA por pagar, así que
    # tiene que ser el mismo total de créditos. Si no calza, falta un
    # documento o sobra uno.
    traspaso = credito.get("sin_documento")
    if traspaso and traspaso["monto"] and abs(abs(traspaso["monto"]) - total_creditos) > 1:
        avisos.append(
            f"El traspaso del mes en {nombre_credito} es {abs(traspaso['monto']):,.0f} y el total "
            f"de créditos propuesto es {total_creditos:,.0f}: hay que revisar por qué no calzan."
            .replace(",", ".")
        )

    # --- Lo determinado ------------------------------------------------
    determinado = total_debitos - total_creditos
    poner("089", max(determinado, 0), "código 538 − código 537", "total")
    # Sin la cuenta de IVA débito cargada, los débitos son 0 y el mes "queda
    # con remanente" por falta de datos, no por lo que pasó. Eso ya lo dice
    # que falte la cuenta.
    if determinado < 0 and "iva_debito" in por_concepto:
        avisos.append(
            f"Los créditos superan a los débitos en {-determinado:,.0f}: el mes queda con "
            "remanente y no con impuesto a pagar.".replace(",", ".")
        )

    unico = sum(_lado_declarado(c) for c in por_concepto.get("impuesto_unico", ()))
    honorarios = sum(_lado_declarado(c) for c in por_concepto.get("honorarios", ()))
    ppm = sum(_lado_declarado(c) for c in por_concepto.get("ppm", ()))
    poner("048", unico, _nombres(por_concepto.get("impuesto_unico")))
    poner("151", honorarios, _nombres(por_concepto.get("honorarios")))
    poner("062", ppm, _nombres(por_concepto.get("ppm")))

    subtotal = max(determinado, 0) + ppm + unico + honorarios
    poner("595", subtotal, "código 089 + código 062 + código 048 + código 151", "total")
    poner("547", subtotal, "código 595", "total")
    poner("091", subtotal, "código 547", "total")

    # --- Lo que todavía no se puede poner solo -------------------------
    sin_codigo = []
    for cuenta in por_concepto.get("iva_retenido", ()):
        retenido = _lado_declarado(cuenta)
        if retenido:
            sin_codigo.append({"nombre": cuenta["nombre"], "valor": retenido})

    faltan = [
        CONCEPTOS[c] for c in CONCEPTOS
        if c not in por_concepto and c in CONCEPTOS_IVA
    ]
    sin_clasificar = [
        {"cuenta": c["cuenta"], "nombre": c["nombre"]} for c in por_concepto.get("", ())
    ]
    return {
        "lineas": lineas,
        "faltan": faltan,
        "sin_codigo": sin_codigo,
        "sin_clasificar": sin_clasificar,
        "avisos": avisos,
        "a_pagar": subtotal,
    }


def _nombres(cuentas) -> str:
    return ", ".join(c["nombre"] for c in cuentas or ()) or "—"
