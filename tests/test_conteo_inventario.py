import io

from werkzeug.datastructures import FileStorage

from app.models.conteo_inventario import ItemConteoInventario
from app.utils.importar_conteo import importar_qms, importar_defontana


CSV_QMS = """﻿Sucursal;Linea Negocio;Categoria; Columna1 ; Valor Total Stock CLP ;Stock;Stock Critico;Descripción;Unidad;Código Único;ubicacion_bodega
Casa Matriz;GOMAS;CAT-A;0;0;10;0;PRODUCTO UNO;UN;COD-001;RACK A1
Antofagasta;GOMAS;CAT-A;0;0;5;0;PRODUCTO UNO;UN;COD-001;
Casa Matriz;ACEROS;CAT-B;0;0;7;0;PRODUCTO DOS;UN;COD-002;RACK B2
"""

CSV_DEFONTANA = (
    "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad\r\n"
    '"COD-001";"PRODUCTO UNO";"BODEGACENTRAL";"BODEGA CENTRAL";"12";"UN"\r\n'
    '"COD-001";"PRODUCTO UNO";"BODEGAINSUMOS";"BODEGA INSUMOS";"3";"UN"\r\n'
    '"COD-003";"PRODUCTO TRES";"BODEGACENTRAL";"BODEGA CENTRAL";"8";"UN"\r\n'
)


def _fs(contenido_bytes, nombre):
    return FileStorage(stream=io.BytesIO(contenido_bytes), filename=nombre)


def test_importar_qms_agrupa_por_codigo(db, empresa):
    resultado = importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    assert resultado["total_codigos"] == 2

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.cantidad_qms == 15  # 10 + 5 sumado entre sucursales
    assert item.nombre == "PRODUCTO UNO"
    assert item.linea_negocio == "GOMAS"
    assert item.ubicacion == "RACK A1"


