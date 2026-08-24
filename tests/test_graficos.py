"""Los gráficos de barras del tablero.

Las barras se dibujan con un ancho en porcentaje escrito en el atributo style.
Si ese porcentaje sale mal, el gráfico no falla: se dibuja igual, sólo que
mintiendo. Por eso lo que se comprueba acá es la proporción, no que exista el
elemento.
"""

import re

from flask import render_template_string


def _barras(app, datos, macro="barras_agrupadas"):
    with app.test_request_context():
        return render_template_string(
            "{% import 'partials/_graficos.html' as g %}"
            "{{ g." + macro + "(datos) }}",
            datos=datos,
        )


def _anchos(html):
    return [float(x) for x in re.findall(r"width:\s*([\d.]+)%", html)]


def _grupo(nombre, a, b):
    return {
        "etiqueta": nombre,
        "valor_a": a, "valor_a_texto": f"${a}",
        "valor_b": b, "valor_b_texto": f"${b}",
        "diferencia_texto": f"${a - b}", "diferencia_es_cero": a == b,
    }


def test_las_barras_son_proporcionales_al_valor_mas_alto(app):
    """La escala es común a las dos series y a todos los grupos.

    Si cada grupo se escalara por su cuenta, dos líneas de tamaños muy
    distintos se verían iguales y el gráfico dejaría de servir para comparar.
    """
    html = _barras(app, [_grupo("FUSION", 25, 100), _grupo("PRENSAS", 50, 75)])

    assert _anchos(html) == [25.0, 100.0, 50.0, 75.0]


def test_un_valor_en_cero_no_dibuja_barra(app):
    # El 80 es el máximo del gráfico, así que ocupa el 100% del ancho.
    html = _barras(app, [_grupo("SIN STOCK", 0, 80)])
    assert _anchos(html) == [0.0, 100.0]


def test_sin_datos_se_avisa_en_vez_de_dividir_por_cero(app):
    assert "chart-empty" in _barras(app, [])
    # Todo en cero tampoco puede reventar: no hay máximo con el que escalar.
    assert "chart-empty" in _barras(app, [_grupo("VACIA", 0, 0)])


def test_la_diferencia_se_marca_en_verde_solo_si_cuadra(app):
    cuadra = _barras(app, [_grupo("IGUALES", 100, 100)])
    descuadra = _barras(app, [_grupo("DISTINTAS", 100, 90)])

    assert "text-success" in cuadra and "text-danger" not in cuadra
    assert "text-danger" in descuadra and "text-success" not in descuadra


def test_la_barra_de_una_sola_serie_tambien_es_proporcional(app):
    """El mismo macro simple lo usan otros ocho gráficos de la aplicación."""
    datos = [
        {"etiqueta": "Ene", "valor": 20, "texto": "$20"},
        {"etiqueta": "Feb", "valor": 80, "texto": "$80"},
    ]
    assert _anchos(_barras(datos=datos, app=app, macro="barras")) == [25.0, 100.0]
