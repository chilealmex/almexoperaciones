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

from app.utils.f29_pdf import CODIGOS_INFORMATIVOS

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
    "honorarios": "Retención sobre honorarios (segunda categoría)",
    "ppm": "Pagos provisionales mensuales",
    "impuesto_por_pagar": "Impuesto por pagar (el traspaso del mes)",
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
    # La retención a las boletas de honorarios es el impuesto de segunda
    # categoría, y así se llama la cuenta: "IMPUESTO 2 CATEGORIA".
    if "HONORARIO" in n or "2CATEGORIA" in n or "SEGUNDACATEGORIA" in n:
        return "honorarios"
    if "IMPUESTOUNICO" in n or ("UNICO" in n and "TRABAJADOR" in n):
        return "impuesto_unico"
    # Donde se centraliza lo que hay que pagar. No es una línea del
    # formulario: es contra qué comprobar que la propuesta esté completa.
    if "IMPUESTOPORPAGAR" in n:
        return "impuesto_por_pagar"
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


def es_de_documento(tipo, documentos=0) -> bool:
    """Si el asiento es de un documento o del cierre del mes.

    Defontana nombra los asientos de documento con el libro adelante —
    "Cpra_FCA", "Vta_FVAELECT"— y los demás con una sola palabra: "TRASPASO",
    "EGRESO", "APERTURA". Esos no son nada que el formulario declare, y
    sumarlos al crédito del mes lo dejaría al doble.

    Que la línea nombre un documento vale igual: si otro plan de cuentas
    bautizara los tipos de otra forma, lo que nombra una factura es una
    factura.
    """
    return "_" in str(tipo or "") or bool(documentos)


def _grupos(cuenta) -> dict:
    """Lo que movió la cuenta en el mes, juntado por clase de documento."""
    grupos = {}
    for movimiento in cuenta.get("movimientos", ()):
        documentos = movimiento.get("documentos") or 0
        tipo = movimiento.get("tipo")
        familia = familia_de_tipo(tipo) if es_de_documento(tipo, documentos) else "sin_documento"
        grupo = grupos.setdefault(
            familia, {"monto": 0, "documentos": 0, "lineas": 0, "tipos": [], "detalle": []}
        )
        neto = (movimiento.get("debe") or 0) - (movimiento.get("haber") or 0)
        monto = neto * (cuenta.get("signo") or 1)
        # El formulario pide cuántas facturas son. Cuando el asiento las
        # nombra se cuentan documentos distintos; cuando no, cada línea es una.
        cuantos = documentos or (movimiento.get("lineas") or 0)
        grupo["monto"] += monto
        grupo["documentos"] += cuantos
        grupo["lineas"] += movimiento.get("lineas") or 0
        grupo["tipos"].append(tipo)
        # De qué está hecho, por si el código no calza con lo declarado: ahí
        # hay que poder mirar qué asientos lo formaron.
        grupo["detalle"].append({
            "cuenta": cuenta.get("nombre", ""), "tipo": tipo, "monto": monto,
            "documentos": cuantos, "lineas": movimiento.get("lineas") or 0,
        })
    # Una nota de crédito mueve la cuenta al revés que una factura, y el
    # formulario la pide en positivo para restarla después.
    if "nota_credito" in grupos:
        grupos["nota_credito"]["monto"] = -grupos["nota_credito"]["monto"]
        for linea in grupos["nota_credito"]["detalle"]:
            linea["monto"] = -linea["monto"]
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


def _traspaso(cuenta) -> int:
    """Cuánto se traspasó al cerrar el mes, sin signo.

    Al cierre, el saldo de cada cuenta de impuestos se lleva a la de impuesto
    por pagar con un asiento de tipo "TRASPASO". Ese monto es la contabilidad
    diciendo cuánto declaró, y sirve para comprobar la propuesta.
    """
    total = 0
    for movimiento in cuenta.get("movimientos", ()):
        if str(movimiento.get("tipo") or "").strip().upper() != "TRASPASO":
            continue
        total += (movimiento.get("debe") or 0) - (movimiento.get("haber") or 0)
    return abs(total)


