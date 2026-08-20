"""Cruce entre el Registro de Compras y Ventas del SII y los libros de Defontana.

Cada mes hay que comprobar que lo que el SII tiene registrado a nombre de la
empresa sea exactamente lo que está contabilizado en Defontana. Lo que se busca
son tres cosas: documentos que el SII conoce y Defontana no (falta
contabilizarlos), documentos que Defontana tiene y el SII no (se contabilizó
algo que no llegó al SII), y documentos que están en los dos pero por montos
distintos.

Los dos sistemas exportan en formatos distintos:

- el SII entrega un .csv separado por punto y coma;
- Defontana entrega un ".xls" que en realidad es una página HTML con tablas.

Este módulo lee los dos, los normaliza a la misma forma y los cruza por
tipo de documento + folio, que es la única llave que ambos comparten.

No todo descuadre es un error. Las facturas de combustible llevan impuesto
específico y los dos sistemas no lo reparten igual entre neto e impuestos, así
que nunca van a calzar. Esos casos se revisan y se dan por buenos desde la
pantalla (ver el campo 'aceptado' de ConciliacionSiiDocumento); acá sólo se
detecta la diferencia, la decisión de aceptarla es de quien concilia.
"""

import csv
import io
import re
import unicodedata
from html.parser import HTMLParser

# Nombres que el SII le da a cada tipo de documento. Se usan sólo para mostrar:
# un código suelto ("61") no le dice nada a quien revisa la conciliación.
TIPOS_DOCUMENTO = {
    "29": "Factura de Inicio",
    "30": "Factura",
    "32": "Factura de Venta Bien Raíz",
    "33": "Factura Electrónica",
    "34": "Factura No Afecta o Exenta Electrónica",
    "35": "Boleta",
    "38": "Boleta Exenta",
    "39": "Boleta Electrónica",
    "41": "Boleta Exenta Electrónica",
    "43": "Liquidación Factura Electrónica",
    "45": "Factura de Compra",
    "46": "Factura de Compra Electrónica",
    "56": "Nota de Débito",
    "60": "Nota de Débito",
    "61": "Nota de Crédito Electrónica",
    "110": "Factura de Exportación Electrónica",
    "111": "Nota de Crédito de Exportación",
    "112": "Nota de Débito de Exportación",
    "914": "Declaración de Importación (DIN)",
}

# Notas de crédito: el SII las informa en positivo, pero contablemente restan.
# Se les da vuelta el signo antes de comparar, porque Defontana ya las tiene
# con el signo que corresponde.
TIPOS_NOTA_CREDITO = frozenset({"60", "61", "111"})

# Notas de débito en el libro de ventas de Defontana: a veces salen en negativo
# aunque suman. Se toma el valor absoluto para poder compararlas con el SII.
TIPOS_NOTA_DEBITO = frozenset({"56", "112"})

# Los montos se guardan en pesos enteros. Una diferencia de hasta un peso es
# redondeo de alguno de los dos sistemas, no un descuadre real.
TOLERANCIA_PESOS = 1

ESTADOS = ("solo_sii", "solo_defontana", "dif_monto", "dif_datos", "coincide")
ESTADO_ETIQUETAS = {
    "coincide": "Coincide",
    "solo_sii": "Solo en SII",
    "solo_defontana": "Solo en Defontana",
    "dif_monto": "Diferencia de monto",
    "dif_datos": "Diferencia de datos",
}
# Orden en que se muestran: primero lo que exige trabajo, al final lo que ya cuadra.
ORDEN_ESTADOS = {"solo_sii": 0, "solo_defontana": 1, "dif_monto": 2, "dif_datos": 3, "coincide": 4}

LIBROS = ("compra", "venta")


class ArchivoInvalido(ValueError):
    """El archivo no tiene la forma esperada; el mensaje explica qué falta."""


