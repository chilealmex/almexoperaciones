"""El cálculo del ajuste de Regularización, que vive en el navegador.

Es la matemática que decide cuánto ajustar el inventario, y hasta ahora no se
podía comprobar más que a ojo: el módulo corre en el navegador y no había forma
de llamarlo desde una prueba. Las comprobaciones están en tests/js/ y se corren
con node; acá se las engancha al resto de la suite.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
JS = Path(__file__).parent / "js"
PRUEBAS = {
    "el ajuste se mide al momento de contar": JS / "test_ajuste.js",
    "los costos fuera de lo normal se detectan": JS / "test_costos.js",
    "los datos se buscan en la hoja que los tenga": JS / "test_hojas.js",
}


@pytest.mark.skipif(NODE is None, reason="hace falta node para correr el cálculo del navegador")
@pytest.mark.parametrize("que_prueba", sorted(PRUEBAS), ids=sorted(PRUEBAS))
def test_el_calculo_del_navegador(que_prueba):
    archivo = PRUEBAS[que_prueba]
    resultado = subprocess.run(
        [NODE, str(archivo)], capture_output=True, text=True, timeout=120,
        cwd=str(JS.parent.parent),
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_las_comprobaciones_del_navegador_existen():
    """Si un archivo se borra, su prueba pasaría sin comprobar nada."""
    for archivo in PRUEBAS.values():
        assert archivo.exists(), archivo
    assert "entrada por 2" in (JS / "test_ajuste.js").read_text(encoding="utf-8")
    assert "20 veces" in (JS / "test_costos.js").read_text(encoding="utf-8")
    assert "segunda hoja" in (JS / "test_hojas.js").read_text(encoding="utf-8")
