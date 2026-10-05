"""Submódulo Cruce de datos: consistencia de unidad de medida y costo unitario."""

import re

import io

from werkzeug.datastructures import FileStorage

from app.models.conteo_inventario import ItemConteoInventario
from app.utils.importar_conteo import importar_defontana, importar_qms
from tests.conftest import login


CSV_QMS = """﻿Sucursal;Linea Negocio;Categoria; Valor Total Stock CLP ;Stock;Stock Critico;Descripción;Unidad;Código Único;ubicacion_bodega; Valor Unitario CLP
Casa Matriz;GOMAS;CAT-A;100000;10;0;PRODUCTO UNO;UN;COD-001;RACK A1; 10,000
Casa Matriz;ACEROS;CAT-B;70000;7;0;PRODUCTO DOS;RL;COD-002;RACK B2; 10,000
Casa Matriz;GOMAS;CAT-A;30000;3;0;PRODUCTO TRES;UN;COD-003;RACK A2; 10,000
"""

CSV_DEFONTANA = (
    "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad;Costo Unitario\r\n"
    '"COD-001";"PRODUCTO UNO";"BODEGACENTRAL";"BODEGA CENTRAL";"8";"UN";"9.500"\r\n'
    '"COD-002";"PRODUCTO DOS";"BODEGACENTRAL";"BODEGA CENTRAL";"7";"UN";"10.000"\r\n'
)


def _fs(contenido, nombre):
    return FileStorage(stream=io.BytesIO(contenido), filename=nombre)


def _importar(empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    importar_defontana(_fs(CSV_DEFONTANA.encode("cp1252"), "def.csv"), empresa.id)


# --- Clasificación del modelo ---


def test_estado_maestro_clasifica_cada_combinacion(db, empresa):
    _importar(empresa)

    dif_costo = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert dif_costo.estado_maestro == "dif_costo"

    dif_unidad = ItemConteoInventario.query.filter_by(codigo="COD-002").first()  # RL vs UN, mismo costo
    assert dif_unidad.estado_maestro == "dif_unidad"

    sin_costo = ItemConteoInventario.query.filter_by(codigo="COD-003").first()  # solo en QMS
    assert sin_costo.estado_maestro == "ok"  # tiene costo (QMS) y no hay unidad Defontana con qué comparar

    dif_costo.costo_unitario_defontana = None
    assert dif_costo.estado_maestro == "ok"
    dif_costo.costo_unitario_defontana = 1
    dif_costo.unidad_defontana = "RL"
    assert dif_costo.estado_maestro == "ambas"


def test_sin_costo_en_ningun_sistema(db, empresa):
    _importar(empresa)
    item = ItemConteoInventario.query.filter_by(codigo="COD-003").first()
    item.costo_unitario_qms = None
    assert item.estado_maestro == "sin_costo"


def test_desviacion_e_impacto_del_costo(db, empresa):
    _importar(empresa)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()

    # QMS 10.000 vs Defontana 9.500 -> +500, sobre 9.500 es ~5.26%
    assert round(item.desviacion_costo_pct, 2) == round(500 / 9500 * 100, 2)
    assert item.impacto_diferencia_costo == 500 * item.cantidad_qms  # 500 * 10 = 5000


def test_sin_datos_de_ambos_costos_no_hay_desviacion(db, empresa):
    _importar(empresa)
    item = ItemConteoInventario.query.filter_by(codigo="COD-003").first()  # sin costo Defontana
    assert item.desviacion_costo_pct is None
    assert item.impacto_diferencia_costo is None


# --- Vista y filtros ---


def test_la_pagina_lista_y_clasifica_los_articulos(client, empresa, usuario_admin):
    _importar(empresa)
    login(client, "admin@test.cl")

    respuesta = client.get("/inventario/cruce-datos")
    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "Cruce de datos" in cuerpo
    assert "COD-001" in cuerpo
    assert "COD-002" in cuerpo


def test_filtro_diferencia_de_costo(client, empresa, usuario_admin):
    _importar(empresa)
    login(client, "admin@test.cl")

    cuerpo = client.get("/inventario/cruce-datos?filtro=dif_costo").get_data(as_text=True)
    assert "COD-001" in cuerpo
    assert "COD-002" not in cuerpo


def test_filtro_distinta_unidad(client, empresa, usuario_admin):
    _importar(empresa)
    login(client, "admin@test.cl")

    cuerpo = client.get("/inventario/cruce-datos?filtro=dif_unidad").get_data(as_text=True)
    assert "COD-002" in cuerpo
    assert "COD-001" not in cuerpo


def test_filtro_sin_costo_cargado(client, empresa, usuario_admin):
    _importar(empresa)
    login(client, "admin@test.cl")
    item = ItemConteoInventario.query.filter_by(codigo="COD-003").first()
    item.costo_unitario_qms = None
    from app.extensions import db
    db.session.commit()

    cuerpo = client.get("/inventario/cruce-datos?filtro=sin_costo").get_data(as_text=True)
    assert "COD-003" in cuerpo
    assert "COD-001" not in cuerpo


def test_exportacion_excel_incluye_desviacion_e_impacto(client, empresa, usuario_admin):
    import io as _io
    from openpyxl import load_workbook

    _importar(empresa)
    login(client, "admin@test.cl")

    respuesta = client.get("/inventario/cruce-datos.xlsx")
    assert respuesta.status_code == 200
    hoja = load_workbook(_io.BytesIO(respuesta.get_data())).active
    titulos = [hoja.cell(row=4, column=i).value for i in range(1, hoja.max_column + 1)]
    assert "Desviación costo (%)" in titulos
    assert "Impacto en stock QMS" in titulos


def test_no_se_solapa_con_ajuste_inventario(client, empresa, usuario_admin):
    """Ajuste inventario ya no debe mostrar columnas de unidad ni filtros de calidad del maestro."""
    _importar(empresa)
    login(client, "admin@test.cl")

    cuerpo = client.get("/inventario/ajuste").get_data(as_text=True)
    assert "Un. QMS" not in cuerpo
    assert "Diferencia de costo" not in cuerpo
    assert "Distinta unidad" not in cuerpo
    assert "Ir a Cruce de datos" in cuerpo  # enlace cruzado entre ambos submódulos


def test_cruce_de_datos_exige_permiso(client, empresa, usuario_bodega):
    login(client, "bodega@test.cl")
    assert client.get("/inventario/cruce-datos").status_code == 200


def test_cruce_de_datos_exige_sesion(client, empresa):
    respuesta = client.get("/inventario/cruce-datos")
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]


