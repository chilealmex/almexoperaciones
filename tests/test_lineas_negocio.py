"""El informe de Defontana con la línea de negocio al lado.

El Informe de Inventario dice cuánto hay de cada artículo pero no a qué línea
de negocio pertenece. La línea está en los archivos de Regularización, y en
tres que no siempre dicen lo mismo: el conteo, QMS y el Informe de Artículos.

Lo que pidió la usuaria: una sola línea cuando las tres coinciden —"si son
iguales que solo salga cualquiera, ya que tienen el mismo nombre"— y las tres
cuando no. Y que las filas verdes de subtotal del informe no lleguen al Excel.
"""

import io

import openpyxl
import pytest

from app.models.regularizacion import RegularizacionArchivo
from app.utils.lineas_negocio import (
    AVISO_DISTINTAS,
    AVISO_SIN_LINEA,
    SinArchivos,
    informe_con_lineas,
    leer_informe,
    leer_lineas,
    resolver,
)
from tests.conftest import login


def _xlsx(filas) -> bytes:
    libro = openpyxl.Workbook()
    for fila in filas:
        libro.active.append(fila)
    memoria = io.BytesIO()
    libro.save(memoria)
    return memoria.getvalue()


class _Archivo:
    """Lo mínimo que los lectores esperan de un archivo subido."""

    def __init__(self, contenido, nombre="informe.xlsx"):
        self.filename = nombre
        self.stream = io.BytesIO(contenido)


# El informe tal como lo entrega Defontana: cada artículo seguido de su
# subtotal —la fila verde, que no trae código— y el total general al final.
CABECERA = ["Código Artículo", "Descripción", "Categoría", "Bodega", "Saldo", "Unidad", "Valorización"]
ARTICULO_1 = ["00-FSR-OTH-01", "TUERCAS DE ANCLAJE", "REPUESTOS", "BODEGA CENTRAL", 13, "UN", 72751.25]
ARTICULO_2 = ["ZXDNHX20", "FRESA ANULAR HSS 20mm", "INS DE PRODUCCION", "BODEGA CENTRAL", 1, "UN", 29239]

INFORME_CON_SUBTOTALES = _xlsx([
    CABECERA,
    ARTICULO_1,
    ["", "Total Artículo 00-FSR-OTH-01:", "", "", 13, "UN", 72751.25],
    ARTICULO_2,
    ["", "Total Artículo ZXDNHX20:", "", "", 1, "UN", 29239],
    ["", "TOTAL GENERAL:", "", "", 14, "", 101990.25],
])

INFORME_LIMPIO = _xlsx([CABECERA, ARTICULO_1, ARTICULO_2])


# Los tres archivos de Regularización, cada uno con la columna como la escribe
# su sistema: con tilde, sin tilde y con otro nombre de código.
CONTEO = _xlsx([
    ["Código", "Descripción", "Línea de negocio"],
    ["00-FSR-OTH-01", "TUERCAS", "REPUESTOS"],
    ["ZXDNHX20", "FRESA", "INS DE PRODUCCION"],
])
QMS = _xlsx([
    ["Código Único", "Descripción", "Linea Negocio"],
    ["00-FSR-OTH-01", "TUERCAS", "Repuestos"],
    ["ZXDNHX20", "FRESA", "LAGGING"],
])
ARTICULOS = _xlsx([
    ["Código Artículo", "Descripción", "Línea de Negocio"],
    ["00-FSR-OTH-01", "TUERCAS", "REPUESTOS"],
    ["ZXDNHX20", "FRESA", "INS DE PRODUCCION"],
])

TRES_ARCHIVOS = {
    "conteo": ("conteo.xlsx", CONTEO),
    "qms": ("qms.xlsx", QMS),
    "articulos": ("articulos.xlsx", ARTICULOS),
}


# ---------- Los subtotales ----------

def test_las_filas_de_subtotal_no_llegan_al_informe():
    """Las verdes: "Total Artículo …" y "TOTAL GENERAL". No son artículos."""
    informe = leer_informe(_Archivo(INFORME_CON_SUBTOTALES))

    assert informe["subtotales"] == 3
    assert [f["Código Artículo"] for f in informe["filas"]] == ["00-FSR-OTH-01", "ZXDNHX20"]


def test_el_informe_sin_subtotales_se_lee_igual():
    """Defontana lo entrega de las dos formas y las dos tienen que servir."""
    informe = leer_informe(_Archivo(INFORME_LIMPIO))

    assert informe["subtotales"] == 0
    assert len(informe["filas"]) == 2


def test_las_columnas_del_informe_se_entregan_como_vinieron():
    # El informe se devuelve con las columnas de Defontana y la nueva al final:
    # si se reordenaran, dejaría de ser el mismo archivo con una columna más.
    informe = leer_informe(_Archivo(INFORME_LIMPIO))

    assert informe["encabezados"] == CABECERA