def a_monto(valor) -> int:
    """Convierte a pesos enteros un importe tal como lo escriben estas planillas.

    Acepta el paréntesis contable para los negativos —"(1.234)" son -1.234— y
    los distintos separadores de miles y decimales que usa cada exportador:
    '1.234.567', '1,234,567' y '1234567,89'. El último separador manda cuando
    deja 1 o 2 dígitos a su derecha; en cualquier otro caso es de miles.
    """
    if valor is None or valor == "":
        return 0
    if isinstance(valor, bool):
        return 0
    if isinstance(valor, (int, float)):
        return int(round(valor))

    limpio = str(valor).strip().replace("$", "").replace(" ", "").replace("\xa0", "")
    if not limpio:
        return 0
    negativo = limpio.startswith("-") or (limpio.startswith("(") and limpio.endswith(")"))
    limpio = limpio.strip("-()")
    if not limpio:
        return 0

    ultimo = max(limpio.rfind(","), limpio.rfind("."))
    if ultimo != -1 and len(limpio) - ultimo - 1 in (1, 2):
        entero = limpio[:ultimo].replace(".", "").replace(",", "")
        texto = f"{entero or '0'}.{limpio[ultimo + 1:]}"
    else:
        texto = limpio.replace(".", "").replace(",", "")

    try:
        numero = float(texto)
    except ValueError:
        return 0
    numero = int(round(numero))
    return -numero if negativo else numero


def normalizar_rut(valor) -> str:
    """RUT sin puntos y en mayúsculas, que es como se puede comparar entre sistemas."""
    return str(valor or "").strip().upper().replace(".", "")


def normalizar_nombre(valor) -> str:
    """Razón social comparable entre los dos sistemas.

    El SII y Defontana escriben el mismo nombre de formas distintas: "COMERCIAL
    ALFA S.P.A." y "Comercial Alfa SPA" son la misma empresa. Se descarta todo
    lo que no sea letra o número —acentos, puntos, espacios— porque ahí está
    justamente la diferencia de estilo entre un sistema y otro. Los puntos no
    se cambian por espacios: eso convertiría "S.P.A." en "S P A", que no calza
    con "SPA" y haría saltar una diferencia donde no la hay.

    Si después de eso los nombres siguen sin coincidir, son de verdad dos
    empresas distintas y vale la pena avisarlo.
    """
    texto = str(valor or "").strip().upper()
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return "".join(c for c in sin_acentos if c.isalnum())


def normalizar_folio(valor) -> str:
    """Folio sin ceros de relleno ni espacios: '00123' y '123' son el mismo documento."""
    texto = str(valor or "").strip()
    if not texto:
        return ""
    # Se quitan los ceros a la izquierda sólo si lo que queda sigue siendo un
    # número; hay folios con letras donde el cero inicial sí es parte del dato.
    sin_ceros = texto.lstrip("0")
    return sin_ceros if sin_ceros.isdigit() else texto


def _texto(valor, limite: int) -> str:
    return str(valor or "").strip()[:limite]


def _decodificar(datos: bytes, codificaciones) -> str:
    for codificacion in codificaciones:
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
    # Último recurso: no perder el archivo entero por un carácter suelto.
    return datos.decode(codificaciones[-1], errors="replace")


def _leer_bytes(archivo) -> bytes:
    datos = archivo.read() if hasattr(archivo, "read") else archivo
    if hasattr(archivo, "seek"):
        try:
            archivo.seek(0)
        except (OSError, ValueError):
            pass
    return datos


# --- Registro de Compras y Ventas del SII (.csv separado por ';') ---------

# El SII usa nombres distintos según el libro. Se buscan por palabras clave y
# no por igualdad exacta porque el encabezado cambia de un año a otro.
_COLUMNAS_SII = {
    "compra": {
        "rut": ("rut", "proveedor"),
        "iva": ("iva", "recuperable"),
    },
    "venta": {
        "rut": ("rut", "cliente"),
        "iva": ("iva",),
    },
}


def _buscar_columna(campos, *palabras):
    """Primera columna cuyo nombre contiene todas las palabras dadas."""
    for campo in campos or ():
        nombre = (campo or "").strip().lower()
        if all(palabra in nombre for palabra in palabras):
            return campo
    return None