# --- Columna "Falta en" ---


def _item(db, empresa, codigo, en_qms=True, en_defontana=True, **campos):
    item = ItemConteoInventario(
        empresa_id=empresa.id, codigo=codigo, nombre=codigo,
        en_qms=en_qms, en_defontana=en_defontana, **campos,
    )
    db.session.add(item)
    db.session.commit()
    return item


def test_falta_en_dice_el_sistema_que_no_lo_tiene(db, empresa):
    """Un SKU sin costo o sin unidad muchas veces no es un dato mal cargado:
    es que el artículo no existe en uno de los dos sistemas."""
    assert _item(db, empresa, "SOLO-QMS", en_defontana=False).falta_en == "Defontana"
    assert _item(db, empresa, "SOLO-DEFO", en_qms=False).falta_en == "QMS"


def test_si_esta_en_los_dos_no_dice_nada(db, empresa):
    assert _item(db, empresa, "EN-AMBOS").falta_en == ""


def test_si_ya_no_esta_en_ninguno_lo_dice_completo(db, empresa):
    """Dejó de venir en las dos planillas: ya no es stock vigente."""
    item = _item(db, empresa, "DESAPARECIDO", en_qms=False, en_defontana=False)
    assert item.falta_en == "QMS y Defontana"


def test_la_columna_aparece_en_la_pantalla_de_cruce(client, db, empresa, usuario_admin):
    # Con stock: la pantalla entra escondiendo lo que no tiene ni stock ni costo.
    _item(db, empresa, "SOLO-QMS", en_defontana=False, cantidad_qms=5)
    _item(db, empresa, "EN-AMBOS", cantidad_qms=5, cantidad_defontana=5)
    login(client, "admin@test.cl")

    texto = client.get("/inventario/cruce-datos").get_data(as_text=True)
    cuerpo = texto[texto.index("<tbody>"):texto.index("</tbody>")]

    assert "Falta en" in texto
    assert "Defontana</span>" in cuerpo
    # El que está en los dos no agrega ninguna insignia
    fila_ambos = cuerpo[cuerpo.index("EN-AMBOS"):]
    fila_ambos = fila_ambos[:fila_ambos.index("</tr>")]
    assert "bg-warning" not in fila_ambos


