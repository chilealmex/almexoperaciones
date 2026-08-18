"""Cantidades de inventario con decimales.

No todo el stock se cuenta de a uno: hay artículos que se miden en metros,
kilos o litros, y ahí "12,5" es un dato legítimo, no un error de tipeo.
Por eso las cantidades se guardan con hasta tres decimales.

Se usa Decimal y no float a propósito: la pantalla de conteo vive de restar
cantidades (físico menos QMS, físico menos Defontana) y con float esas restas
sacan colas —12,3 - 10 daría 2,3000000000000007—, justo en la columna donde la
diferencia es lo único que importa.
"""

from decimal import Context, Decimal, InvalidOperation

# Tres decimales: alcanza para gramos dentro de un kilo y para milímetros
# dentro de un metro, que es el nivel al que se cuenta en bodega.
DECIMALES = 3
# 22 dígitos en total, o sea 19 enteros: los mismos que aguantaba el BigInteger
# que había antes. Achicar ese rango al agregar decimales habría reintroducido
# el error 500 que ya costó una importación completa: una celda con una cifra
# disparatada tiene que seguir entrando, no tumbar el archivo entero.
PRECISION = 22
_PASO = Decimal(1).scaleb(-DECIMALES)  # 0.001
_CONTEXTO = Context(prec=PRECISION)


def cuantizar(numero: Decimal, por_defecto=None):
    """Deja el número con exactamente los decimales que admite la columna.

    Si ni así cabe —una celda con una cifra sin sentido, de más dígitos que los
    que acepta la columna— devuelve 'por_defecto' en vez de dejar que reviente
    al guardar: una sola celda mala no puede volver a tumbar la importación
    completa.
    """
    try:
        return numero.quantize(_PASO, context=_CONTEXTO)
    except (InvalidOperation, ValueError, OverflowError):
        return por_defecto


def _separador_decimal(texto: str) -> int:
    """Posición del separador decimal en el texto, o -1 si son todos de miles.

    Acá está la única ambigüedad real: en Chile el punto separa los miles y la
    coma los decimales, así que '1.234' son mil doscientos treinta y cuatro,
    no uno coma doscientos treinta y cuatro. Pero las planillas exportadas en
    inglés escriben '12.5', y eso sí son doce y medio. Las reglas:

    - una coma con 1 a 3 dígitos detrás siempre es decimal;
    - un punto con 1 o 2 dígitos detrás es decimal ('12.5', '12.75');
    - un punto con 3 dígitos detrás es separador de miles ('1.234'), salvo que
      lo que va delante sea sólo un 0: '0.125' no es una cifra de miles.
    """
    posicion = max(texto.rfind(","), texto.rfind("."))
    if posicion == -1:
        return -1
    digitos = len(texto) - posicion - 1
    if not 1 <= digitos <= DECIMALES:
        return -1
    if texto[posicion] == ",":
        return posicion
    if digitos < DECIMALES:
        return posicion
    entero = texto[:posicion].replace(".", "").replace(",", "")
    return posicion if entero in ("", "0") else -1


def a_cantidad(valor, por_defecto=None):
    """Convierte a Decimal lo que venga de una planilla, un formulario o un JSON.

    Acepta números nativos (Excel vía openpyxl), y texto en los formatos que
    escriben las planillas: '12,5' (coma decimal), '1.234' (punto de miles),
    '1.234,5' y '1,234.5'. Devuelve 'por_defecto' si no hay número.
    """
    if valor is None or valor == "":
        return por_defecto
    if isinstance(valor, bool):
        return por_defecto
    if isinstance(valor, Decimal):
        return cuantizar(valor, por_defecto)
    if isinstance(valor, int):
        return cuantizar(Decimal(valor), por_defecto)
    if isinstance(valor, float):
        # str() y no Decimal(float): Decimal(12.5) arrastra el ruido binario.
        return cuantizar(Decimal(str(valor)), por_defecto)

    limpio = str(valor).strip().replace(" ", "").replace("\xa0", "")
    if not limpio:
        return por_defecto

    negativo = limpio.startswith("-") or (limpio.startswith("(") and limpio.endswith(")"))
    limpio = limpio.strip("-()")

    ultimo = _separador_decimal(limpio)
    if ultimo != -1:
        entero = limpio[:ultimo].replace(".", "").replace(",", "")
        decimales = limpio[ultimo + 1 :]
        texto = f"{entero or '0'}.{decimales}"
    else:
        texto = limpio.replace(".", "").replace(",", "")

    try:
        numero = Decimal(texto)
    except InvalidOperation:
        return por_defecto
    return cuantizar(-numero if negativo else numero, por_defecto)


def format_cantidad(valor) -> str:
    """Cantidad como se lee en Chile: '1.234', '12,5', '0,25'.

    Los decimales se muestran sólo si existen: un stock de 1.234 unidades no
    tiene por qué aparecer como '1.234,000' y llenar de ruido la tabla.

    Este formato es también el que se escribe en el campo de conteo, y por eso
    tiene que poder volver a leerse con a_cantidad() dando exactamente el mismo
    número. Si el campo mostrara '3.125' para tres coma ciento veinticinco,
    guardar sin tocar nada lo convertiría en tres mil ciento veinticinco: el
    conteo se corrompería solo al recargar la página.
    """
    if valor is None or valor == "":
        return ""
    numero = a_cantidad(valor)
    if numero is None:
        return str(valor)

    signo = "-" if numero < 0 else ""
    entero, _, decimales = format(abs(numero), "f").partition(".")
    entero = "{:,}".format(int(entero)).replace(",", ".")
    decimales = decimales.rstrip("0")
    return f"{signo}{entero},{decimales}" if decimales else f"{signo}{entero}"


def format_cantidad_signo(valor) -> str:
    """Como format_cantidad, pero siempre con el signo delante: '+12,5', '-3', '0'.

    Es el formato de las columnas de diferencia, donde interesa de inmediato
    hacia qué lado está el descuadre.
    """
    numero = a_cantidad(valor)
    if numero is None:
        return format_cantidad(valor)
    texto = format_cantidad(numero)
    return f"+{texto}" if numero > 0 else texto


def a_entero_clp(valor) -> int:
    """Redondea a pesos un monto que quedó con decimales por venir de una cantidad.

    Las columnas de plata se guardan en pesos enteros; al multiplicar por una
    cantidad decimal el resultado deja centavos que ahí no caben.
    """
    if valor is None:
        return 0
    return int(Decimal(valor).to_integral_value(rounding="ROUND_HALF_UP"))