def test_un_archivo_que_no_es_el_informe_lo_dice():
    otro = _xlsx([["Fecha", "Glosa", "Monto"], ["01/01/2026", "algo", 1000]])

    with pytest.raises(ValueError, match="Código Artículo"):
        leer_informe(_Archivo(otro))


def test_un_informe_con_puros_totales_no_pasa_por_vacio():
    # Sin esto se bajaría un Excel con cero filas y sin decir por qué.
    solo_totales = _xlsx([CABECERA, ["", "TOTAL GENERAL:", "", "", 14, "", 101990.25]])

    with pytest.raises(ValueError, match="sólo encontré filas de totales"):
        leer_informe(_Archivo(solo_totales))


# ---------- Qué línea sale ----------

def test_cuando_las_tres_coinciden_sale_una_sola():
    """Lo que pidió: "si son iguales que solo salga cualquiera"."""
    linea, aviso = resolver({"Conteo": "REPUESTOS", "QMS": "REPUESTOS", "Defontana": "REPUESTOS"})

    assert linea == "REPUESTOS"
    assert aviso == ""


def test_la_misma_linea_escrita_distinto_sigue_siendo_la_misma():
    # Cada sistema la escribe a su manera. Comparándolas tal cual, casi todas
    # las filas saldrían marcadas como distintas y el aviso no serviría.
    linea, aviso = resolver({"Conteo": "INS DE PRODUCCION", "QMS": "Ins de Producción"})

    assert aviso == ""
    assert linea == "INS DE PRODUCCION"


def test_cuando_no_coinciden_salen_las_tres_con_su_origen():
    linea, aviso = resolver({"Conteo": "REPUESTOS", "QMS": "LAGGING", "Defontana": "REPUESTOS"})

    assert linea == "Conteo: REPUESTOS · QMS: LAGGING · Defontana: REPUESTOS"
    assert aviso == AVISO_DISTINTAS


def test_la_fuente_que_no_conoce_el_articulo_no_es_un_desacuerdo():
    # No saber es distinto de contradecir: si QMS no tiene el artículo, que las
    # otras dos coincidan es acuerdo, no conflicto.
    linea, aviso = resolver({"Conteo": "REPUESTOS", "Defontana": "REPUESTOS"})

    assert (linea, aviso) == ("REPUESTOS", "")


def test_el_articulo_que_no_esta_en_ningun_archivo_lo_dice():
    assert resolver(None) == ("", AVISO_SIN_LINEA)
    assert resolver({}) == ("", AVISO_SIN_LINEA)


# ---------- Leer los archivos de Regularización ----------

def test_se_lee_la_columna_de_linea_aunque_cada_sistema_la_escriba_distinto():
    """"Línea de negocio", "Linea Negocio" y "Línea de Negocio" son la misma."""
    lineas = leer_lineas(TRES_ARCHIVOS)

    assert lineas["00-FSR-OTH-01"] == {"Conteo": "REPUESTOS", "QMS": "Repuestos", "Defontana": "REPUESTOS"}
    assert lineas["ZXDNHX20"]["QMS"] == "LAGGING"


def test_con_un_archivo_solo_se_cruza_con_uno():
    lineas = leer_lineas({"qms": ("qms.xlsx", QMS)})

    assert lineas["ZXDNHX20"] == {"QMS": "LAGGING"}


def test_sin_ningun_archivo_con_linea_se_avisa():
    with pytest.raises(SinArchivos, match="Regularización"):
        leer_lineas({})


def test_el_codigo_escrito_distinto_igual_cruza():
    # QMS exporta " ZXDNHX 20" y Defontana "ZXDNHX20": es el mismo artículo.
    qms = _xlsx([["Código Único", "Descripción", "Linea Negocio"], [" ZXDNHX 20", "FRESA", "LAGGING"]])

    lineas = leer_lineas({"qms": ("qms.xlsx", qms)})

    assert lineas["ZXDNHX20"] == {"QMS": "LAGGING"}


# ---------- El informe armado ----------

def test_el_informe_queda_con_la_linea_al_final_y_el_resumen_cuadra():
    informe = leer_informe(_Archivo(INFORME_CON_SUBTOTALES))

    resultado = informe_con_lineas(informe, leer_lineas(TRES_ARCHIVOS))

    # Una sola columna al final, no dos: el informe de Defontana más la línea.
    assert resultado["encabezados"] == CABECERA + ["Línea de negocio"]
    # El primero: las tres dicen REPUESTOS, así que sale una sola.
    assert resultado["filas"][0][-1] == "REPUESTOS"
    # El segundo: QMS dice otra cosa, así que salen las tres en esa misma celda.
    assert resultado["filas"][1][-1] == (
        "Conteo: INS DE PRODUCCION · QMS: LAGGING · Defontana: INS DE PRODUCCION"
    )
    assert resultado["resumen"] == {
        "fuentes": ["Conteo", "QMS", "Defontana"],
        "articulos": 2, "subtotales": 3, "con_linea": 2, "sin_linea": 0, "distintas": 1,
    }