def test_la_columna_va_tambien_en_el_excel(client, db, empresa, usuario_admin):
    import io
    from openpyxl import load_workbook

    _item(db, empresa, "SOLO-DEFO", en_qms=False)
    login(client, "admin@test.cl")

    hoja = load_workbook(io.BytesIO(
        client.get("/inventario/cruce-datos.xlsx").get_data())).active
    valores = [c.value for fila in hoja.iter_rows() for c in fila]

    assert "Falta en" in valores
    assert "QMS" in valores


# --- Cruzar sólo lo que aporta algo: con stock, o con costo sin stock ---
#
# Un costo sobre cero unidades valoriza $0 igual, así que o falta cargar el
# stock o el costo quedó de un movimiento viejo. Es lo que hay que revisar, y
# por eso es lo único sin stock que la pantalla conserva.


def _cuerpo(client, consulta=""):
    """Sólo las filas: la píldora del filtro dice "Costo sin stock" igual que la
    insignia, así que mirar la página entera daba por marcada una fila que no lo
    estaba."""
    texto = client.get(f"/inventario/cruce-datos{consulta}").get_data(as_text=True)
    return texto[texto.index("<tbody>"):texto.index("</tbody>")]


def _codigos_visibles(client, consulta=""):
    return set(re.findall(
        r'<td class="text-nowrap fw-semibold">([^<]*)</td>', _cuerpo(client, consulta)
    ))


def test_al_entrar_se_cruzan_los_que_tienen_stock(client, db, empresa, usuario_admin):
    _item(db, empresa, "CON-STOCK-QMS", cantidad_qms=4)
    _item(db, empresa, "CON-STOCK-DEFO", cantidad_defontana=9)
    _item(db, empresa, "SIN-NADA")
    login(client, "admin@test.cl")

    assert _codigos_visibles(client) == {"CON-STOCK-QMS", "CON-STOCK-DEFO"}


def test_un_costo_sin_stock_no_se_esconde_porque_es_lo_que_hay_que_revisar(
    client, db, empresa, usuario_admin
):
    _item(db, empresa, "COSTO-SIN-STOCK", costo_unitario_qms=1500)
    _item(db, empresa, "SIN-NADA")
    login(client, "admin@test.cl")

    assert _codigos_visibles(client) == {"COSTO-SIN-STOCK"}


def test_el_costo_sin_stock_se_marca_en_la_fila(client, db, empresa, usuario_admin):
    _item(db, empresa, "COSTO-SIN-STOCK", costo_unitario_defontana=800)
    login(client, "admin@test.cl")

    assert "Costo sin stock" in _cuerpo(client)


def test_hay_un_filtro_para_verlos_solos(client, db, empresa, usuario_admin):
    _item(db, empresa, "COSTO-SIN-STOCK", costo_unitario_qms=1500)
    _item(db, empresa, "COSTO-CON-STOCK", cantidad_qms=3, costo_unitario_qms=1500)
    login(client, "admin@test.cl")

    assert _codigos_visibles(client, "?filtro=costo_sin_stock") == {"COSTO-SIN-STOCK"}


def test_con_stock_el_costo_no_se_marca(client, db, empresa, usuario_admin):
    _item(db, empresa, "NORMAL", cantidad_qms=3, costo_unitario_qms=1500)
    login(client, "admin@test.cl")

    assert "Costo sin stock" not in _cuerpo(client)


def test_esconderlos_todos_no_dice_que_falta_importar(client, db, empresa, usuario_admin):
    """Decía "aún no hay artículos cruzados" y mandaba a subir archivos que ya
    estaban subidos: el dato estaba, sólo escondido."""
    _item(db, empresa, "SIN-NADA")
    login(client, "admin@test.cl")

    texto = client.get("/inventario/cruce-datos").get_data(as_text=True)

    assert "Aún no hay artículos cruzados" not in texto
    assert "Se están ocultando" in texto