def test_importar_defontana_cruza_con_qms(db, empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    resultado = importar_defontana(_fs(CSV_DEFONTANA.encode("cp1252"), "def.csv"), empresa.id)
    assert resultado["total_codigos"] == 2

    cruzado = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert cruzado.cantidad_qms == 15
    assert cruzado.cantidad_defontana == 15  # 12 + 3 entre bodegas
    assert cruzado.diferencia_sistemas == 0

    solo_qms = ItemConteoInventario.query.filter_by(codigo="COD-002").first()
    assert solo_qms.cantidad_defontana == 0
    assert solo_qms.diferencia_sistemas == 7

    solo_def = ItemConteoInventario.query.filter_by(codigo="COD-003").first()
    assert solo_def.cantidad_qms == 0
    assert solo_def.diferencia_sistemas == -8


def test_diferencia_fisica_se_compara_contra_cada_sistema(db, empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    item = ItemConteoInventario.query.filter_by(codigo="COD-002").first()
    item.cantidad_defontana = 4  # QMS dice 7, Defontana 4

    assert not item.contado
    assert item.diferencia_fisica_qms is None
    assert item.diferencia_fisica_defontana is None

    item.cantidad_fisica = 5
    assert item.contado
    assert item.diferencia_fisica_qms == -2
    assert item.diferencia_fisica_defontana == 1
    assert item.tiene_diferencia

    # los tres cuadran: deja de aparecer como diferencia
    item.cantidad_fisica = 7
    item.cantidad_defontana = 7
    assert item.diferencia_fisica_qms == 0
    assert item.diferencia_fisica_defontana == 0
    assert not item.tiene_diferencia


def test_importacion_no_escala_en_consultas_por_articulo(db, empresa):
    """Con miles de artículos, una consulta por código agota el tiempo contra la base remota."""
    from sqlalchemy import event

    filas = [
        f"Casa Matriz;GOMAS;CAT;0;0;{i};0;PRODUCTO {i};UN;COD-{i:04d};RACK" for i in range(200)
    ]
    csv_grande = CSV_QMS.splitlines()[0] + "\n" + "\n".join(filas) + "\n"

    consultas = []
    motor = db.engine

    def contar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)

    event.listen(motor, "before_cursor_execute", contar)
    try:
        importar_qms(_fs(csv_grande.encode("utf-8"), "qms.csv"), empresa.id)
    finally:
        event.remove(motor, "before_cursor_execute", contar)

    selects = [c for c in consultas if c.strip().upper().startswith("SELECT")]
    assert len(selects) <= 5, f"{len(selects)} SELECT para 200 artículos: debe ser un número fijo"


def test_textos_mas_largos_que_la_columna_se_recortan(db, empresa):
    nombre_largo = "X" * 400
    csv_largo = (
        CSV_QMS.splitlines()[0]
        + "\n"
        + f"Casa Matriz;{'L' * 200};CAT;0;0;5;0;{nombre_largo};UN;{'C' * 120};{'U' * 400}\n"
    )
    importar_qms(_fs(csv_largo.encode("utf-8"), "qms.csv"), empresa.id)

    item = ItemConteoInventario.query.first()
    assert len(item.codigo) <= 80
    assert len(item.nombre) <= 255
    assert len(item.linea_negocio) <= 120
    assert len(item.ubicacion) <= 255


def test_reimportar_no_pierde_conteo_fisico(db, empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    item.cantidad_fisica = 14
    db.session.commit()

    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.cantidad_fisica == 14


# --- QMS ahora también exporta en .xlsx en vez de .csv ---


def _xlsx(encabezados, filas, nombre="datos.xlsx"):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(encabezados)
    for fila in filas:
        ws.append(fila)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return FileStorage(stream=buf, filename=nombre)


def test_importar_qms_desde_xlsx(db, empresa):
    """El formato nuevo de QMS: mismas columnas, pero en Excel en vez de CSV."""
    archivo = _xlsx(
        ["Linea Negocio", "Categoria", "Valor Total Stock CLP", "Stock", "Valor Unitario Stock CLP", "Descripción", "Unidad", "Código Único"],
        [
            ["PRENSAS", "COMPONENTES", 49465752, 3, 16488584, "SET DE PLATOS VULCANIZADORES", "SET", "SVP-3378-R"],
            ["FUSION", "LINNING", 17657305, 9, 1961922.7777777778, "ROLLO DE GOMA LISA", "RL", "CFW-60SB-1050"],
        ],
        "stock_qms.xlsx",
    )
    resultado = importar_qms(archivo, empresa.id)
    assert resultado["total_codigos"] == 2

    item = ItemConteoInventario.query.filter_by(codigo="SVP-3378-R").first()
    assert item.cantidad_qms == 3
    assert item.costo_unitario_qms == 16488584
    assert item.unidad_qms == "SET"
    assert item.categoria == "COMPONENTES"
    assert item.linea_negocio == "PRENSAS"

    # el costo con decimales (Excel guarda floats) se redondea a un entero de pesos
    item2 = ItemConteoInventario.query.filter_by(codigo="CFW-60SB-1050").first()
    assert item2.costo_unitario_qms == 1961923


def test_importar_defontana_desde_xlsx(db, empresa):
    archivo = _xlsx(
        ["CodArticulo", "Descripción Artículo", "Nombre Bodega", "Saldo Stock", "Unidad", "Costo Unitario"],
        [
            ["COD-001", "PRODUCTO UNO", "BODEGA CENTRAL", 15, "UN", 9500],
        ],
        "stock_defontana.xlsx",
    )
    resultado = importar_defontana(archivo, empresa.id)
    assert resultado["total_codigos"] == 1

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.cantidad_defontana == 15
    assert item.costo_unitario_defontana == 9500
    assert item.unidad_defontana == "UN"


def test_plantilla_qms_se_puede_descargar_y_reimportar(client, usuario_admin, empresa, db):
    from tests.conftest import login

    login(client, "admin@test.cl")
    respuesta = client.get("/inventario/conteo/importar/plantilla-qms")
    assert respuesta.status_code == 200
    assert respuesta.headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    archivo = _fs(respuesta.data, "plantilla-qms.xlsx")
    resultado = importar_qms(archivo, empresa.id)
    assert resultado["total_codigos"] == 1
    item = ItemConteoInventario.query.filter_by(codigo="ROP-BCAN-M").first()
    assert item is not None
    assert item.cantidad_qms == 12


def test_plantilla_defontana_se_puede_descargar_y_reimportar(client, usuario_admin, empresa, db):
    from tests.conftest import login

    login(client, "admin@test.cl")
    respuesta = client.get("/inventario/conteo/importar/plantilla-defontana")
    assert respuesta.status_code == 200

    archivo = _fs(respuesta.data, "plantilla-defontana.xlsx")
    resultado = importar_defontana(archivo, empresa.id)
    assert resultado["total_codigos"] == 1
    item = ItemConteoInventario.query.filter_by(codigo="ROP-BCAN-M").first()
    assert item is not None
    assert item.cantidad_defontana == 12


def test_xlsx_sin_extension_reconocible_se_detecta_por_contenido(db, empresa):
    """Si el archivo llega sin extensión .xlsx en el nombre, se detecta por la firma del archivo."""
    archivo = _xlsx(
        ["Código Único", "Descripción", "Unidad", "Stock", "Valor Unitario Stock CLP"],
        [["COD-999", "PRODUCTO ZETA", "UN", 5, 1000]],
        nombre="reporte_sin_extension",
    )
    resultado = importar_qms(archivo, empresa.id)
    assert resultado["total_codigos"] == 1
    assert ItemConteoInventario.query.filter_by(codigo="COD-999").first() is not None


def test_codigos_con_distinto_espaciado_cruzan_como_el_mismo_articulo(db, empresa):
    """QMS exporta 'ROP- BCAN-M', Defontana el mismo artículo como 'ROP-BCAN-M': deben cruzar."""
    csv_qms = (
        "Sucursal;Linea Negocio;Categoria;Valor Total Stock CLP;Stock;Stock Critico;"
        "Descripción;Unidad;Código Único;ubicacion_bodega\n"
        "Casa Matriz;GOMAS;CAT-A;0;10;0;PRODUCTO ESPACIADO;UN;ROP- BCAN-M;RACK A1\n"
    )
    csv_defontana = (
        "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad\r\n"
        '"ROP-BCAN-M";"PRODUCTO ESPACIADO";"BODEGACENTRAL";"BODEGA CENTRAL";"10";"UN"\r\n'
    )

    importar_qms(_fs(csv_qms.encode("utf-8"), "qms.csv"), empresa.id)
    importar_defontana(_fs(csv_defontana.encode("cp1252"), "def.csv"), empresa.id)

    assert ItemConteoInventario.query.count() == 1
    item = ItemConteoInventario.query.first()
    assert item.codigo == "ROP-BCAN-M"
    assert item.cantidad_qms == 10
    assert item.cantidad_defontana == 10
    assert item.diferencia_sistemas == 0


def test_espacios_multiples_tambien_se_colapsan(db, empresa):
    csv_qms = (
        "Sucursal;Linea Negocio;Categoria;Valor Total Stock CLP;Stock;Stock Critico;"
        "Descripción;Unidad;Código Único;ubicacion_bodega\n"
        "Casa Matriz;GOMAS;CAT-A;0;3;0;PRODUCTO;UN;A B   C;RACK A1\n"
    )
    importar_qms(_fs(csv_qms.encode("utf-8"), "qms.csv"), empresa.id)
    item = ItemConteoInventario.query.first()
    assert item.codigo == "ABC"


def test_filas_vacias_del_xlsx_se_ignoran(db, empresa):
    archivo = _xlsx(
        ["Código Único", "Descripción", "Unidad", "Stock", "Valor Unitario Stock CLP"],
        [
            ["COD-001", "PRODUCTO UNO", "UN", 5, 1000],
            [None, None, None, None, None],
        ],
        "qms.xlsx",
    )
    resultado = importar_qms(archivo, empresa.id)
    assert resultado["total_codigos"] == 1


# --- Códigos que son el mismo escrito distinto ---------------------------

CSV_QMS_CON_ESPACIO = """﻿Sucursal;Linea Negocio;Categoria; Columna1 ; Valor Total Stock CLP ;Stock;Stock Critico;Descripción;Unidad;Código Único;ubicacion_bodega
Casa Matriz;GOMAS;CAT-A;0;0;1;0;Pantalla Beltgard;UN;EM-R-Pantalla BG3;BODEGA CENTRAL
"""

CSV_DEFONTANA_SIN_ESPACIO = (
    "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad\r\n"
    '"EM-R-PantallaBG3";"Pantalla Beltgard";"BODEGACENTRAL";"BODEGA CENTRAL";"1";"UN"\r\n'
)


def test_codigo_normalizado_ignora_espacios_acentos_y_mayusculas():
    from app.utils.importar_conteo import codigo_normalizado

    assert codigo_normalizado("EM-R-Pantalla BG3") == codigo_normalizado("EM-R-PantallaBG3")
    assert codigo_normalizado("CÓD-Ñ 1") == codigo_normalizado("cod-n1")
    assert codigo_normalizado(None) == ""


def test_el_mismo_codigo_con_y_sin_espacio_no_crea_dos_articulos(db, empresa):
    importar_qms(_fs(CSV_QMS_CON_ESPACIO.encode("utf-8"), "qms.csv"), empresa.id)
    importar_defontana(_fs(CSV_DEFONTANA_SIN_ESPACIO.encode("utf-8"), "def.csv"), empresa.id)

    items = ItemConteoInventario.query.filter_by(empresa_id=empresa.id).all()
    assert len(items) == 1
    assert items[0].cantidad_qms == 1
    assert items[0].cantidad_defontana == 1


def test_unificar_junta_las_cantidades_y_conserva_el_conteo(db, empresa):
    from app.utils.importar_conteo import grupos_duplicados, unificar_grupo

    sin_contar = ItemConteoInventario(empresa_id=empresa.id, codigo="EM-R-Pantalla BG3",
                                      cantidad_qms=1, cantidad_defontana=1)
    contado = ItemConteoInventario(empresa_id=empresa.id, codigo="EM-R-PantallaBG3",
                                   cantidad_qms=1, cantidad_defontana=1, cantidad_fisica=2,
                                   nombre="Pantalla Beltgard 3.0")
    db.session.add_all([sin_contar, contado])
    db.session.commit()

    grupos = grupos_duplicados(empresa.id)
    assert len(grupos) == 1 and len(grupos[0]) == 2

    unificar_grupo(grupos[0])
    db.session.commit()

    items = ItemConteoInventario.query.filter_by(empresa_id=empresa.id).all()
    assert len(items) == 1
    assert items[0].cantidad_qms == 2
    assert items[0].cantidad_defontana == 2
    assert items[0].cantidad_fisica == 2          # se conservó el conteo de bodega
    assert items[0].nombre == "Pantalla Beltgard 3.0"


# --- Artículos dados de baja en ambos sistemas ---------------------------


def test_un_articulo_que_deja_de_venir_en_una_planilla_no_se_marca_como_ausente(db, empresa):
    from app.utils.importar_conteo import articulos_fuera_de_ambas_planillas

    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    importar_defontana(_fs(CSV_DEFONTANA.encode("utf-8"), "def.csv"), empresa.id)

    # COD-002 solo estaba en QMS; ahora QMS deja de traerlo.
    csv_qms_sin_cod2 = """﻿Sucursal;Linea Negocio;Categoria; Columna1 ; Valor Total Stock CLP ;Stock;Stock Critico;Descripción;Unidad;Código Único;ubicacion_bodega
Casa Matriz;GOMAS;CAT-A;0;0;10;0;PRODUCTO UNO;UN;COD-001;RACK A1
"""
    importar_qms(_fs(csv_qms_sin_cod2.encode("utf-8"), "qms.csv"), empresa.id)

    fuera = articulos_fuera_de_ambas_planillas(empresa.id)
    assert [i.codigo for i in fuera] == ["COD-002"]
    # COD-003 sigue en Defontana, así que no está fuera de ambas.
    assert "COD-003" not in [i.codigo for i in fuera]


def test_importar_solo_qms_no_da_de_baja_lo_que_vive_en_defontana(db, empresa):
    """Las planillas se suben por separado: subir una no puede borrar la otra."""
    from app.utils.importar_conteo import articulos_fuera_de_ambas_planillas

    importar_defontana(_fs(CSV_DEFONTANA.encode("utf-8"), "def.csv"), empresa.id)
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)

    fuera = articulos_fuera_de_ambas_planillas(empresa.id)
    assert fuera == []  # COD-003 solo está en Defontana, pero sigue vigente


def test_eliminar_los_que_no_estan_en_ninguna_planilla(client, usuario_admin, empresa, db):
    from tests.conftest import login
    from app.utils.importar_conteo import articulos_fuera_de_ambas_planillas

    baja = ItemConteoInventario(empresa_id=empresa.id, codigo="VIEJO-001", cantidad_qms=0,
                                cantidad_defontana=0, en_qms=False, en_defontana=False)
    vigente = ItemConteoInventario(empresa_id=empresa.id, codigo="VIVE-001", cantidad_qms=5,
                                   cantidad_defontana=0, en_qms=True, en_defontana=False)
    db.session.add_all([baja, vigente])
    db.session.commit()
    assert len(articulos_fuera_de_ambas_planillas(empresa.id)) == 1

    login(client, "admin@test.cl")
    client.post("/inventario/conteo/duplicados/eliminar-ausentes", follow_redirects=True)

    codigos = [i.codigo for i in ItemConteoInventario.query.filter_by(empresa_id=empresa.id).all()]
    assert codigos == ["VIVE-001"]


def test_la_pantalla_de_depuracion_avisa_si_hay_conteo_en_los_dados_de_baja(client, usuario_admin, empresa, db):
    from tests.conftest import login

    db.session.add(ItemConteoInventario(empresa_id=empresa.id, codigo="VIEJO-002", cantidad_qms=0,
                                        cantidad_defontana=0, cantidad_fisica=7,
                                        en_qms=False, en_defontana=False))
    db.session.commit()

    login(client, "admin@test.cl")
    texto = client.get("/inventario/conteo/duplicados").get_data(as_text=True)
    assert "VIEJO-002" in texto
    assert "conteo físico registrado" in texto


# --- Toma de varios días: refrescar el stock sin alterar lo ya contado ---

# Mismos códigos que CSV_QMS pero con el stock movido: COD-001 pasa de 15 a 2
# y COD-002 de 7 a 99. Simula la exportación del día siguiente.
CSV_QMS_DIA_2 = """﻿Sucursal;Linea Negocio;Categoria; Columna1 ; Valor Total Stock CLP ;Stock;Stock Critico;Descripción;Unidad;Código Único;ubicacion_bodega
Casa Matriz;GOMAS;CAT-A;0;0;2;0;PRODUCTO UNO;UN;COD-001;RACK A1
Casa Matriz;ACEROS;CAT-B;0;0;99;0;PRODUCTO DOS;UN;COD-002;RACK B2
"""

CSV_DEFONTANA_DIA_2 = (
    "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad\r\n"
    '"COD-001";"PRODUCTO UNO";"BODEGACENTRAL";"BODEGA CENTRAL";"1";"UN"\r\n'
    '"COD-003";"PRODUCTO TRES";"BODEGACENTRAL";"BODEGA CENTRAL";"44";"UN"\r\n'
)


def _contar(codigo, cantidad):
    item = ItemConteoInventario.query.filter_by(codigo=codigo).first()
    item.cantidad_fisica = cantidad
    return item


def test_reimportar_qms_no_toca_el_stock_de_lo_ya_contado(db, empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    _contar("COD-001", 15)  # bodega ya contó este y cuadraba
    db.session.commit()

    resultado = importar_qms(_fs(CSV_QMS_DIA_2.encode("utf-8"), "qms.csv"), empresa.id,
                             solo_no_contados=True)

    contado = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert contado.cantidad_qms == 15  # sigue comparándose contra la foto del día del conteo
    assert contado.diferencia_fisica_qms == 0  # no aparece una diferencia inventada

    sin_contar = ItemConteoInventario.query.filter_by(codigo="COD-002").first()
    assert sin_contar.cantidad_qms == 99  # este sí se refresca, que es lo que se busca

    assert resultado["congelados"] == 1
    assert resultado["actualizados"] == 1


def test_reimportar_defontana_no_toca_el_stock_de_lo_ya_contado(db, empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    importar_defontana(_fs(CSV_DEFONTANA.encode("cp1252"), "def.csv"), empresa.id)
    _contar("COD-001", 15)
    db.session.commit()

    resultado = importar_defontana(_fs(CSV_DEFONTANA_DIA_2.encode("cp1252"), "def.csv"), empresa.id,
                                   solo_no_contados=True)

    contado = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert contado.cantidad_defontana == 15
    assert contado.diferencia_fisica_defontana == 0

    otro = ItemConteoInventario.query.filter_by(codigo="COD-003").first()
    assert otro.cantidad_defontana == 44

    assert resultado["congelados"] == 1


def test_sin_la_opcion_se_actualiza_el_stock_de_todos(db, empresa):
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    _contar("COD-001", 15)
    db.session.commit()

    resultado = importar_qms(_fs(CSV_QMS_DIA_2.encode("utf-8"), "qms.csv"), empresa.id,
                             solo_no_contados=False)

    contado = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert contado.cantidad_qms == 2  # se pisa con la cifra nueva
    assert resultado["congelados"] == 0


def test_congelar_el_stock_igual_deja_actualizar_costo_y_datos(db, empresa):
    """Congelar es sólo para la cantidad: el costo y la unidad son datos de
    referencia y deben poder corregirse aunque el artículo ya esté contado."""
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    _contar("COD-001", 15)
    db.session.commit()

    csv_con_costo = """﻿Sucursal;Linea Negocio;Categoria; Valor Unitario ;Stock;Descripción;Unidad;Código Único;ubicacion_bodega
Casa Matriz;GOMAS;CAT-A;8000;2;PRODUCTO UNO CORREGIDO;KG;COD-001;RACK A1
"""
    importar_qms(_fs(csv_con_costo.encode("utf-8"), "qms.csv"), empresa.id, solo_no_contados=True)

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.cantidad_qms == 15  # la cantidad sigue congelada
    assert item.costo_unitario_qms == 8000  # el costo sí se corrigió
    assert item.unidad_qms == "KG"
    assert item.nombre == "PRODUCTO UNO CORREGIDO"


def test_un_articulo_nuevo_entra_aunque_se_congelen_los_contados(db, empresa):
    """Los códigos que aparecen por primera vez no tienen conteo, así que entran normal."""
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    _contar("COD-001", 15)
    db.session.commit()

    csv_nuevo = """﻿Sucursal;Linea Negocio;Categoria;Stock;Descripción;Unidad;Código Único;ubicacion_bodega
Casa Matriz;GOMAS;CAT-A;30;PRODUCTO NUEVO;UN;COD-999;RACK Z9
"""
    resultado = importar_qms(_fs(csv_nuevo.encode("utf-8"), "qms.csv"), empresa.id,
                             solo_no_contados=True)

    assert resultado["creados"] == 1
    nuevo = ItemConteoInventario.query.filter_by(codigo="COD-999").first()
    assert nuevo.cantidad_qms == 30


def test_la_pantalla_de_importar_ofrece_la_opcion_marcada_por_defecto(client, usuario_admin, db):
    from tests.conftest import login

    login(client, "admin@test.cl")
    texto = client.get("/inventario/conteo/importar").get_data(as_text=True)
    assert "solo los artículos que aún no se han contado" in texto
    # Debe venir marcada: es lo que se quiere durante una toma de varios días.
    assert texto.count("checked") >= 2  # una casilla por cada sistema


def test_importar_por_la_ruta_respeta_la_casilla(client, usuario_admin, empresa, db):
    """Prueba de punta a punta: la casilla del formulario llega hasta el importador."""
    from tests.conftest import login

    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    _contar("COD-001", 15)
    db.session.commit()

    login(client, "admin@test.cl")
    respuesta = client.post(
        "/inventario/conteo/importar/qms",
        data={
            "qms-archivo": (io.BytesIO(CSV_QMS_DIA_2.encode("utf-8")), "qms.csv"),
            "qms-solo_no_contados": "y",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "ya contados" in respuesta.get_data(as_text=True)

    contado = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert contado.cantidad_qms == 15


def test_importar_por_la_ruta_sin_la_casilla_actualiza_todo(client, usuario_admin, empresa, db):
    from tests.conftest import login

    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    _contar("COD-001", 15)
    db.session.commit()

    login(client, "admin@test.cl")
    client.post(
        "/inventario/conteo/importar/qms",
        data={"qms-archivo": (io.BytesIO(CSV_QMS_DIA_2.encode("utf-8")), "qms.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    contado = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert contado.cantidad_qms == 2


# --- Que la importación no vuelva a hacer una consulta por artículo ---

def _contar_consultas(fn):
    """Ejecuta fn contando las sentencias que se mandan a la base."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    sentencias = []

    def antes(conn, cur, stmt, params, ctx, many):
        sentencias.append(stmt.split()[0].upper())

    event.listen(Engine, "before_cursor_execute", antes)
    try:
        fn()
    finally:
        event.remove(Engine, "before_cursor_execute", antes)
    return sentencias


def _planilla_qms(n):
    filas = ["Sucursal;Linea Negocio;Categoria;Stock;Descripción;Unidad;Código Único;ubicacion_bodega"]
    for i in range(n):
        filas.append(f"Casa Matriz;GOMAS;CAT;{i};ARTICULO {i};UN;COD-{i:05d};RACK {i%50}")
    return "\n".join(filas).encode("utf-8")


def test_importar_no_hace_una_consulta_por_articulo(db, empresa):
    """Con la base remota de Render cada sentencia es una ida y vuelta por la red.

    Antes se mandaba un UPDATE por artículo y importar 3162 filas tardaba
    minutos. Esta prueba fija el techo para que no vuelva a colarse.
    """
    importar_qms(_fs(_planilla_qms(300), "qms.csv"), empresa.id)  # crea los 300

    sentencias = _contar_consultas(
        lambda: importar_qms(_fs(_planilla_qms(300), "qms.csv"), empresa.id)
    )
    assert len(sentencias) < 30, f"demasiadas consultas: {len(sentencias)}"
    assert ItemConteoInventario.query.filter_by(empresa_id=empresa.id).count() == 300


def test_importar_en_lote_deja_los_mismos_datos_que_antes(db, empresa):
    """Las reglas de 'solo sobrescribe si la planilla trae dato' deben mantenerse."""
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    item.ubicacion = "RACK PROPIO"  # puesto a mano
    db.session.commit()

    # Planilla sin nombre, sin categoría y sin ubicación: no debe borrar nada.
    sin_datos = """﻿Sucursal;Linea Negocio;Categoria;Stock;Descripción;Unidad;Código Único;ubicacion_bodega
Casa Matriz;;;99;;;COD-001;
"""
    importar_qms(_fs(sin_datos.encode("utf-8"), "qms.csv"), empresa.id)

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.cantidad_qms == 99          # el stock sí se actualiza
    assert item.nombre == "PRODUCTO UNO"    # el nombre no se pisa con vacío
    assert item.linea_negocio == "GOMAS"
    assert item.categoria == "CAT-A"
    assert item.ubicacion == "RACK PROPIO"  # la ubicación puesta a mano se respeta


def test_defontana_en_lote_no_pisa_el_nombre_que_ya_existe(db, empresa):
    """En Defontana el nombre sólo se usa si el artículo aún no tiene."""
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    importar_defontana(_fs(CSV_DEFONTANA.encode("cp1252"), "def.csv"), empresa.id)

    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    assert item.nombre == "PRODUCTO UNO"  # el de QMS manda, no lo reemplaza Defontana

    solo_def = ItemConteoInventario.query.filter_by(codigo="COD-003").first()
    assert solo_def.nombre == "PRODUCTO TRES"  # este sí lo puso Defontana


def test_marcar_ausentes_sigue_funcionando_en_lote(db, empresa):
    """Un artículo que deja de venir en la planilla queda marcado como ausente."""
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    assert ItemConteoInventario.query.filter_by(codigo="COD-002").first().en_qms is True

    solo_uno = """﻿Sucursal;Linea Negocio;Categoria;Stock;Descripción;Unidad;Código Único;ubicacion_bodega
Casa Matriz;GOMAS;CAT-A;5;PRODUCTO UNO;UN;COD-001;RACK A1
"""
    importar_qms(_fs(solo_uno.encode("utf-8"), "qms.csv"), empresa.id)

    assert ItemConteoInventario.query.filter_by(codigo="COD-001").first().en_qms is True
    assert ItemConteoInventario.query.filter_by(codigo="COD-002").first().en_qms is False


def test_congelar_el_stock_sigue_funcionando_con_la_carga_en_lote(db, empresa):
    """La protección de lo ya contado no se puede perder al agrupar las escrituras."""
    importar_qms(_fs(CSV_QMS.encode("utf-8"), "qms.csv"), empresa.id)
    item = ItemConteoInventario.query.filter_by(codigo="COD-001").first()
    item.cantidad_fisica = 15
    db.session.commit()

    resultado = importar_qms(_fs(CSV_QMS_DIA_2.encode("utf-8"), "qms.csv"), empresa.id,
                             solo_no_contados=True)

    assert ItemConteoInventario.query.filter_by(codigo="COD-001").first().cantidad_qms == 15
    assert ItemConteoInventario.query.filter_by(codigo="COD-002").first().cantidad_qms == 99
    assert resultado["congelados"] == 1


# --- Códigos iguales que se ven distintos (o peor: que se ven iguales) ---

def test_los_caracteres_invisibles_no_separan_un_codigo(db, empresa):
    """Excel mete caracteres que no se ven y partían el artículo en dos.

    En pantalla los dos códigos se ven idénticos, así que el problema era
    imposible de diagnosticar mirando.
    """
    from app.utils.importar_conteo import codigo_normalizado

    base = "KIT-ST3150213420X8"
    iguales = [
        "KIT-ST 3150213420X8",      # espacio normal
        "KIT-ST\xa03150213420X8",   # espacio duro
        "KIT-ST​3150213420X8", # espacio de ancho cero
        "KIT-ST­3150213420X8", # guion suave
        "KIT-ST﻿3150213420X8", # marca BOM
        "KIT-ST‍3150213420X8", # unión de ancho cero
        "KIT–ST3150213420X8",  # guion largo
        "KIT−ST3150213420X8",  # signo menos
        "'KIT-ST3150213420X8",      # apóstrofe de Excel
        "kit-st3150213420x8",       # minúsculas
        "  KIT-ST3150213420X8  ",   # espacios alrededor
    ]
    for variante in iguales:
        assert codigo_normalizado(variante) == codigo_normalizado(base), repr(variante)


def test_dos_codigos_de_verdad_distintos_no_se_unen(db, empresa):
    from app.utils.importar_conteo import codigo_normalizado

    assert codigo_normalizado("KIT-ST315") != codigo_normalizado("KIT-ST316")
    assert codigo_normalizado("ABC-1") != codigo_normalizado("ABC-2")


def test_importar_cruza_el_codigo_con_caracter_invisible(db, empresa):
    """Lo que importa de verdad: que no cree una fila nueva."""
    qms = """﻿Sucursal;Linea Negocio;Categoria;Stock;Descripción;Unidad;Código Único;ubicacion_bodega
Casa Matriz;GOMAS;CAT;10;KIT ST;UN;KIT-ST3150213420X8;RACK A
"""
    importar_qms(_fs(qms.encode("utf-8"), "qms.csv"), empresa.id)

    # Defontana trae el mismo código con un espacio de ancho cero en medio
    defontana = (
        "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad\r\n"
        '"KIT-ST​3150213420X8";"KIT ST";"BC";"BODEGA CENTRAL";"7";"UN"\r\n'
    )
    importar_defontana(_fs(defontana.encode("cp1252", "ignore"), "def.csv"), empresa.id)

    items = ItemConteoInventario.query.filter_by(empresa_id=empresa.id).all()
    assert len(items) == 1, [i.codigo for i in items]  # una sola fila, no dos
    assert items[0].cantidad_qms == 10
    assert items[0].cantidad_defontana == 7


def test_el_codigo_se_guarda_sin_caracteres_invisibles(db, empresa):
    qms = """﻿Sucursal;Linea Negocio;Categoria;Stock;Descripción;Unidad;Código Único;ubicacion_bodega
Casa Matriz;GOMAS;CAT;10;KIT ST;UN;KIT-ST​315;RACK A
"""
    importar_qms(_fs(qms.encode("utf-8"), "qms.csv"), empresa.id)

    item = ItemConteoInventario.query.filter_by(empresa_id=empresa.id).one()
    assert item.codigo == "KIT-ST315"
    assert "​" not in item.codigo


def test_la_pantalla_de_depuracion_explica_la_diferencia_invisible(client, usuario_admin, empresa, db):
    """Dos códigos que se ven iguales necesitan que la pantalla diga en qué difieren."""
    from tests.conftest import login

    db.session.add_all([
        ItemConteoInventario(empresa_id=empresa.id, codigo="KIT-ST315",
                             cantidad_qms=1, cantidad_defontana=0),
        ItemConteoInventario(empresa_id=empresa.id, codigo="KIT-ST​315",
                             cantidad_qms=0, cantidad_defontana=2),
    ])
    db.session.commit()

    login(client, "admin@test.cl")
    texto = client.get("/inventario/conteo/duplicados").get_data(as_text=True)
    assert "espacio de ancho cero" in texto


def test_unificar_junta_el_par_con_caracter_invisible(client, usuario_admin, empresa, db):
    from tests.conftest import login

    db.session.add_all([
        ItemConteoInventario(empresa_id=empresa.id, codigo="KIT-ST315",
                             cantidad_qms=10, cantidad_defontana=0, cantidad_fisica=9),
        ItemConteoInventario(empresa_id=empresa.id, codigo="KIT-ST​315",
                             cantidad_qms=0, cantidad_defontana=4),
    ])
    db.session.commit()

    login(client, "admin@test.cl")
    client.post("/inventario/conteo/duplicados/unificar",
                data={"clave": "KIT-ST315"}, follow_redirects=True)

    items = ItemConteoInventario.query.filter_by(empresa_id=empresa.id).all()
    assert len(items) == 1
    assert items[0].cantidad_qms == 10
    assert items[0].cantidad_defontana == 4
    assert items[0].cantidad_fisica == 9  # el conteo de bodega se conserva


# --- Valores fuera de rango: reventaban la importación entera con un error 500 ---

def test_un_costo_gigante_no_tumba_la_importacion(db, empresa):
    """El entero normal de PostgreSQL llega a 2.147.483.647.

    Una sola celda por sobre ese valor no se guardaba mal: hacía fallar el
    archivo completo con un error 500, sin cargar nada y sin decir por qué.
    """
    qms = """﻿Sucursal;Linea Negocio;Categoria;Stock;Descripción;Unidad;Código Único;ubicacion_bodega;Valor Unitario
Casa Matriz;GOMAS;CAT;1;ARTICULO CARO;UN;CARO-01;RACK;5000000000
"""
    resultado = importar_qms(_fs(qms.encode("utf-8"), "qms.csv"), empresa.id)
    assert resultado["creados"] == 1

    item = ItemConteoInventario.query.filter_by(codigo="CARO-01").one()
    assert item.costo_unitario_qms == 5_000_000_000
    assert item.costo_unitario_qms > 2_147_483_647  # no cabría en un Integer


def test_un_stock_gigante_tampoco_la_tumba(db, empresa):
    defontana = (
        "CodArticulo;Descripci\xf3n Art\xedculo;CodBodega;Nombre Bodega;Saldo Stock;Unidad\r\n"
        '"MUCHO-01";"ARTICULO";"BC";"BODEGA";"3000000000";"UN"\r\n'
    )
    resultado = importar_defontana(_fs(defontana.encode("cp1252"), "def.csv"), empresa.id)
    assert resultado["creados"] == 1
    assert ItemConteoInventario.query.filter_by(codigo="MUCHO-01").one().cantidad_defontana == 3_000_000_000


def test_las_cantidades_y_costos_son_bigint():
    """Las pruebas corren en SQLite, que no respeta el límite del Integer.

    Sin esta comprobación, volver las columnas a Integer pasaría inadvertido
    aquí y reventaría recién en producción, sobre PostgreSQL, dejando la
    importación diaria sin funcionar.
    """
    from sqlalchemy import BigInteger

    from app.models.conteo_inventario import TomaInventarioDetalle

    campos = ("cantidad_qms", "cantidad_defontana", "cantidad_fisica",
              "costo_unitario_qms", "costo_unitario_defontana")
    for modelo in (ItemConteoInventario, TomaInventarioDetalle):
        for campo in campos:
            tipo = modelo.__table__.columns[campo].type
            assert isinstance(tipo, BigInteger), (
                f"{modelo.__tablename__}.{campo} debería ser BigInteger, es {tipo}"
            )


def test_si_la_importacion_falla_se_avisa_en_vez_de_mostrar_un_error_500(client, usuario_admin, empresa, db):
    """Una página de "Internal Server Error" no le dice nada a quien importa."""
    from unittest.mock import patch

    from sqlalchemy.exc import DataError
    from tests.conftest import login

    login(client, "admin@test.cl")
    planilla = (
        "﻿Sucursal;Linea Negocio;Categoria;Stock;Descripción;Unidad;Código Único;ubicacion_bodega\n"
        "Casa Matriz;GOMAS;CAT;1;ARTICULO;UN;COD-001;RACK\n"
    ).encode("utf-8")

    fallo = DataError("INSERT ...", {}, Exception("integer out of range"))
    with patch("app.inventario.routes.importar_qms", side_effect=fallo):
        respuesta = client.post(
            "/inventario/conteo/importar/qms",
            data={"qms-archivo": (io.BytesIO(planilla), "qms.csv")},
            content_type="multipart/form-data", follow_redirects=True,
        )

    assert respuesta.status_code == 200, "debe responder la página, no un error 500"
    texto = respuesta.get_data(as_text=True)
    assert "No se pudo importar QMS" in texto
    assert "demasiado grande" in texto
