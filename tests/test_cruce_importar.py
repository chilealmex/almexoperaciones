"""Subir las dos planillas sin salir de Cruce de datos.

Arreglar un código y volver a cargarlo era ida y vuelta a Importar cada vez, y
al volver se perdía el filtro que se traía puesto.
"""

import io

from app.models.conteo_inventario import ItemConteoInventario
from app.models.importacion_inventario import ultimas_importaciones
from tests.conftest import login

CSV_QMS = """﻿Sucursal;Linea Negocio;Categoria; Valor Total Stock CLP ;Stock;Stock Critico;Descripción;Unidad;Código Único;ubicacion_bodega; Valor Unitario CLP
Casa Matriz;GOMAS;CAT-A;100000;10;0;PRODUCTO UNO;UN;COD-001;RACK A1; 10,000
Casa Matriz;ACEROS;CAT-B;70000;7;0;PRODUCTO DOS;UN;COD-002;RACK B2; 10,000
"""

CSV_DEFONTANA = (
    "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad;Costo Unitario\r\n"
    '"COD-001";"PRODUCTO UNO";"BODEGACENTRAL";"BODEGA CENTRAL";"8";"UN";"9.500"\r\n'
    '"COD-003";"PRODUCTO TRES";"BODEGACENTRAL";"BODEGA CENTRAL";"4";"UN";"500"\r\n'
)


def _archivo(texto, nombre, codificacion="utf-8"):
    return (io.BytesIO(texto.encode(codificacion)), nombre)


def _subir(client, follow_redirects=False, **campos):
    datos = {"solo_no_contados": "y"}
    datos.update(campos)
    return client.post(
        "/inventario/cruce-datos/importar", data=datos,
        content_type="multipart/form-data", follow_redirects=follow_redirects,
    )


def _por_codigo(codigo):
    return ItemConteoInventario.query.filter_by(codigo=codigo).one()


# --- Las dos planillas de una vez ---


