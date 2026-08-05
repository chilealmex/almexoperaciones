"""Cálculo de la diferencia de tipo de cambio, celda por celda como la planilla.

Las tres columnas calculadas de "control.xlsx" (hoja clientes) son:

    Valor en $        X = W * $AB$2          (monto en moneda origen por el T/C)
    Dif de cambio     Y = IF(AND(J>0,X>0), J-X, IF(AND(J<0,X<0), J-X, J+X))
    % Dif Variación   Z = Y / J

La fórmula de la diferencia se ve rara, pero lo que hace es: si el saldo
contable y el valor convertido apuntan al mismo lado, se restan; si apuntan a
lados distintos, se suman. Se reproduce tal cual para que los números coincidan
con los de la planilla.
"""


def _num(valor):
    try:
        return float(valor) if valor is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _entero(valor):
    return int(round(valor))


def valor_en_pesos(mon_orig, tipo_cambio) -> float:
    return _num(mon_orig) * _num(tipo_cambio)


def diferencia_de_cambio(saldo, valor_clp) -> float:
    """Fórmula Y de la planilla: mismo signo se resta, signo distinto se suma."""
    saldo = _num(saldo)
    valor = _num(valor_clp)
    if (saldo > 0 and valor > 0) or (saldo < 0 and valor < 0):
        return saldo - valor
    return saldo + valor


def porcentaje_variacion(dif_cambio, saldo) -> float:
    saldo = _num(saldo)
    if not saldo:
        return 0.0
    return _num(dif_cambio) / saldo


def recalcular_linea(linea, tipo_cambio) -> None:
    """Deja al día las tres columnas calculadas de una línea."""
    valor = valor_en_pesos(linea.mon_orig, tipo_cambio)
    dif = diferencia_de_cambio(linea.saldo, valor)
    linea.valor_clp = _entero(valor)
    linea.dif_cambio = _entero(dif)
    linea.pct_variacion = porcentaje_variacion(dif, linea.saldo)


def recalcular_periodo(periodo) -> None:
    """Recalcula todas las líneas con el tipo de cambio vigente del período."""
    for linea in periodo.lineas:
        recalcular_linea(linea, periodo.tipo_cambio)


def totales_periodo(periodo) -> dict:
    lineas = periodo.lineas
    return {
        "saldo": sum(l.saldo or 0 for l in lineas),
        "valor_clp": sum(l.valor_clp or 0 for l in lineas),
        "dif_cambio": sum(l.dif_cambio or 0 for l in lineas),
        "mon_orig": sum(_num(l.mon_orig) for l in lineas),
        "lineas": len(lineas),
        "sin_mon_orig": sum(1 for l in lineas if l.mon_orig is None),
    }