def propuesta_f29(cuentas) -> dict:
    """La propuesta del F29 con las cuentas del mayor de un mes.

    Devuelve las líneas del formulario con su código, de dónde salió cada una
    y qué falta para que esté completa. No inventa códigos: lo que no se pudo
    sacar del F29 de referencia queda dicho como tal.
    """
    por_concepto = {}
    for cuenta in cuentas:
        por_concepto.setdefault(cuenta.get("concepto") or "", []).append(cuenta)

    lineas, avisos, controles = [], [], []

    def poner(codigo, valor, de, clase="monto", detalle=()):
        lineas.append({"codigo": codigo, "glosa": GLOSAS[codigo], "valor": valor,
                       "de": de, "clase": clase, "detalle": list(detalle)})

    def grupos_de(concepto):
        juntos = {}
        for cuenta in por_concepto.get(concepto, ()):
            for familia, grupo in _grupos(cuenta).items():
                destino = juntos.setdefault(
                    familia,
                    {"monto": 0, "documentos": 0, "lineas": 0, "tipos": [], "detalle": []},
                )
                destino["monto"] += grupo["monto"]
                destino["documentos"] += grupo["documentos"]
                destino["lineas"] += grupo["lineas"]
                destino["tipos"] += grupo["tipos"]
                destino["detalle"] += grupo["detalle"]
        return juntos

    vacio = {"monto": 0, "documentos": 0, "lineas": 0, "tipos": [], "detalle": []}

    # --- Débitos: lo que se vendió -------------------------------------
    debito = grupos_de("iva_debito")
    facturas = debito.get("documento", vacio)
    notas_v = debito.get("nota_credito", vacio)
    nombre_debito = _nombres(por_concepto.get("iva_debito"))
    poner("503", facturas["documentos"], nombre_debito, "cantidad", facturas["detalle"])
    poner("502", facturas["monto"], nombre_debito, detalle=facturas["detalle"])
    poner("509", notas_v["documentos"], nombre_debito, "cantidad", notas_v["detalle"])
    poner("510", notas_v["monto"], nombre_debito, detalle=notas_v["detalle"])
    total_debitos = facturas["monto"] - notas_v["monto"]
    poner("538", total_debitos, "código 502 − código 510", "total")
    for cuenta in por_concepto.get("iva_debito", ()):
        _comprobar_traspaso(cuenta, total_debitos, "el total de débitos", avisos, controles)

    # --- Créditos: lo que se compró ------------------------------------
    credito = grupos_de("iva_credito")
    recibidas = credito.get("documento", vacio)
    notas_c = credito.get("nota_credito", vacio)
    importacion = credito.get("importacion", vacio)
    nombre_credito = _nombres(por_concepto.get("iva_credito"))
    poner("519", recibidas["documentos"], nombre_credito, "cantidad", recibidas["detalle"])
    poner("520", recibidas["monto"], nombre_credito, detalle=recibidas["detalle"])
    poner("527", notas_c["documentos"], nombre_credito, "cantidad", notas_c["detalle"])
    poner("528", notas_c["monto"], nombre_credito, detalle=notas_c["detalle"])
    poner("534", importacion["documentos"], nombre_credito, "cantidad", importacion["detalle"])
    poner("535", importacion["monto"], nombre_credito, detalle=importacion["detalle"])
    total_creditos = recibidas["monto"] - notas_c["monto"] + importacion["monto"]
    poner("537", total_creditos, "código 520 − código 528 + código 535", "total")

    # El traspaso del mes lleva el saldo de la cuenta a impuesto por pagar, así
    # que tiene que ser el mismo total de créditos. Si no calza, falta un
    # documento o sobra uno.
    for cuenta in por_concepto.get("iva_credito", ()):
        _comprobar_traspaso(cuenta, total_creditos, "el total de créditos", avisos, controles)

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
    poner("048", unico, _nombres(por_concepto.get("impuesto_unico")),
          detalle=_detalle_de(por_concepto.get("impuesto_unico")))
    poner("151", honorarios, _nombres(por_concepto.get("honorarios")),
          detalle=_detalle_de(por_concepto.get("honorarios")))
    poner("062", ppm, _nombres(por_concepto.get("ppm")),
          detalle=_detalle_de(por_concepto.get("ppm")))

    subtotal = max(determinado, 0) + ppm + unico + honorarios
    poner("595", subtotal, "código 089 + código 062 + código 048 + código 151", "total")
    poner("547", subtotal, "código 595", "total")
    poner("091", subtotal, "código 547", "total")

    # Al cerrar el mes, lo que hay que pagar se centraliza en su cuenta. Ese
    # traspaso es la contabilidad diciendo cuánto declaró, así que comprobarlo
    # contra la propuesta dice si está completa.
    for cuenta in por_concepto.get("impuesto_por_pagar", ()):
        _comprobar_traspaso(cuenta, subtotal, "el total a pagar propuesto", avisos, controles)

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
        "controles": controles,
        "faltan": faltan,
        "sin_codigo": sin_codigo,
        "sin_clasificar": sin_clasificar,
        "avisos": avisos,
        "a_pagar": subtotal,
    }


