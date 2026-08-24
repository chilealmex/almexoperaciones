"""Comprobaciones de los archivos estáticos.

Un error de sintaxis en la hoja de estilos no rompe ninguna página: el
navegador simplemente ignora el resto del archivo. Se ve "casi bien" y los
estilos que faltan pasan inadvertidos hasta que alguien nota que una pantalla
quedó como antes. Por eso se comprueba aquí.
"""

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CSS = RAIZ / "app" / "static" / "css" / "custom.css"
JS = RAIZ / "app" / "static" / "js" / "main.js"


def _sin_comentarios(texto: str) -> str:
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


def test_la_hoja_de_estilos_tiene_todas_las_llaves_cerradas():
    contenido = _sin_comentarios(CSS.read_text(encoding="utf-8"))
    abiertas, cerradas = contenido.count("{"), contenido.count("}")
    assert abiertas == cerradas, (
        f"custom.css tiene {abiertas} llaves de apertura y {cerradas} de cierre. "
        "Con una sin cerrar, el navegador descarta todo lo que viene después."
    )


def test_ningun_bloque_de_estilos_queda_abierto_a_mitad_de_archivo():
    """Además de cuadrar el total, ninguna llave puede cerrarse de más."""
    contenido = _sin_comentarios(CSS.read_text(encoding="utf-8"))
    profundidad = 0
    for numero, linea in enumerate(contenido.split("\n"), 1):
        profundidad += linea.count("{") - linea.count("}")
        assert profundidad >= 0, f"llave de cierre de más en la línea {numero} de custom.css"
    assert profundidad == 0


def test_el_javascript_tiene_los_parentesis_y_llaves_cuadrados():
    contenido = JS.read_text(encoding="utf-8")
    sin_comentarios = re.sub(r"//[^\n]*", "", _sin_comentarios(contenido))
    for abre, cierra in (("{", "}"), ("(", ")"), ("[", "]")):
        assert sin_comentarios.count(abre) == sin_comentarios.count(cierra), (
            f"main.js no cuadra en '{abre}{cierra}'"
        )


def _bloque(selector: str) -> str:
    """Devuelve el cuerpo de la regla CSS de un selector, sin comentarios."""
    contenido = _sin_comentarios(CSS.read_text(encoding="utf-8"))
    patron = re.compile(r"(^|[},])\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", re.M)
    encontrado = patron.search(contenido)
    assert encontrado, f"no existe la regla {selector} en custom.css"
    return encontrado.group(2)


def test_el_relleno_de_las_barras_es_un_bloque():
    """Sin esto, ningún gráfico de barras muestra su valor.

    .bar-fill es un <span>. En un elemento en línea el navegador ignora width y
    height, así que el relleno medía 0x0 y sólo se veía la pista gris de fondo:
    todas las barras se veían iguales sin importar el monto. Medido en Chromium:
    display 'inline', 0x0 px. Con display:block pasó a 160px y 488px para 32,8%
    y 100%. Afecta a los nueve gráficos de barras de la aplicación.
    """
    assert "display: block" in _bloque(".bar-fill")


def test_la_pista_de_las_barras_tiene_alto():
    """Si la pista no tiene alto, no hay dónde dibujar el relleno."""
    assert "height" in _bloque(".bar-track")