def test_subir_los_dos_archivos_carga_los_dos_sistemas(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    _subir(
        client,
        archivo_qms=_archivo(CSV_QMS, "qms.csv"),
        archivo_defontana=_archivo(CSV_DEFONTANA, "defontana.csv", "cp1252"),
    )

    assert ItemConteoInventario.query.count() == 3
    assert _por_codigo("COD-001").cantidad_qms == 10
    assert _por_codigo("COD-001").cantidad_defontana == 8
    # Y cada uno queda sabiendo en qué sistema está y en cuál no
    assert _por_codigo("COD-002").falta_en == "Defontana"
    assert _por_codigo("COD-003").falta_en == "QMS"


def test_se_puede_subir_uno_solo_sin_tocar_el_otro(client, db, empresa, usuario_admin):
    """Sirve para volver a cargar sólo el sistema que se arregló. Si exigiera
    los dos, habría que volver a exportar el otro sin necesidad."""
    login(client, "admin@test.cl")
    _subir(
        client,
        archivo_qms=_archivo(CSV_QMS, "qms.csv"),
        archivo_defontana=_archivo(CSV_DEFONTANA, "defontana.csv", "cp1252"),
    )

    qms_corregido = CSV_QMS.replace(";10;0;PRODUCTO UNO", ";99;0;PRODUCTO UNO")
    _subir(client, archivo_qms=_archivo(qms_corregido, "qms.csv"))

    assert _por_codigo("COD-001").cantidad_qms == 99   # lo que se volvió a subir
    assert _por_codigo("COD-001").cantidad_defontana == 8   # lo otro, intacto


def test_sin_ningun_archivo_avisa_y_no_borra_nada(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    _subir(client, archivo_qms=_archivo(CSV_QMS, "qms.csv"))

    respuesta = _subir(client)
    cuerpo = client.get(respuesta.headers["Location"]).get_data(as_text=True)

    assert "Elige al menos uno" in cuerpo
    assert ItemConteoInventario.query.count() == 2   # lo ya cargado sigue ahí


def test_un_archivo_que_no_es_planilla_no_se_traga(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    respuesta = _subir(client, archivo_qms=_archivo("no soy una planilla", "notas.txt"))
    cuerpo = client.get(respuesta.headers["Location"]).get_data(as_text=True)

    assert ".csv o .xlsx" in cuerpo
    assert ItemConteoInventario.query.count() == 0


def test_si_la_primera_planilla_viene_mala_la_segunda_igual_se_carga(client, db, empresa, usuario_admin):
    """La mala va primero a propósito: si la carga se cortara en el primer
    error, la buena que venía detrás se perdería y habría que volver a
    subirla. Guardar las dos juntas o ninguna tendría el mismo problema."""
    login(client, "admin@test.cl")

    _subir(
        client,
        archivo_qms=_archivo("esto no tiene las columnas\n", "qms.csv"),
        archivo_defontana=_archivo(CSV_DEFONTANA, "defontana.csv", "cp1252"),
    )

    assert _por_codigo("COD-001").cantidad_defontana == 8
    assert ultimas_importaciones(empresa.id).get("qms") is None


def test_si_la_segunda_planilla_viene_mala_la_primera_queda_guardada(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    _subir(
        client,
        archivo_qms=_archivo(CSV_QMS, "qms.csv"),
        archivo_defontana=_archivo("esto no tiene las columnas\n", "defontana.csv"),
    )

    assert _por_codigo("COD-001").cantidad_qms == 10
    assert ultimas_importaciones(empresa.id).get("defontana") is None


def test_si_la_base_rechaza_un_dato_se_avisa_en_vez_de_un_error_500(client, db, empresa, usuario_admin):
    """Una página de "Internal Server Error" no le dice nada a quien sube el
    archivo. Las dos pantallas comparten esta salida, así que se prueba también
    desde acá: la de Importar sólo la cubre por el lado de QMS."""
    from unittest.mock import patch

    from sqlalchemy.exc import DataError

    login(client, "admin@test.cl")
    fallo = DataError("INSERT ...", {}, Exception("integer out of range"))

    with patch("app.inventario.routes.importar_defontana", side_effect=fallo):
        respuesta = _subir(
            client,
            archivo_defontana=_archivo(CSV_DEFONTANA, "defontana.csv", "cp1252"),
            follow_redirects=True,
        )

    assert respuesta.status_code == 200, "debe responder la página, no un error 500"
    texto = respuesta.get_data(as_text=True)
    assert "No se pudo importar Defontana" in texto
    assert "demasiado grande" in texto   # y dice qué mirar en la planilla


# --- Volver a donde se estaba ---


def test_al_volver_se_conserva_el_filtro_que_se_traia(client, db, empresa, usuario_admin):
    """Sin esto aparecen de golpe los miles de artículos escondidos y hay que
    volver a filtrar para seguir donde se iba."""
    login(client, "admin@test.cl")

    respuesta = _subir(
        client,
        archivo_qms=_archivo(CSV_QMS, "qms.csv"),
        filtro="dif_costo", q="PRODUCTO", vacios="no", f_categoria="CAT-A",
    )

    destino = respuesta.headers["Location"]
    assert "filtro=dif_costo" in destino
    assert "q=PRODUCTO" in destino
    assert "vacios=no" in destino
    assert "f_categoria=CAT-A" in destino


def test_tambien_se_conserva_cuando_la_subida_se_rechaza(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    respuesta = _subir(client, filtro="dif_costo")

    assert "filtro=dif_costo" in respuesta.headers["Location"]
    # Y el panel vuelve abierto: cerrado, el aviso de error queda arriba sin
    # nada visible que lo explique.
    assert "subir=1" in respuesta.headers["Location"]


def test_el_panel_vuelve_abierto_cuando_hubo_error(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    cuerpo = client.get("/inventario/cruce-datos?subir=1").get_data(as_text=True)

    assert "<details class=\"card mb-3\" open>" in cuerpo


# --- La pantalla ---


def test_la_pantalla_ofrece_subir_las_dos_planillas(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    cuerpo = client.get("/inventario/cruce-datos").get_data(as_text=True)

    assert "/inventario/cruce-datos/importar" in cuerpo
    assert 'name="archivo_qms"' in cuerpo
    assert 'name="archivo_defontana"' in cuerpo


def test_quien_solo_mira_no_ve_el_formulario(client, db, empresa, usuario_bodega):
    """El cruce se puede mirar sin permiso de edición; subir planillas no."""
    login(client, "bodega@test.cl")

    cuerpo = client.get("/inventario/cruce-datos").get_data(as_text=True)

    assert 'name="archivo_qms"' not in cuerpo


def test_subir_exige_permiso_de_edicion(client, db, empresa, usuario_bodega):
    login(client, "bodega@test.cl")

    respuesta = _subir(client, archivo_qms=_archivo(CSV_QMS, "qms.csv"))

    assert respuesta.status_code == 403
    assert ItemConteoInventario.query.count() == 0


# --- El rastro de cuándo se subió ---


def test_queda_registrado_cuando_se_subio_cada_planilla(client, db, empresa, usuario_admin):
    """La pantalla muestra la fecha de la última importación de cada sistema:
    si subir desde acá no la dejara, diría "nunca se ha importado" encima de
    datos recién cargados."""
    login(client, "admin@test.cl")

    _subir(
        client,
        archivo_qms=_archivo(CSV_QMS, "qms.csv"),
        archivo_defontana=_archivo(CSV_DEFONTANA, "defontana.csv", "cp1252"),
    )

    cargas = ultimas_importaciones(empresa.id)
    assert cargas["qms"].archivo == "qms.csv"
    assert cargas["defontana"].archivo == "defontana.csv"
    assert cargas["qms"].importado_por_id == usuario_admin.id


# --- Lo que ya hacía Importar sigue igual ---


def test_la_pantalla_de_importar_sigue_funcionando(client, db, empresa, usuario_admin):
    """Las dos pantallas comparten la carga: lo que se arregle en una tiene que
    valer en la otra, y lo que se mueva no puede romper ésta."""
    login(client, "admin@test.cl")

    client.post(
        "/inventario/conteo/importar/qms",
        data={"qms-archivo": _archivo(CSV_QMS, "qms.csv"), "qms-solo_no_contados": "y"},
        content_type="multipart/form-data",
    )

    assert _por_codigo("COD-001").cantidad_qms == 10
    assert ultimas_importaciones(empresa.id)["qms"].archivo == "qms.csv"
