"""Submódulo Regularización: la página entrega el conteo para cruzarlo con Defontana en el navegador."""

import io
import json
import re
from datetime import datetime

from app.models.conteo_inventario import ItemConteoInventario
from app.models.regularizacion import RegularizacionArchivo
from tests.conftest import login


def _conteo_de_la_pagina(cuerpo):
    datos = re.search(r'<script type="application/json" id="regx-conteo">(.*?)</script>', cuerpo, re.S)
    assert datos, "la página debe traer el conteo como JSON"
    return json.loads(datos.group(1))


def _config_de_la_pagina(cuerpo):
    datos = re.search(r'<script type="application/json" id="regx-config">(.*?)</script>', cuerpo, re.S)
    assert datos, "la página debe traer la configuración de guardado"
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


# --- Lo que se sube queda guardado ---


def test_guardar_y_leer_un_informe(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    respuesta = client.post(
        "/inventario/regularizacion/guardado/informe",
        data={"archivo": (io.BytesIO(b"contenido del informe"), "informe.xlsx")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json()["nombre"] == "informe.xlsx"

    leido = client.get("/inventario/regularizacion/guardado/informe")
    assert leido.status_code == 200
    assert leido.data == b"contenido del informe"

    # la página avisa que hay un informe guardado para cargarlo solo
    config = _config_de_la_pagina(client.get("/inventario/regularizacion").get_data(as_text=True))
    assert config["guardados"]["informe"]["nombre"] == "informe.xlsx"
    assert config["guardar"] is True


def test_guardar_y_quitar_el_archivo_de_ajustes_hechos(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    respuesta = client.post(
        "/inventario/regularizacion/guardado/ajustes",
        data={"archivo": (io.BytesIO(b"solo ajustes"), "solo_ajuste.xlsx")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 200
    config = _config_de_la_pagina(client.get("/inventario/regularizacion").get_data(as_text=True))
    assert config["guardados"]["ajustes"]["nombre"] == "solo_ajuste.xlsx"

    assert client.post("/inventario/regularizacion/guardado/ajustes", data={"borrar": "1"}).status_code == 200
    assert client.get("/inventario/regularizacion/guardado/ajustes").status_code == 404


def test_subir_de_nuevo_reemplaza_lo_guardado(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    for contenido in (b"primero", b"segundo"):
        client.post(
            "/inventario/regularizacion/guardado/informe",
            data={"archivo": (io.BytesIO(contenido), "informe.xlsx")},
            content_type="multipart/form-data",
        )
    assert RegularizacionArchivo.query.filter_by(clave="informe").count() == 1
    assert client.get("/inventario/regularizacion/guardado/informe").data == b"segundo"


def test_guardar_el_estado_en_json(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    estado = {"recount": {"COD001": {"qty": 38, "fecha": 1}}, "pmp": {}, "ajSel": None}
    respuesta = client.post("/inventario/regularizacion/guardado/estado", data=json.dumps(estado), content_type="application/json")
    assert respuesta.status_code == 200
    assert client.get("/inventario/regularizacion/guardado/estado").get_json() == estado
    assert client.post("/inventario/regularizacion/guardado/estado", data="no es json", content_type="application/json").status_code == 400


def test_sin_permiso_de_edicion_no_se_guarda_pero_se_lee(client, db, empresa, usuario_bodega):
    db.session.add(RegularizacionArchivo(empresa_id=empresa.id, clave="informe", nombre="x.xlsx", contenido=b"guardado"))
    db.session.commit()
    login(client, "bodega@test.cl")
    respuesta = client.post(
        "/inventario/regularizacion/guardado/informe",
        data={"archivo": (io.BytesIO(b"otro"), "otro.xlsx")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 403
    assert client.get("/inventario/regularizacion/guardado/informe").data == b"guardado"
    assert _config_de_la_pagina(client.get("/inventario/regularizacion").get_data(as_text=True))["guardar"] is False


def test_lo_guardado_es_de_cada_empresa(client, db, empresa, usuario_admin):
    from app.models.empresa import Empresa

    otra = Empresa(rut="77.000.000-0", razon_social="Otra SPA")
    db.session.add(otra)
    db.session.commit()
    db.session.add(RegularizacionArchivo(empresa_id=otra.id, clave="informe", nombre="ajeno.xlsx", contenido=b"ajeno"))
    db.session.commit()
    login(client, "admin@test.cl")
    assert client.get("/inventario/regularizacion/guardado/informe").status_code == 404
    assert client.get("/inventario/regularizacion/guardado/otra-cosa").status_code == 404


# --- Conteo de una toma cerrada ---


def test_con_la_toma_cerrada_usa_su_conteo(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    _items(db, empresa, usuario_admin)
    client.post("/inventario/toma/cerrar")   # archiva el conteo y deja el cruce vivo en blanco

    cuerpo = client.get("/inventario/regularizacion").get_data(as_text=True)
    conteo = {fila[0]: fila for fila in _conteo_de_la_pagina(cuerpo)}
    assert conteo["COD-001"][2] == 12.5            # viene de la toma cerrada
    assert "toma cerrada" in cuerpo

    # se puede elegir el conteo en curso, que quedó vacío
    cuerpo = client.get("/inventario/regularizacion?conteo=actual").get_data(as_text=True)
    assert all(fila[2] is None for fila in _conteo_de_la_pagina(cuerpo))