def leer_rcv_sii(archivo, libro: str) -> list:
    """Lee el RCV del SII y devuelve una lista de documentos normalizados.

    'libro' es 'compra' o 'venta': cambia el nombre de las columnas de RUT y de
    IVA, que el SII escribe distinto en cada uno.
    """
    if libro not in LIBROS:
        raise ValueError(f"Libro desconocido: {libro}")

    texto = _decodificar(_leer_bytes(archivo), ("utf-8-sig", "cp1252", "latin-1"))
    lector = csv.DictReader(io.StringIO(texto), delimiter=";")
    campos = lector.fieldnames or []

    col_tipo = _buscar_columna(campos, "tipo", "doc")
    col_folio = _buscar_columna(campos, "folio")
    if not col_tipo or not col_folio:
        raise ArchivoInvalido(
            "El archivo del SII no tiene las columnas 'Tipo Doc' y 'Folio'. "
            "Descárgalo desde el SII como RCV en formato CSV, sin abrirlo ni guardarlo en Excel."
        )

    claves = _COLUMNAS_SII[libro]
    col_rut = _buscar_columna(campos, *claves["rut"]) or _buscar_columna(campos, "rut")
    col_razon = _buscar_columna(campos, "razon", "social")
    col_fecha = _buscar_columna(campos, "fecha", "docto") or _buscar_columna(campos, "fecha")
    col_neto = _buscar_columna(campos, "monto", "neto")
    col_exento = _buscar_columna(campos, "monto", "exento")
    col_iva = _buscar_columna(campos, *claves["iva"]) or _buscar_columna(campos, "iva")
    col_total = _buscar_columna(campos, "monto", "total")

    documentos = []
    for fila in lector:
        def dato(columna):
            return (fila.get(columna) or "").strip() if columna else ""

        tipo = dato(col_tipo)
        if not tipo:
            continue
        documentos.append({
            "tipo_doc": tipo,
            "folio": normalizar_folio(dato(col_folio)),
            "rut": normalizar_rut(dato(col_rut)),
            "contraparte": _texto(dato(col_razon), 200),
            "fecha": _texto(dato(col_fecha), 20),
            "neto": a_monto(dato(col_neto)),
            "exento": a_monto(dato(col_exento)),
            "iva": a_monto(dato(col_iva)),
            "total": a_monto(dato(col_total)),
        })
    return documentos


# --- Libro de Compras / Ventas de Defontana (".xls" que es HTML) ----------