def _detalle_de(cuentas) -> list:
    """De qué está hecho lo que aporta una cuenta de retención o de PPM.

    Acá no hay familias de documento: lo que se declara es un lado de la
    cuenta, así que el detalle son sus asientos del mes.
    """
    detalle = []
    for cuenta in cuentas or ():
        for movimiento in cuenta.get("movimientos", ()):
            lado = "haber" if (cuenta.get("signo") or 1) < 0 else "debe"
            if not movimiento.get(lado):
                continue
            detalle.append({
                "cuenta": cuenta.get("nombre", ""), "tipo": movimiento.get("tipo"),
                "monto": movimiento.get(lado), "documentos": movimiento.get("documentos") or 0,
                "lineas": movimiento.get("lineas") or 0,
            })
    return detalle


def _comprobar_traspaso(cuenta, propuesto, que_es, avisos, controles):
    """Compara el traspaso del cierre con lo que propone el formulario.

    El traspaso no es una línea del F29: es el asiento con que la contabilidad
    cierra el mes. Que calce con lo propuesto quiere decir que no falta ni
    sobra nada; que no calce, que hay algo que mirar. Si el mes todavía no se
    cerró no hay traspaso y no se dice nada.
    """
    traspasado = _traspaso(cuenta)
    if not traspasado:
        return
    # El IVA se redondea documento por documento: un peso de diferencia es eso
    # y no un documento que falte.
    if abs(traspasado - propuesto) <= 1:
        controles.append({
            "cuenta": cuenta["nombre"], "traspasado": traspasado,
            "propuesto": propuesto, "que_es": que_es, "calza": True,
        })
        return
    controles.append({
        "cuenta": cuenta["nombre"], "traspasado": traspasado,
        "propuesto": propuesto, "que_es": que_es, "calza": False,
    })
    avisos.append(
        f"El traspaso del mes en {cuenta['nombre']} es {traspasado:,.0f} y {que_es} da "
        f"{propuesto:,.0f}: hay que revisar por qué no calzan.".replace(",", ".")
    )


def _nombres(cuentas) -> str:
    return ", ".join(c["nombre"] for c in cuentas or ()) or "—"


# --- Lo declarado contra lo que dice la contabilidad ---------------------

ESTADOS_COMPARACION = {
    "calza": "Calza",
    "distinto": "Distinto",
    "no_declarado": "No está en el formulario",
    "sin_propuesta": "Declarado, sin comparar",
}


def comparar_con_declarado(lineas, declarado) -> dict:
    """Pone lado a lado cada código propuesto y lo que dice el F29 presentado.

    Se perdona un peso: el IVA se redondea documento por documento y la suma
    de las facturas puede quedar a un peso de lo que informa el SII.

    'declarado' es {código: valor}; lo que trae y la propuesta no calcula
    —la base imponible, el IVA de documentos electrónicos— queda aparte, dicho
    pero sin comparar.
    """
    filas, iguales, distintos = [], 0, 0
    for linea in lineas:
        codigo = linea["codigo"]
        propuesto = linea["valor"]
        if codigo not in declarado:
            filas.append({"codigo": codigo, "glosa": linea["glosa"], "propuesto": propuesto,
                          "declarado": None, "diferencia": None, "estado": "no_declarado"})
            continue
        valor = declarado[codigo]
        diferencia = propuesto - valor
        estado = "calza" if abs(diferencia) <= 1 else "distinto"
        if estado == "calza":
            iguales += 1
        else:
            distintos += 1
        filas.append({"codigo": codigo, "glosa": linea["glosa"], "propuesto": propuesto,
                      "declarado": valor, "diferencia": diferencia, "estado": estado})

    propuestos = {linea["codigo"] for linea in lineas}
    aparte = [
        {"codigo": codigo, "glosa": GLOSAS.get(codigo) or CODIGOS_INFORMATIVOS.get(codigo, ""),
         "declarado": valor, "estado": "sin_propuesta"}
        for codigo, valor in sorted(declarado.items()) if codigo not in propuestos
    ]
    return {"filas": filas, "sin_comparar": aparte, "calzan": iguales, "distintos": distintos}
