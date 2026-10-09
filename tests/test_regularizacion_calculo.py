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
    "los ajustes se verifican con el informe actualizado": JS / "test_verificar.js",
    "se respetan las parejas confirmadas en Unificar códigos": JS / "test_uniones.js",
    "se detectan las valorizaciones imposibles": JS / "test_imposibles.js",
    "los costos malos entran al paso 2 del plan": JS / "test_plan.js",
    "cada paso se marca por su cuenta": JS / "test_marcas.js",
    "el ajuste de costo se mide contra lo que Defontana tiene hoy": JS / "test_recosteo.js",
    "se avisa cuando al informe le faltan movimientos": JS / "test_faltanmov.js",
    "el stock valorizado manda sobre lo que arrastran los movimientos": JS / "test_valorizado.js",
    "los costos se llenan en el Excel y se suben de vuelta": JS / "test_costos_excel.js",
    "los productos con unidades y sin valor van en su propio paso": JS / "test_sinvalor.js",
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
    assert "mismo día del ajuste" in (JS / "test_verificar.js").read_text(encoding="utf-8")
    assert "partido en dos" in (JS / "test_uniones.js").read_text(encoding="utf-8")
    assert "no existe" in (JS / "test_imposibles.js").read_text(encoding="utf-8")
    assert "no se inventa uno malo" in (JS / "test_plan.js").read_text(encoding="utf-8")
    assert "no esconde el ajuste de cantidad" in (JS / "test_marcas.js").read_text(encoding="utf-8")
    assert "reproduce el valor de Defontana" in (JS / "test_recosteo.js").read_text(encoding="utf-8")
    assert "manda la foto" in (JS / "test_valorizado.js").read_text(encoding="utf-8")
    assert "se suben de vuelta" in (JS / "test_costos_excel.js").read_text(encoding="utf-8")
    assert "su propia compra" in (JS / "test_sinvalor.js").read_text(encoding="utf-8")
    assert "Saldo Inventario salta" in (JS / "test_faltanmov.js").read_text(encoding="utf-8")
