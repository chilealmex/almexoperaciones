"""La línea de negocio de cada artículo, pegada a un informe de Defontana.

El Informe de Inventario de Defontana —"Código Artículo", "Descripción",
"Categoría", "Bodega", "Saldo", "Unidad", "Valorización"— dice cuánto hay de
cada producto pero no a qué línea de negocio pertenece. Esa información está en
los archivos de Regularización, y en tres lugares que no siempre dicen lo
mismo: el conteo, QMS y el Informe de Artículos de Defontana.

Acá se juntan las tres. Cuando las tres coinciden sale una sola, porque es el
mismo nombre escrito tres veces; cuando no, salen las tres con su origen, que
es justo el caso que hay que ir a mirar.
"""

from io import BytesIO

from app.utils.codigos import codigo_normalizado
# Los lectores de planillas viven en el importador: leen .xlsx y .csv, buscan
# la cabecera aunque no esté en la primera fila y aguantan las codificaciones
# con que exporta cada sistema. Reimplementarlos acá sería tener dos lectores
# que se arreglan por separado.
from app.utils.importar_conteo import _buscar_columna_plana, _leer_filas, _sin_tildes


class SinArchivos(Exception):
    """Ninguno de los archivos de Regularización tiene línea de negocio."""


# De qué archivo de Regularización sale cada línea, y cómo se llama su columna
# en ese archivo. El orden es el que se muestra: conteo, QMS, Defontana.
FUENTES = (
    ("conteo", "Conteo", ("linea",)),
    ("qms", "QMS", ("linea",)),
    ("articulos", "Defontana", ("linea",)),
)

# Lo que se escribe en la columna de aviso. Vacío cuando no hay nada que mirar.
AVISO_DISTINTAS = "Las tres no coinciden"
AVISO_SIN_LINEA = "No está en los archivos de Regularización"


class _Archivo:
    """Un blob de la base presentado como el archivo que los lectores esperan."""

    def __init__(self, nombre, contenido):
        self.filename = nombre or ""
        self.stream = BytesIO(contenido)


def _misma_linea(a: str, b: str) -> bool:
    """Si dos líneas son la misma escritas distinto.

    "INS DE PRODUCCION" y "Ins de Producción" son la misma línea: cada sistema
    la escribe a su manera y compararlas tal cual las dejaría como distintas en
    casi todas las filas, que es el aviso que no sirve.
    """
    return _clave_de_linea(a) == _clave_de_linea(b)


def _clave_de_linea(texto: str) -> str:
    return _sin_tildes(str(texto or "")).strip().upper()


def leer_lineas(archivos: dict) -> dict:
    """{código normalizado: {"Conteo": línea, "QMS": línea, "Defontana": línea}}.

    `archivos` es {clave de Regularización: (nombre, contenido)}. Las claves que
    no estén se saltan: con dos archivos cargados se cruza con dos.
    """
    lineas = {}
    for clave, etiqueta, palabras in FUENTES:
        if clave not in archivos:
            continue
        nombre, contenido = archivos[clave]
        for codigo, linea in _lineas_del_archivo(nombre, contenido, palabras).items():
            lineas.setdefault(codigo, {})[etiqueta] = linea
    if not lineas:
        raise SinArchivos(
            "Ninguno de los archivos de Regularización trae línea de negocio. "
            "Carga el conteo, el de QMS o el Informe de Artículos y vuelve a intentarlo."
        )
    return lineas


def _lineas_del_archivo(nombre, contenido, palabras) -> dict:
    """{código: línea} de un archivo, saltándose las filas sin línea."""
    try:
        encabezados, filas = _leer_filas(_Archivo(nombre, contenido),
                                         codificaciones_csv=("utf-8-sig", "cp1252", "latin-1"))
    except Exception:
        # Un archivo que no se puede leer no debe voltear el informe entero: se
        # cruza con los que sí se leen y el resumen dice con cuáles se cruzó.
        return {}

    columna_codigo = (
        _buscar_columna_plana(encabezados, "digo", "nico")
        or _buscar_columna_plana(encabezados, "digo", "art")
        or _buscar_columna_plana(encabezados, "codarticulo")
        or _buscar_columna_plana(encabezados, "digo")
    )
    columna_linea = _buscar_columna_plana(encabezados, *palabras)
    if not columna_codigo or not columna_linea:
        return {}

    salida = {}
    for fila in filas:
        codigo = codigo_normalizado(fila.get(columna_codigo) or "")
        linea = str(fila.get(columna_linea) or "").strip()
        # La primera gana: un artículo puede venir en varias filas —una por
        # bodega— y todas traen la misma línea.
        if codigo and linea and codigo not in salida:
            salida[codigo] = linea
    return salida