def test_se_pueden_mostrar_y_la_busqueda_los_encuentra(client, db, empresa, usuario_admin):
    _item(db, empresa, "SIN-NADA")
    login(client, "admin@test.cl")

    assert _codigos_visibles(client, "?vacios=si") == {"SIN-NADA"}
    assert _codigos_visibles(client, "?q=SIN-NADA") == {"SIN-NADA"}


def test_el_excel_del_cruce_sigue_bajando_todo(client, db, empresa, usuario_admin):
    import io
    from openpyxl import load_workbook

    _item(db, empresa, "SIN-NADA")
    _item(db, empresa, "COSTO-SIN-STOCK", costo_unitario_qms=1500)
    login(client, "admin@test.cl")

    hoja = load_workbook(io.BytesIO(
        client.get("/inventario/cruce-datos.xlsx").get_data())).active
    valores = [c.value for fila in hoja.iter_rows() for c in fila]

    assert "SIN-NADA" in valores
    assert "Costo sin stock" in valores


# --- Paso a paso para regularizar (Defontana como referencia) ---


def test_plan_paso_a_paso_ordena_lo_que_hay_que_corregir(client, db, empresa, usuario_admin):
    from app.inventario.routes import _pasos_regularizar

    _importar(empresa)
    pasos = _pasos_regularizar(ItemConteoInventario.query.order_by(ItemConteoInventario.codigo).all())
    codigos = {clave: [i.codigo for i, _ in lista] for clave, lista in pasos.items()}

    assert codigos["unidad"] == ["COD-002"]            # RL en QMS, UN en Defontana
    assert codigos["costo"] == ["COD-001"]             # $10.000 en QMS, $9.500 en Defontana
    assert codigos["stock"] == ["COD-001"]             # 10 en QMS, 8 en Defontana
    assert codigos["crear_defontana"] == ["COD-003"]   # solo está en QMS
    acciones = dict((i.codigo, a) for i, a in pasos["costo"])
    assert "a $9.500" in acciones["COD-001"]

    login(client, "admin@test.cl")
    cuerpo = client.get("/inventario/cruce-datos/plan").get_data(as_text=True)
    assert "Paso a paso para regularizar" in cuerpo
    assert "Cambiar en QMS la unidad RL por UN" in cuerpo
    assert "Crear en Defontana" in cuerpo
    assert "/inventario/cruce-datos/plan" in client.get("/inventario/cruce-datos").get_data(as_text=True)


def test_plan_paso_a_paso_en_excel_con_una_hoja_por_paso(client, db, empresa, usuario_admin):
    from openpyxl import load_workbook

    _importar(empresa)
    login(client, "admin@test.cl")
    respuesta = client.get("/inventario/cruce-datos/plan.xlsx")
    assert respuesta.status_code == 200
    libro = load_workbook(io.BytesIO(respuesta.data))
    assert len(libro.sheetnames) == 6
    assert libro.sheetnames[0].startswith("Paso 1")


# --- Los avisos de la fila: cada uno en su propia columna ---
#
# Antes compartían una celda, y un "QMS" suelto no dejaba claro si el artículo
# faltaba ahí o si lo que pasaba era otra cosa. Son dos problemas distintos,
# que se arreglan en lugares distintos y se filtran por separado.


def _avisos_de(client, codigo):
    texto = client.get("/inventario/cruce-datos?filtro=todos").get_data(as_text=True)
    cuerpo = texto[texto.index("<tbody"):texto.index("</tbody>")]
    fila = cuerpo[cuerpo.index(codigo):]
    fila = fila[:fila.index("</tr>")]
    return re.findall(r'<span class="badge[^"]*"[^>]*>([^<]+)</span>', fila), fila


def test_el_aviso_dice_en_que_sistema_falta(client, db, empresa, usuario_admin):
    """Lo que ella pidió: que diga si falta en QMS o si falta en Defontana."""
    _item(db, empresa, "SOLO-QMS", en_defontana=False, cantidad_qms=5)
    _item(db, empresa, "SOLO-DEFO", en_qms=False, cantidad_defontana=5)
    login(client, "admin@test.cl")

    assert _avisos_de(client, "SOLO-QMS")[0] == ["Falta en Defontana"]
    assert _avisos_de(client, "SOLO-DEFO")[0] == ["Falta en QMS"]


