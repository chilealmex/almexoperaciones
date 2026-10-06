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
PRUEBA = Path(__file__).parent / "js" / "test_ajuste.js"


@pytest.mark.skipif(NODE is None, reason="hace falta node para correr el cálculo del navegador")
def test_el_ajuste_se_mide_al_momento_de_contar():
    resultado = subprocess.run(
        [NODE, str(PRUEBA)], capture_output=True, text=True, timeout=120,
        cwd=str(PRUEBA.parent.parent.parent),
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_las_comprobaciones_del_navegador_existen():
    """Si el archivo se borra, la prueba de arriba pasaría sin comprobar nada."""
    assert PRUEBA.exists()
    assert "entrada por 2" in PRUEBA.read_text(encoding="utf-8")
