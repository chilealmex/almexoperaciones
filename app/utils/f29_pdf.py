"""El F29 presentado, leído de su PDF.

El SII entrega el formulario como PDF y adentro está lo declarado, código por
código. Leerlo permite poner lado a lado lo que se declaró y lo que dice la
contabilidad, que es de donde sale la propuesta.

El PDF trae las líneas de dos formas:

    503     CANTIDAD FACTURAS EMITIDAS                 29
    TOTAL A PAGAR DENTRO DEL PLAZO LEGAL      91      75.277.038      +

y en el encabezado el período y el folio:

    FOLIO [07] 9383590556
    PERIODO [15] 202609
"""

import re

from app.utils.conciliacion_sii import ArchivoInvalido, a_monto

# Los códigos que se leen. Es una lista cerrada a propósito: el PDF trae
# también filas de títulos con varios números sueltos —"931 Monto Interés 932
# Monto Multa 60 Condonación"— y leerlas a ciegas inventaría declaraciones.
# Las glosas están copiadas del F29 de septiembre de 2026.
CODIGOS_INFORMATIVOS = {
    "511": "CRÉD. IVA POR DCTOS. ELECTRÓNICOS",
    "584": "CANT.INT.EX.NO GRAV.SIN DER. CRED.FISCAL",
    "562": "MONTO SIN DER. A CRED. FISCAL",
    "544": "RECUP. IMP. ESP. DIESEL (Art. 2)",
    "779": "Monto de IVA postergado 6 o 12 cuotas",
    "563": "BASE IMPONIBLE",
    "115": "TASA PPM 1ra. CATEGORÍA",
}

_RE_PERIODO = re.compile(r"PERIODO\s*\[?\s*15\s*\]?\s*(\d{6})")
_RE_FOLIO = re.compile(r"FOLIO\s*\[?\s*07\s*\]?\s*(\d+)")
# "503 CANTIDAD FACTURAS EMITIDAS 29"
_RE_LINEA = re.compile(r"^\s*(\d{2,4})\s+(.+?)\s+(-?[\d.,]+)\s*$")
# "TOTAL A PAGAR DENTRO DEL PLAZO LEGAL 91 75.277.038 +"
_RE_LINEA_TOTAL = re.compile(r"^\s*([^\d]+?)\s+(\d{2,4})\s+(-?[\d.,]+)\s*[+=-]?\s*$")


def _texto_del_pdf(archivo) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover - falta la dependencia
        raise ArchivoInvalido(
            "Falta la librería para leer PDF en el servidor."
        ) from error

    try:
        lector = PdfReader(archivo)
        return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
    except ArchivoInvalido:
        raise
    except Exception as error:  # noqa: BLE001 - pypdf levanta de todo
        raise ArchivoInvalido(
            "No se pudo abrir el archivo como PDF. Sube el F29 tal como lo entrega el SII."
        ) from error


def leer_f29_pdf(archivo, codigos_validos) -> dict:
    """Lo declarado en un F29, leído de su PDF.

    'codigos_validos' son los códigos que se saben leer: los que la propuesta
    calcula más los informativos. Lo que no esté ahí no se lee, para no
    confundir una fila de títulos con una declaración.

    Devuelve {'mes', 'folio', 'codigos': {código: valor}}.
    """
    texto = _texto_del_pdf(archivo)
    if "FORMULARIO 29" not in texto.upper():
        raise ArchivoInvalido(
            "Ese PDF no parece un Formulario 29 del SII: no dice \"Formulario 29\" en "
            "ninguna parte."
        )

    periodo = _RE_PERIODO.search(texto)
    if not periodo:
        raise ArchivoInvalido(
            "No se encontró el período del formulario (el código 15, \"202609\"). "
            "Sube el F29 tal como lo entrega el SII, sin recortarlo."
        )
    crudo = periodo.group(1)
    mes = f"{crudo[:4]}-{crudo[4:]}"

    folio = _RE_FOLIO.search(texto)
    codigos = {}
    for linea in texto.splitlines():
        for patron, orden in ((_RE_LINEA, "codigo"), (_RE_LINEA_TOTAL, "glosa")):
            encontrado = patron.match(linea)
            if not encontrado:
                continue
            codigo = encontrado.group(1 if orden == "codigo" else 2).lstrip("0").zfill(3)
            if codigo not in codigos_validos:
                continue
            codigos[codigo] = a_monto(encontrado.group(3))
            break

    if not codigos:
        raise ArchivoInvalido(
            "No se pudo leer ningún código del formulario. Sube el F29 tal como lo "
            "entrega el SII, sin recortarlo ni volver a imprimirlo."
        )
    return {"mes": mes, "folio": folio.group(1) if folio else "", "codigos": codigos}
