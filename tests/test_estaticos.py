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
