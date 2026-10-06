"""Submódulo Regularización: independiente de la toma de inventario; trabaja con los archivos que se suben y los guarda."""

import io
import json
import re
from datetime import datetime

from app.models.conteo_inventario import ItemConteoInventario
from app.models.regularizacion import RegularizacionArchivo
from tests.conftest import login


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


def test_no_toma_nada_de_stock_y_conteo(client, db, empresa, usuario_bodega):
    """Aunque haya un conteo en Stock y conteo, Regularización no lo usa: se sube su propio archivo."""
    _items(db, empresa, usuario_bodega)
    login(client, "bodega@test.cl")

    respuesta = client.get("/inventario/regularizacion")
    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert 'id="regx-conteo"' not in cuerpo
    assert "COD-001" not in cuerpo and "PRODUCTO UNO" not in cuerpo
    assert "Elige o arrastra el Excel del conteo físico" in cuerpo


def test_la_pagina_carga_su_javascript_y_la_libreria_de_excel_local(client, usuario_bodega):
    login(client, "bodega@test.cl")
    cuerpo = client.get("/inventario/regularizacion").get_data(as_text=True)
    # la política de seguridad solo permite scripts propios: nada desde CDN
    assert "/static/vendor/xlsx/xlsx.full.min.js" in cuerpo
    assert "/static/js/regularizacion.js" in cuerpo
    assert "/static/css/regularizacion.css" in cuerpo
    assert client.get("/static/vendor/xlsx/xlsx.full.min.js").status_code == 200


