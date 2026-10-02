"""Los números de página del pie de tabla.

Con "Anterior / Siguiente" a secas, llegar a la página 8 son siete clics, y
volver a la 1 otros siete. Los números permiten saltar directo.
"""

import re

import pytest
from flask import render_template_string


def _pie(app, pagina, total_paginas, registros=785):
    with app.test_request_context("/inventario/stock"):
        html = render_template_string(
            "{% import 'partials/_tabla.html' as t with context %}"
            "{{ t.paginacion(p, tp, n, 'artículos') }}",
            p=pagina, tp=total_paginas, n=registros,
        )
    return html, re.findall(r">(\d+|…)</(?:a|span)>", html)


def test_con_pocas_paginas_se_ven_todas(app):
    _html, botones = _pie(app, 1, 3)
    assert botones == ["1", "2", "3"]


def test_se_puede_saltar_a_la_ultima_sin_pasar_por_las_del_medio(app):
    """Lo que ella pidió: no avanzar de a una para llegar al final."""
    html, botones = _pie(app, 1, 8)

    assert botones[-1] == "8"
    assert "…" in botones
    assert "pagina=8" in html


def test_con_muchisimas_paginas_no_se_dibujan_todas(app):
    """Doscientos botones serían peor que ninguno."""
    _html, botones = _pie(app, 100, 200)

    numeros = [b for b in botones if b != "…"]
    assert len(numeros) <= 9, f"demasiados botones: {botones}"
    # La primera y la última siempre están, para poder saltar a los extremos
    assert numeros[0] == "1" and numeros[-1] == "200"
    # Y las vecinas de donde se está
    assert {"98", "99", "100", "101", "102"} <= set(numeros)


def test_la_pagina_actual_se_marca(app):
    html, _lista = _pie(app, 4, 8)
    assert 'aria-current=page' in html or 'aria-current="page"' in html
    assert "active" in html


@pytest.mark.parametrize("pagina, total", [(1, 8), (8, 8)])
def test_en_los_extremos_el_boton_que_no_lleva_a_nada_queda_apagado(app, pagina, total):
    html, _lista = _pie(app, pagina, total)
    # El botón que no lleva a ninguna parte queda apagado, y sólo ese.
    for etiqueta in ("Anterior", "Siguiente"):
        trozo = html[html.rindex("<a", 0, html.index(f">{etiqueta}</a>")):]
        trozo = trozo[: trozo.index(">") + 1]
        deberia = (etiqueta == "Anterior") if pagina == 1 else (etiqueta == "Siguiente")
        assert ("disabled" in trozo) is deberia, f"{etiqueta} en página {pagina}: {trozo}"


def test_con_una_sola_pagina_no_se_dibuja_ningun_boton(app):
    html, botones = _pie(app, 1, 1)
    assert botones == []
    assert "Siguiente" not in html
    # Pero el total de registros sí se sigue diciendo
    assert "785" in html


def test_ninguna_pantalla_pagina_por_su_cuenta():
    """El macro es uno solo: así los números llegan a todas las pantallas.

    Si alguna escribiera su propio "Anterior / Siguiente", se quedaría sin
    números sin que nadie lo note hasta que alguien tenga que hacer siete
    clics para llegar al final.
    """
    from pathlib import Path

    por_su_cuenta = []
    for plantilla in Path("app/templates").rglob("*.html"):
        if plantilla.name == "_tabla.html":
            continue
        texto = plantilla.read_text(encoding="utf-8")
        if "Siguiente" in texto and "t.paginacion(" not in texto:
            por_su_cuenta.append(plantilla.name)

    assert not por_su_cuenta, f"paginan sin el macro: {por_su_cuenta}"


def test_el_macro_lo_usan_las_pantallas_que_tienen_listados_largos():
    from pathlib import Path

    usan = sorted(
        p.name for p in Path("app/templates").rglob("*.html")
        if "t.paginacion(" in p.read_text(encoding="utf-8")
    )

    assert usan == ["ajuste.html", "cruce_datos.html", "historial_detalle.html", "stock.html"]