def test_el_resumen_nombra_las_fuentes_que_aportaron_y_no_las_cargadas():
    """Un archivo cargado que no se puede leer no es una fuente de nada.

    Decir que se usó haría creer que su línea se tomó en cuenta, y la columna
    saldría igual aunque ese archivo no exista.
    """
    informe = leer_informe(_Archivo(INFORME_LIMPIO))
    ilegible = {"conteo": ("conteo.xlsx", CONTEO), "qms": ("qms.xlsx", b"esto no es una planilla")}

    resultado = informe_con_lineas(informe, leer_lineas(ilegible))

    assert resultado["resumen"]["fuentes"] == ["Conteo"]


def test_el_articulo_que_no_esta_en_regularizacion_queda_marcado():
    informe = leer_informe(_Archivo(_xlsx([CABECERA, ARTICULO_1, ["NUEVO-1", "RECIEN COMPRADO",
                                                                 "REPUESTOS", "BODEGA CENTRAL", 2, "UN", 100]])))

    resultado = informe_con_lineas(informe, leer_lineas(TRES_ARCHIVOS))

    assert resultado["filas"][1][-1] == ""
    assert resultado["resumen"]["sin_linea"] == 1


# ---------- La pantalla ----------

def _con_archivos(db, empresa, claves=("conteo", "qms", "articulos")):
    for clave in claves:
        nombre, contenido = TRES_ARCHIVOS[clave]
        db.session.add(RegularizacionArchivo(empresa_id=empresa.id, clave=clave,
                                             nombre=nombre, contenido=contenido))
    db.session.commit()


def _subir(client, contenido=INFORME_CON_SUBTOTALES, nombre="informe.xlsx"):
    return client.post(
        "/inventario/lineas-negocio",
        data={"archivo": (io.BytesIO(contenido), nombre)},
        content_type="multipart/form-data", follow_redirects=True,
    )


def test_la_pantalla_dice_que_archivos_hay_cargados(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    _con_archivos(db, empresa, claves=("conteo",))

    cuerpo = client.get("/inventario/lineas-negocio").get_data(as_text=True)

    assert "Conteo" in cuerpo and "QMS" in cuerpo
    assert "no está cargado" in cuerpo      # QMS y Defontana
    assert "cargado" in cuerpo              # el conteo


def test_subir_el_informe_baja_el_excel_con_la_columna(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    _con_archivos(db, empresa)

    respuesta = _subir(client)

    assert respuesta.status_code == 200
    assert "spreadsheetml" in respuesta.headers["Content-Type"]
    libro = openpyxl.load_workbook(io.BytesIO(respuesta.data))
    assert libro.sheetnames == ["Inventario con línea", "Resumen"]
    hoja = libro["Inventario con línea"]
    titulos = [c.value for c in hoja[4]]
    assert titulos == CABECERA + ["Línea de negocio"]
    # Y los subtotales no llegaron: dos artículos, no cinco filas.
    codigos = [hoja.cell(row=f, column=1).value for f in (5, 6)]
    assert codigos == ["00-FSR-OTH-01", "ZXDNHX20"]
    assert hoja.cell(row=7, column=1).value != "ZXDNHX20"


def test_el_resumen_dice_cuantos_subtotales_se_sacaron(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    _con_archivos(db, empresa)

    respuesta = _subir(client)

    hoja = openpyxl.load_workbook(io.BytesIO(respuesta.data))["Resumen"]
    dicho = {hoja.cell(row=f, column=1).value: hoja.cell(row=f, column=2).value
             for f in range(5, 11)}
    assert dicho["Filas de subtotal que se sacaron"] == 3
    assert dicho["Artículos en el informe"] == 2
    assert dicho["Con las fuentes en desacuerdo"] == 1


def test_sin_archivos_de_regularizacion_no_se_arma_nada(client, db, empresa, usuario_admin):
    # Se bajaría un informe con la columna nueva vacía en todas las filas, que
    # es peor que no bajarlo: parece que ningún artículo tiene línea.
    login(client, "admin@test.cl")

    respuesta = _subir(client)

    cuerpo = respuesta.get_data(as_text=True)
    assert "No hay archivos de Regularización cargados" in cuerpo
    assert "spreadsheetml" not in respuesta.headers["Content-Type"]


def test_un_archivo_que_no_es_el_informe_avisa_en_pantalla(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    _con_archivos(db, empresa)

    respuesta = _subir(client, contenido=_xlsx([["Fecha", "Glosa", "Monto"], ["01/01/2026", "x", 1]]))

    assert "Código Artículo" in respuesta.get_data(as_text=True)


def test_el_submodulo_esta_en_el_menu(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    cuerpo = client.get("/inventario/lineas-negocio").get_data(as_text=True)

    assert "/inventario/lineas-negocio" in cuerpo
    assert "Línea de negocio" in cuerpo