def test_guardar_y_leer_el_conteo_subido(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    respuesta = client.post(
        "/inventario/regularizacion/guardado/conteo",
        data={"archivo": (io.BytesIO(b"excel del conteo"), "conteo.xlsx")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 200
    assert client.get("/inventario/regularizacion/guardado/conteo").data == b"excel del conteo"
    config = _config_de_la_pagina(client.get("/inventario/regularizacion").get_data(as_text=True))
    assert config["guardados"]["conteo"]["nombre"] == "conteo.xlsx"


def test_muestra_la_ultima_actualizacion_guardada(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    assert "Aún no hay nada guardado" in client.get("/inventario/regularizacion").get_data(as_text=True)
    client.post(
        "/inventario/regularizacion/guardado/informe",
        data={"archivo": (io.BytesIO(b"informe"), "informe.xlsx")},
        content_type="multipart/form-data",
    )
    cuerpo = client.get("/inventario/regularizacion").get_data(as_text=True)
    assert "Última actualización guardada" in cuerpo


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


def test_guardar_y_quitar_el_stock_valorizado(client, db, empresa, usuario_admin):
    """El Informe de Artículos se guarda como los demás, para no resubirlo cada vez."""
    login(client, "admin@test.cl")
    respuesta = client.post(
        "/inventario/regularizacion/guardado/articulos",
        data={"archivo": (io.BytesIO(b"stock valorizado"), "Informe_Articulo.xlsx")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 200
    config = _config_de_la_pagina(client.get("/inventario/regularizacion").get_data(as_text=True))
    assert config["guardados"]["articulos"]["nombre"] == "Informe_Articulo.xlsx"
    assert client.get("/inventario/regularizacion/guardado/articulos").data == b"stock valorizado"

    assert client.post("/inventario/regularizacion/guardado/articulos", data={"borrar": "1"}).status_code == 200
    assert client.get("/inventario/regularizacion/guardado/articulos").status_code == 404


def test_la_pagina_ofrece_subir_el_stock_valorizado(client, db, empresa, usuario_admin):
    """Sin la casilla en la página no hay dónde subirlo, por bien que lo lea el cálculo."""
    login(client, "admin@test.cl")
    html = client.get("/inventario/regularizacion").get_data(as_text=True)
    assert 'id="fileArticulos"' in html
    assert "Stock valorizado actualizado" in html


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


# --- Empezar una regularización nueva: la anterior queda en el historial ---


def _subir(client, clave, contenido, nombre):
    return client.post(
        f"/inventario/regularizacion/guardado/{clave}",
        data={"archivo": (io.BytesIO(contenido), nombre)},
        content_type="multipart/form-data",
    )


def test_empezar_una_nueva_guarda_la_anterior_en_el_historial(client, db, empresa, usuario_admin):
    from app.models.regularizacion import RegularizacionHistorial

    login(client, "admin@test.cl")
    _subir(client, "conteo", b"conteo de septiembre", "conteo.xlsx")
    _subir(client, "informe", b"informe de septiembre", "informe.xlsx")
    client.post("/inventario/regularizacion/guardado/estado", data=json.dumps({"hechos": {}}), content_type="application/json")

    respuesta = client.post("/inventario/regularizacion/archivar", data={"nombre": "Septiembre 2026"})
    assert respuesta.status_code == 302

    # la pantalla queda vacía para subir lo nuevo
    assert RegularizacionArchivo.query.count() == 0
    assert "Aún no hay nada guardado" in client.get("/inventario/regularizacion").get_data(as_text=True)

    # y la anterior queda en el historial, con sus archivos y su estado
    historial = RegularizacionHistorial.query.one()
    assert historial.nombre == "Septiembre 2026"
    assert sorted(a.clave for a in historial.archivos) == ["conteo", "estado", "informe"]
    lista = client.get("/inventario/regularizacion/historial").get_data(as_text=True)
    assert "Septiembre 2026" in lista and "conteo.xlsx" in lista

    # se puede abrir para verla: lee sus propios archivos y no guarda cambios
    pagina = client.get(f"/inventario/regularizacion/historial/{historial.id}")
    assert pagina.status_code == 200
    config = _config_de_la_pagina(pagina.get_data(as_text=True))
    assert config["guardar"] is False and config["historial"] is True
    assert config["guardados"]["conteo"]["nombre"] == "conteo.xlsx"
    url = config["url"].replace("__CLAVE__", "informe")
    assert client.get(url).data == b"informe de septiembre"

    # subir lo nuevo no toca lo guardado en el historial
    _subir(client, "informe", b"informe de octubre", "informe.xlsx")
    assert client.get(url).data == b"informe de septiembre"
    assert client.get("/inventario/regularizacion/guardado/informe").data == b"informe de octubre"


def test_sin_archivos_no_se_guarda_nada_en_el_historial(client, db, empresa, usuario_admin):
    from app.models.regularizacion import RegularizacionHistorial

    login(client, "admin@test.cl")
    client.post("/inventario/regularizacion/archivar", data={})
    assert RegularizacionHistorial.query.count() == 0


def test_borrar_del_historial(client, db, empresa, usuario_admin):
    from app.models.regularizacion import RegularizacionHistorial, RegularizacionHistorialArchivo

    login(client, "admin@test.cl")
    _subir(client, "informe", b"informe", "informe.xlsx")
    client.post("/inventario/regularizacion/archivar", data={})
    historial = RegularizacionHistorial.query.one()
    assert historial.nombre.startswith("Regularización del ")
    assert client.post(f"/inventario/regularizacion/historial/{historial.id}/borrar").status_code == 302
    assert RegularizacionHistorial.query.count() == 0
    assert RegularizacionHistorialArchivo.query.count() == 0


def test_sin_permiso_de_edicion_no_se_puede_empezar_una_nueva(client, db, empresa, usuario_bodega):
    login(client, "bodega@test.cl")
    assert client.post("/inventario/regularizacion/archivar", data={}).status_code == 403
    assert client.get("/inventario/regularizacion/historial").status_code == 200


# --- Las parejas confirmadas en Unificar códigos llegan a esta pantalla ---
#
# Regularización trabaja con los archivos que se suben en ella, no con el
# maestro, así que cruza los códigos por su cuenta: ignora signos, acentos y
# ceros de adelante. Eso no alcanza para dos códigos que no se parecen y que
# alguien decidió que son el mismo artículo: sin pasárselas, ese artículo queda
# partido en dos y aparece descuadrado por los dos lados.


def test_la_pantalla_recibe_las_parejas_confirmadas(client, db, empresa, usuario_admin):
    from app.models.conteo_inventario import ItemConteoInventario
    from app.models.equivalencia_codigo import crear_equivalencia

    db.session.add_all([
        ItemConteoInventario(empresa_id=empresa.id, codigo="ABC-100", en_qms=True, en_defontana=False),
        ItemConteoInventario(empresa_id=empresa.id, codigo="XYZ-7", en_qms=False, en_defontana=True),
    ])
    db.session.commit()
    crear_equivalencia(empresa.id, "ABC-100", "XYZ-7", usuario_admin.id, 100, "a mano")
    db.session.commit()

    login(client, "admin@test.cl")
    config = _config_de_la_pagina(client.get("/inventario/regularizacion").get_data(as_text=True))

    assert ["XYZ-7", "ABC-100"] in config["uniones"]


def test_tambien_llegan_los_codigos_unidos_por_repetidos(client, db, empresa, usuario_admin):
    """Las dos vías de unir valen acá: la pareja entre sistemas y la línea
    retirada al juntar dos códigos repetidos del maestro."""
    from app.models.codigo_unificado import registrar_unificacion

    registrar_unificacion(empresa.id, "11-AAA-01", "011-AAA-01", usuario_admin.id)
    db.session.commit()

    login(client, "admin@test.cl")
    config = _config_de_la_pagina(client.get("/inventario/regularizacion").get_data(as_text=True))

    assert ["011-AAA-01", "11-AAA-01"] in config["uniones"]


def test_sin_uniones_la_lista_va_vacia(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    config = _config_de_la_pagina(client.get("/inventario/regularizacion").get_data(as_text=True))

    assert config["uniones"] == []