def test_cada_aviso_va_en_su_propia_columna(client, db, empresa, usuario_admin):
    """Son dos problemas distintos, que se arreglan en lugares distintos y se
    filtran por separado. Juntos en una celda, un "QMS" suelto no dejaba claro
    cuál de los dos era."""
    _item(db, empresa, "LOS-DOS", en_qms=False, costo_unitario_defontana=5509)
    login(client, "admin@test.cl")

    avisos, fila = _avisos_de(client, "LOS-DOS")

    assert avisos == ["Falta en QMS", "Costo sin stock"]
    # Cada insignia en su propia celda, no las dos en la misma
    celdas_con_aviso = [c for c in fila.split("<td") if "badge" in c]
    assert len(celdas_con_aviso) == 2


def test_lo_que_esta_en_los_dos_sistemas_no_avisa_nada(client, db, empresa, usuario_admin):
    _item(db, empresa, "NORMAL", cantidad_qms=3, cantidad_defontana=3)
    login(client, "admin@test.cl")

    assert _avisos_de(client, "NORMAL")[0] == []


def test_los_dos_avisos_se_distinguen_a_simple_vista(client, db, empresa, usuario_admin):
    """Son problemas distintos y se arreglan en lugares distintos: el mismo
    color los hacía parecer lo mismo."""
    _item(db, empresa, "LOS-DOS", en_qms=False, costo_unitario_defontana=5509)
    login(client, "admin@test.cl")

    _avisos, fila = _avisos_de(client, "LOS-DOS")

    assert "bg-danger" in fila and "bg-warning" in fila


def test_hay_una_columna_para_cada_aviso(client, db, empresa, usuario_admin):
    _item(db, empresa, "CUALQUIERA", cantidad_qms=1, cantidad_defontana=1)
    login(client, "admin@test.cl")

    texto = client.get("/inventario/cruce-datos").get_data(as_text=True)
    encabezado = texto[texto.index("<thead"):texto.index("</thead>")]

    assert "<th>Falta en</th>" in encabezado
    assert "<th>Costo sin stock</th>" in encabezado


def test_las_columnas_de_titulos_filtros_y_datos_son_las_mismas(
    client, db, empresa, usuario_admin
):
    """Agregar una columna y olvidar la fila de filtros corre todo un lugar:
    los filtros quedan bajo el título equivocado y nadie lo nota enseguida."""
    _item(db, empresa, "CUALQUIERA", cantidad_qms=1, cantidad_defontana=1)
    login(client, "admin@test.cl")

    texto = client.get("/inventario/cruce-datos?filtro=todos").get_data(as_text=True)
    encabezado = texto[texto.index("<thead"):texto.index("</thead>")]
    titulos, filtros = encabezado.split('<tr class="filtros-fila">')
    cuerpo = texto[texto.index("<tbody"):texto.index("</tbody>")]
    # Desde el <tr> y no desde el código: si no, el corte parte a mitad de la
    # primera celda y esa no se cuenta.
    hasta = cuerpo.index("CUALQUIERA")
    fila = cuerpo[cuerpo.rindex("<tr", 0, hasta):].split("</tr>")[0]

    cuantos = len(re.findall(r"<th[ >]", titulos))
    assert cuantos == len(re.findall(r"<th[ >]", filtros)), "la fila de filtros quedó corrida"
    assert cuantos == len(re.findall(r"<td[ >]", fila)), "las celdas no calzan con los títulos"

    # Y la fila de "sin resultados" tiene que cruzar la tabla entera
    vacio = client.get("/inventario/cruce-datos?q=NADADENADA").get_data(as_text=True)
    assert f'colspan="{cuantos}"' in vacio


def test_el_excel_sigue_diciendo_el_sistema_a_secas(client, db, empresa, usuario_admin):
    """En el Excel la columna se llama "Falta en" y está sola, así que el
    nombre del sistema basta: repetirlo sería ruido en cada celda."""
    from openpyxl import load_workbook

    _item(db, empresa, "SOLO-DEFO", en_qms=False, cantidad_defontana=5)
    login(client, "admin@test.cl")

    hoja = load_workbook(io.BytesIO(
        client.get("/inventario/cruce-datos.xlsx").get_data())).active
    valores = [c.value for fila in hoja.iter_rows() for c in fila]

    assert "Falta en" in valores   # el título de la columna
    assert "QMS" in valores        # y el valor, sin repetir el título
