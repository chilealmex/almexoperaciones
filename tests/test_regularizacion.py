"""Submódulo Regularización: la página entrega el conteo para cruzarlo con Defontana en el navegador."""

import json
import re
from datetime import datetime

from app.models.conteo_inventario import ItemConteoInventario
from tests.conftest import login


def _conteo_de_la_pagina(cuerpo):
    datos = re.search(r'<script type="application/json" id="regx-conteo">(.*?)</script>', cuerpo, re.S)
    assert datos, "la página debe traer el conteo como JSON"
    return json.loads(datos.group(1))


def _items(db, empresa, usuario):
    db.session.add_all([
        ItemConteoInventario(
            empresa_id=empresa.id, codigo="COD-001", nombre="PRODUCTO UNO",
            cantidad_fisica=12.5, contado_por_id=usuario.id,
            contado_en=datetime(2026, 8, 19, 21, 33),  # UTC → 17:33 en Chile
            unidad_qms="M", unidad_defontana="FT", linea_negocio="PRENSAS",
        ),
        ItemConteoInventario(empresa_id=empresa.id, codigo="COD-002", nombre="PRODUCTO DOS"),
    ])
    db.session.commit()


def test_la_pagina_trae_el_conteo_con_fecha_y_hora_local(client, db, empresa, usuario_bodega):
    _items(db, empresa, usuario_bodega)
    login(client, "bodega@test.cl")

    respuesta = client.get("/inventario/regularizacion")
    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)

    conteo = {fila[0]: fila for fila in _conteo_de_la_pagina(cuerpo)}
    assert conteo["COD-001"] == ["COD-001", "PRODUCTO UNO", 12.5, "Contado", "Bodega de Prueba", "19-08-2026 17:33", "M", "PRENSAS"]
    assert conteo["COD-002"] == ["COD-002", "PRODUCTO DOS", None, "Pendiente", "", "", "", ""]
    assert "2 códigos · 1 contados" in cuerpo


def test_la_pagina_carga_su_javascript_y_la_libreria_de_excel_local(client, usuario_bodega):
    login(client, "bodega@test.cl")
    cuerpo = client.get("/inventario/regularizacion").get_data(as_text=True)
    # la política de seguridad solo permite scripts propios: nada desde CDN
    assert "/static/vendor/xlsx/xlsx.full.min.js" in cuerpo
    assert "/static/js/regularizacion.js" in cuerpo
    assert "/static/css/regularizacion.css" in cuerpo
    assert client.get("/static/vendor/xlsx/xlsx.full.min.js").status_code == 200


def test_sin_conteo_avisa_donde_registrarlo(client, usuario_bodega):
    login(client, "bodega@test.cl")
    cuerpo = client.get("/inventario/regularizacion").get_data(as_text=True)
    assert "Aún no hay productos contados" in cuerpo
    assert _conteo_de_la_pagina(cuerpo) == []


def test_solo_ve_el_conteo_de_su_empresa(client, db, empresa, usuario_bodega):
    from app.models.empresa import Empresa

    otra = Empresa(rut="77.000.000-0", razon_social="Otra SPA")
    db.session.add(otra)
    db.session.commit()
    db.session.add(ItemConteoInventario(empresa_id=otra.id, codigo="AJENO", cantidad_fisica=1))
    db.session.commit()

    login(client, "bodega@test.cl")
    cuerpo = client.get("/inventario/regularizacion").get_data(as_text=True)
    assert "AJENO" not in cuerpo


def test_aparece_en_el_menu_de_inventario(client, usuario_bodega):
    login(client, "bodega@test.cl")
    cuerpo = client.get("/inventario/stock").get_data(as_text=True)
    assert "/inventario/regularizacion" in cuerpo
    assert "Regularización" in cuerpo