class _TablasHtml(HTMLParser):
    """Extrae las tablas de un HTML como listas de filas de texto.

    Defontana exporta el libro con extensión .xls, pero el contenido es una
    página HTML con tablas. No se usa un parser de Excel: openpyxl y xlrd
    rechazan el archivo porque no es un Excel de verdad.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tablas = []
        self._tabla = None
        self._fila = None
        self._celda = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._tabla = []
        elif tag == "tr" and self._tabla is not None:
            self._fila = []
        elif tag in ("td", "th") and self._fila is not None:
            self._celda = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._celda is not None:
            self._fila.append("".join(self._celda).strip())
            self._celda = None
        elif tag == "tr" and self._fila is not None:
            self._tabla.append(self._fila)
            self._fila = None
        elif tag == "table" and self._tabla is not None:
            self.tablas.append(self._tabla)
            self._tabla = None

    def handle_data(self, data):
        if self._celda is not None:
            self._celda.append(data)


_RE_DOCUMENTO = re.compile(r"^Documento:\s*(\d+)")


def leer_libro_defontana(archivo) -> list:
    """Lee el libro de compras o ventas de Defontana.

    El libro viene agrupado por tipo de documento: una fila dice
    "Documento: 33" y las siguientes son las facturas de ese tipo, hasta que
    aparece otro encabezado. Por eso hay que recorrerlo en orden y arrastrar
    cuál es el tipo vigente, en vez de leer cada fila por separado.
    """
    texto = _decodificar(_leer_bytes(archivo), ("cp1252", "latin-1", "utf-8"))
    parser = _TablasHtml()
    parser.feed(texto)

    # La tabla buena es la que tiene una fila cuyo primer campo es "Folio":
    # el archivo trae además tablas de encabezado con el logo y el período.
    tabla = None
    for candidata in parser.tablas:
        if any(fila and fila[0].strip() == "Folio" for fila in candidata):
            tabla = candidata
            break
    if tabla is None:
        raise ArchivoInvalido(
            "El libro de Defontana no tiene la tabla de documentos esperada. "
            "Descárgalo desde Defontana como Libro de Compras/Ventas, sin convertirlo a otro formato."
        )

    documentos = []
    tipo_actual = None
    for fila in tabla:
        if not fila or not fila[0]:
            continue
        primera = fila[0].strip()

        encabezado = _RE_DOCUMENTO.match(primera)
        if encabezado:
            tipo_actual = encabezado.group(1)
            continue
        if primera == "Folio" or primera.startswith("Total"):
            continue
        if tipo_actual is None:
            continue

        folio = normalizar_folio(primera)
        if not folio:
            continue

        def celda(indice):
            return fila[indice] if indice < len(fila) else ""

        documentos.append({
            "tipo_doc": tipo_actual,
            "folio": folio,
            "rut": normalizar_rut(celda(2)),
            "contraparte": _texto(celda(3), 200),
            "fecha": _texto(celda(1), 20),
            "neto": a_monto(celda(4)),
            "exento": a_monto(celda(5)),
            "iva": a_monto(celda(6)),
            "total": a_monto(celda(7)),
        })
    return documentos


# --- El cruce -------------------------------------------------------------

_CAMPOS_MONTO = ("neto", "exento", "iva", "total")

# Qué se compara para explicar una diferencia, y cómo se llama en pantalla.
_CAMPOS_COMPARADOS = (
    ("neto", "Neto"),
    ("exento", "Exento"),
    ("iva", "IVA"),
    ("total", "Total"),
)


def diferencias_de(fila) -> list:
    """En qué se diferencian los dos sistemas para un documento.

    Saber que un documento "tiene diferencia de monto" no alcanza para
    arreglarlo: hay que ir al asiento y ver qué columna corregir. Esto devuelve
    cuál es —neto, exento, IVA o total— con los dos valores y la resta, y de
    paso avisa si el RUT de la contraparte no es el mismo, que es un error
    distinto y se arregla en otro lado.
    """
    detalles = []
    for campo, etiqueta in _CAMPOS_COMPARADOS:
        valor_sii = fila.get(f"{campo}_sii", 0)
        valor_defo = fila.get(f"{campo}_defontana", 0)
        diferencia = valor_sii - valor_defo
        if abs(diferencia) > TOLERANCIA_PESOS:
            detalles.append({
                "campo": campo,
                "etiqueta": etiqueta,
                "sii": valor_sii,
                "defontana": valor_defo,
                "diferencia": diferencia,
            })

    # Se compara todo lo que describe al documento menos la fecha: los dos
    # sistemas la escriben con formatos distintos y una diferencia ahí casi
    # nunca significa algo, mientras que el RUT o la razón social sí.
    rut_sii, rut_defo = fila.get("rut_sii", ""), fila.get("rut_defontana", "")
    if rut_sii and rut_defo and rut_sii != rut_defo:
        detalles.append({
            "campo": "rut",
            "etiqueta": "RUT",
            "sii": rut_sii,
            "defontana": rut_defo,
            "diferencia": None,
        })

    # La razón social sólo se informa cuando el RUT no alcanza para saber si es
    # la misma empresa. Con el RUT igual, un nombre distinto no es un error:
    # Defontana lo guarda abreviado y recortado ("SOCIEDAD ESTACIONES DE
    # SERVICIO ARAGON LIMITADA" queda como "SOC ESTA DE SERV A RAGON LTDA"), y
    # marcarlo llenaba el informe de avisos falsos que tapaban los reales.
    nombre_sii = fila.get("contraparte_sii", "")
    nombre_defo = fila.get("contraparte_defontana", "")
    ruts_confirman_identidad = bool(rut_sii and rut_defo and rut_sii == rut_defo)
    if (nombre_sii and nombre_defo and not ruts_confirman_identidad
            and normalizar_nombre(nombre_sii) != normalizar_nombre(nombre_defo)):
        detalles.append({
            "campo": "contraparte",
            "etiqueta": "Razón social",
            "sii": nombre_sii,
            "defontana": nombre_defo,
            "diferencia": None,
        })
    return detalles


def _hay_diferencia_de_monto(detalles) -> bool:
    return any(d["campo"] in ("neto", "exento", "iva", "total") for d in detalles)


def describir_diferencia(detalles) -> str:
    """Resumen en una línea: 'Neto: 1.000 vs 900 · IVA: 190 vs 171'."""
    from app.utils.formatting import format_clp

    partes = []
    for detalle in detalles:
        # Los campos de texto (RUT, razón social) vienen sin resta: se muestran
        # tal cual, no como plata.
        if detalle["diferencia"] is None:
            partes.append(
                f"{detalle['etiqueta']} distinto: {detalle['sii']} vs {detalle['defontana']}"
                if detalle["campo"] == "rut"
                else f"{detalle['etiqueta']}: «{detalle['sii']}» vs «{detalle['defontana']}»"
            )
        else:
            partes.append(
                f"{detalle['etiqueta']}: {format_clp(detalle['sii'])} "
                f"vs {format_clp(detalle['defontana'])}"
            )
    return " · ".join(partes)


def _invertir_notas_credito(documentos):
    """Da vuelta el signo de las notas de crédito del SII, que restan."""
    ajustados = []
    for doc in documentos:
        if doc["tipo_doc"] in TIPOS_NOTA_CREDITO:
            doc = dict(doc, **{campo: -doc[campo] for campo in _CAMPOS_MONTO})
        ajustados.append(doc)
    return ajustados


def _absolutizar_notas_debito(documentos):
    """Deja en positivo las notas de débito, que suman aunque vengan con signo."""
    ajustados = []
    for doc in documentos:
        if doc["tipo_doc"] in TIPOS_NOTA_DEBITO:
            doc = dict(doc, **{campo: abs(doc[campo]) for campo in _CAMPOS_MONTO})
        ajustados.append(doc)
    return ajustados


def _por_llave(documentos):
    """Indexa por tipo de documento + folio, que es lo único que ambos comparten.

    Si un mismo tipo y folio aparece repetido, se suman: en los libros pasa con
    documentos que se registran en varias líneas, y sumarlos es lo que permite
    compararlos contra el total que informa el otro sistema.
    """
    indice = {}
    for doc in documentos:
        llave = (doc["tipo_doc"], doc["folio"])
        previo = indice.get(llave)
        if previo is None:
            indice[llave] = dict(doc)
            continue
        for campo in _CAMPOS_MONTO:
            previo[campo] += doc[campo]
    return indice


def cruzar(documentos_sii, documentos_defontana, libro: str = "compra") -> dict:
    """Cruza ambos libros y clasifica cada documento.

    Devuelve {'filas', 'conteos', 'totales'}: las filas ya ordenadas con lo que
    requiere trabajo primero, cuántas hay de cada estado, y las sumas para
    poder cuadrar contra la declaración.
    """
    sii = _por_llave(_invertir_notas_credito(documentos_sii))
    defontana = _por_llave(
        _absolutizar_notas_debito(documentos_defontana) if libro == "venta" else documentos_defontana
    )

    filas = []
    for llave in set(sii) | set(defontana):
        s = sii.get(llave)
        d = defontana.get(llave)
        base = s or d

        total_sii = s["total"] if s else 0
        total_defo = d["total"] if d else 0
        exento_sii = s["exento"] if s else 0
        exento_defo = d["exento"] if d else 0

        if s is None:
            estado = "solo_defontana"
        elif d is None:
            estado = "solo_sii"
        else:
            estado = None  # se decide más abajo, con el detalle ya calculado

        filas.append({
            "tipo_doc": base["tipo_doc"],
            "tipo_doc_desc": TIPOS_DOCUMENTO.get(base["tipo_doc"], f"Doc. {base['tipo_doc']}"),
            "folio": base["folio"],
            "fecha": s["fecha"] if s else d["fecha"],
            "rut_sii": s["rut"] if s else "",
            "rut_defontana": d["rut"] if d else "",
            "contraparte_sii": s["contraparte"] if s else "",
            "contraparte_defontana": d["contraparte"] if d else "",
            "neto_sii": s["neto"] if s else 0,
            "neto_defontana": d["neto"] if d else 0,
            "exento_sii": exento_sii,
            "exento_defontana": exento_defo,
            "iva_sii": s["iva"] if s else 0,
            "iva_defontana": d["iva"] if d else 0,
            "total_sii": total_sii,
            "total_defontana": total_defo,
            # Una diferencia por cada columna, no sólo la del total: así se ve
            # de inmediato si lo que baila es el neto, el exento o el IVA.
            "dif_neto": (s["neto"] if s else 0) - (d["neto"] if d else 0),
            "dif_exento": exento_sii - exento_defo,
            "dif_iva": (s["iva"] if s else 0) - (d["iva"] if d else 0),
            "diferencia": total_sii - total_defo,
            "estado": estado,
        })

    # El detalle se calcula sobre la fila ya armada. Para los documentos que
    # están en los dos sistemas, además decide el estado: si lo que difiere son
    # montos es un descuadre de plata; si son sólo el RUT o la razón social, el
    # dinero cuadra pero hay un dato mal y también hay que avisarlo.
    for fila in filas:
        detalles = diferencias_de(fila)
        fila["detalles_diferencia"] = detalles
        fila["diferencia_descrita"] = describir_diferencia(detalles)
        if fila["estado"] is None:
            if _hay_diferencia_de_monto(detalles):
                fila["estado"] = "dif_monto"
            elif detalles:
                fila["estado"] = "dif_datos"
            else:
                fila["estado"] = "coincide"

    filas.sort(key=lambda f: (
        ORDEN_ESTADOS[f["estado"]],
        f["tipo_doc"].zfill(4),
        f["folio"].zfill(12),
    ))

    conteos = {estado: 0 for estado in ESTADOS}
    for fila in filas:
        conteos[fila["estado"]] += 1

    return {
        "filas": filas,
        "conteos": conteos,
        "totales": totales_de(filas),
    }


# Las columnas de plata de la tabla, en el orden en que se muestran. La misma
# lista arma el pie de totales y las columnas del Excel, para que no se puedan
# desincronizar.
COLUMNAS_MONTO = (
    ("neto_sii", "Neto SII"),
    ("neto_defontana", "Neto Defontana"),
    ("dif_neto", "Dif. neto"),
    ("exento_sii", "Exento SII"),
    ("exento_defontana", "Exento Defontana"),
    ("dif_exento", "Dif. exento"),
    ("iva_sii", "IVA SII"),
    ("iva_defontana", "IVA Defontana"),
    ("dif_iva", "Dif. IVA"),
    ("total_sii", "Total SII"),
    ("total_defontana", "Total Defontana"),
    ("diferencia", "Dif. total"),
)


def totales_de(filas) -> dict:
    """Suma de cada columna de plata, para el pie de la tabla y para cuadrar.

    Se totaliza columna por columna —y no sólo el total general— porque el
    cuadre contra la declaración se hace por línea: el neto contra el neto, el
    IVA contra el IVA.
    """
    totales = {"documentos": len(filas)}
    for campo, _etiqueta in COLUMNAS_MONTO:
        totales[campo] = sum(fila[campo] for fila in filas)
    return totales