def resolver(lineas_del_articulo: dict) -> tuple:
    """(línea a mostrar, aviso) para un artículo.

    Una sola cuando las fuentes que lo conocen dicen lo mismo; las tres con su
    origen cuando no. Una fuente que no tiene el artículo no cuenta como
    desacuerdo: no sabe, que es distinto de contradecir.
    """
    dichas = [(etiqueta, (lineas_del_articulo or {}).get(etiqueta, "").strip())
              for _clave, etiqueta, _palabras in FUENTES]
    dichas = [(etiqueta, linea) for etiqueta, linea in dichas if linea]
    if not dichas:
        return "", AVISO_SIN_LINEA

    primera = dichas[0][1]
    if all(_misma_linea(linea, primera) for _etiqueta, linea in dichas):
        return primera, ""
    return " · ".join(f"{etiqueta}: {linea}" for etiqueta, linea in dichas), AVISO_DISTINTAS


def es_subtotal(fila: dict, columna_codigo: str, columna_nombre: str) -> bool:
    """Si la fila es un subtotal del informe y no un artículo.

    Defontana intercala una fila "Total Artículo XXX:" después de cada producto
    y cierra con "TOTAL GENERAL:". En la planilla van pintadas de verde, pero lo
    que las delata sin depender del color —que cambia si el informe se vuelve a
    guardar— es que no traen código: el código es de quien es artículo.
    """
    if str(fila.get(columna_codigo) or "").strip():
        return False
    nombre = str(fila.get(columna_nombre) or "").strip().upper()
    return nombre.startswith("TOTAL") or not nombre


def leer_informe(file_storage) -> dict:
    """El informe de Defontana sin sus subtotales.

    Devuelve los encabezados tal como vienen —el informe se entrega con sus
    mismas columnas, más la nueva al lado— y las filas de artículo, contando
    cuántos subtotales se sacaron para poder decirlo.
    """
    encabezados, filas = _leer_filas(file_storage,
                                     codificaciones_csv=("cp1252", "latin-1", "utf-8-sig"))
    encabezados = [e for e in encabezados if e]
    columna_codigo = (
        _buscar_columna_plana(encabezados, "digo", "art")
        or _buscar_columna_plana(encabezados, "codarticulo")
        or _buscar_columna_plana(encabezados, "digo")
    )
    if not columna_codigo:
        raise ValueError(
            "No encontré la columna “Código Artículo”. ¿Es el Informe de Inventario de Defontana?"
        )
    columna_nombre = _buscar_columna_plana(encabezados, "descripci") or ""

    articulos, subtotales = [], 0
    for fila in filas:
        if es_subtotal(fila, columna_codigo, columna_nombre):
            subtotales += 1
            continue
        articulos.append(fila)

    if not articulos:
        raise ValueError("El informe no trae artículos: sólo encontré filas de totales.")

    return {"encabezados": encabezados, "columna_codigo": columna_codigo,
            "filas": articulos, "subtotales": subtotales}


def fuentes_con_datos(lineas: dict) -> list:
    """Las fuentes que de verdad aportaron líneas, en el orden de siempre.

    No es lo mismo que "los archivos cargados": uno guardado en Regularización
    puede venir en un formato que el lector no abre, o sin la columna de línea,
    y entonces no aporta nada. Nombrarlo igual en el resumen haría creer que su
    línea se tomó en cuenta cuando no.
    """
    presentes = {etiqueta for dicho in lineas.values() for etiqueta in dicho}
    return [etiqueta for _clave, etiqueta, _palabras in FUENTES if etiqueta in presentes]


def informe_con_lineas(informe: dict, lineas: dict) -> dict:
    """Las filas del informe con la línea de negocio al lado, y el resumen.

    Las columnas del informe se entregan tal como vinieron: lo que se agrega va
    al final, para que la planilla siga siendo la misma más una columna.
    """
    encabezados = informe["encabezados"]
    columna_codigo = informe["columna_codigo"]

    filas, distintas, sin_linea = [], 0, 0
    for fila in informe["filas"]:
        codigo = codigo_normalizado(fila.get(columna_codigo) or "")
        linea, aviso = resolver(lineas.get(codigo))
        if aviso == AVISO_DISTINTAS:
            distintas += 1
        elif aviso == AVISO_SIN_LINEA:
            sin_linea += 1
        # Una sola columna. Lo que pasa con cada artículo —si quedó sin línea o
        # si las fuentes no coinciden— se cuenta para el resumen, que va en su
        # propia hoja: el informe se entrega como el de Defontana más una
        # columna, no más dos.
        filas.append([fila.get(e) for e in encabezados] + [linea])

    return {
        "encabezados": encabezados + ["Línea de negocio"],
        "filas": filas,
        "resumen": {
            "fuentes": fuentes_con_datos(lineas),
            "articulos": len(filas),
            "subtotales": informe["subtotales"],
            "con_linea": len(filas) - sin_linea,
            "sin_linea": sin_linea,
            "distintas": distintas,
        },
    }
