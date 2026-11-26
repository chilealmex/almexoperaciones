"""El F29 ya presentado, leído de su PDF y puesto al lado de la propuesta.

El SII entrega el formulario como PDF y adentro está lo declarado, código por
código. Leerlo permite comparar, mes a mes, lo que se declaró con lo que dice
la contabilidad.

Las líneas de estas pruebas son las del F29 de septiembre de 2026 (folio
9383590556).
"""

import io

import pytest

from app.models.contabilidad import F29Declarado
from app.utils.conciliacion_sii import ArchivoInvalido
from app.utils.f29 import CODIGOS_INFORMATIVOS, GLOSAS, comparar_con_declarado
from app.utils.f29_pdf import leer_f29_pdf
from tests.conftest import login

LEIBLES = set(GLOSAS) | set(CODIGOS_INFORMATIVOS)


def _pdf(lineas) -> io.BytesIO:
    """Un PDF con texto de verdad, para leerlo como se lee el del SII."""
    texto = "".join(
        f"({linea.replace('(', '').replace(')', '')}) Tj 0 -14 Td\n" for linea in lineas
    )
    contenido = f"BT /F1 10 Tf 20 760 Td\n{texto}ET".encode("latin-1", "replace")

    objetos = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>",
        b"<</Length %d>>stream\n%s\nendstream" % (len(contenido), contenido),
    ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for numero, cuerpo in enumerate(objetos, 1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % numero + cuerpo + b"\nendobj\n"
    inicio_tabla = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for posicion in posiciones:
        salida += b"%010d 00000 n \n" % posicion
    salida += b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objetos) + 1, inicio_tabla,
    )
    return io.BytesIO(bytes(salida))


# Como viene el de septiembre, con sus dos columnas una tras otra y la fila de
# títulos que trae varios números sueltos.
SEPTIEMBRE = [
    "DECLARACION MENSUAL Y PAGO",
    "SIMULTANEO DE IMPUESTOS",
    "FORMULARIO 29",
    "FOLIO [07] 9383590556",
    "RUT [03] 99.578.050-K",
    "PERIODO [15] 202609",
    "Codigo Glosa Valor",
    "503 CANTIDAD FACTURAS EMITIDAS 29",
    "509 CANT. DCTOS. NOTAS DE CREDITOS EMITIDAS 1",
    "511 CRED. IVA POR DCTOS. ELECTRONICOS 9.140.232",
    "519 CANT. DE DCTOS. FACT. RECIB. DEL GIRO 113",
    "527 CANT. NOTAS DE CREDITO RECIBIDAS 1",
    "534 CANT. FORM. PAGO IMP. DEL GIRO 3",
    "048 RET. IMP. UNICO TRAB. ART. 74 N 1 LIR 2.370.462",
    "151 RETENCION TASA LEY 21.133 SOBRE RENTAS 405.548",
    "502 DEBITOS FACTURAS EMITIDAS 95.961.778",
    "510 DEBITOS NOTAS DE CREDITOS EMITIDAS 159.600",
    "538 TOTAL DEBITOS 95.802.178",
    "520 CREDITO REC. Y REINT./FACT. DEL GIRO 9.167.806",
    "528 CREDITO RECUP. Y REINT NOTAS DE CRED 27.574",
    "535 CRED, RECUP. Y REINT. PAGO IMP. DEL GIRO 19.203.138",
    "537 TOTAL CREDITOS 28.343.370",
    "089 IMP. DETERM. IVA 67.458.808",
    "062 PPM NETO DETERMINADO 5.042.220",
    "595 SUB TOTAL IMP. DETERMINADO ANVERSO 75.277.038",
    "547 TOTAL DETERMINADO 75.277.038",
    "931 Monto Interes 932 Monto Multa 60 Condonacion",
    "TOTAL A PAGAR DENTRO DEL PLAZO LEGAL 91 75.277.038 +",
]


# ---------- Leer el PDF ----------

def test_se_lee_el_periodo_el_folio_y_los_codigos():
    declarado = leer_f29_pdf(_pdf(SEPTIEMBRE), LEIBLES)

    assert declarado["mes"] == "2026-09"
    assert declarado["folio"] == "9383590556"
    assert declarado["codigos"]["502"] == 95961778
    assert declarado["codigos"]["520"] == 9167806
    assert declarado["codigos"]["062"] == 5042220


def test_el_total_a_pagar_lleva_el_codigo_despues_de_la_glosa():
    # En el cuerpo del formulario el código va adelante, pero abajo, en los
    # totales, va después: "TOTAL A PAGAR ... 91 75.277.038 +".
    assert leer_f29_pdf(_pdf(SEPTIEMBRE), LEIBLES)["codigos"]["091"] == 75277038


def test_una_fila_de_titulos_no_se_lee_como_una_declaracion():
    # "931 Monto Interes 932 Monto Multa 60 Condonacion" empieza con un código
    # y lleva números adentro, pero termina en palabra: no es una línea
    # declarada y no se lee como tal.
    codigos = leer_f29_pdf(_pdf(SEPTIEMBRE), LEIBLES)["codigos"]

    assert "931" not in codigos
    assert codigos.get("060") is None


def test_solo_se_leen_los_codigos_que_se_saben_leer():
    # Una línea con forma de declaración pero con un código que no está en la
    # lista no se lee: inventar un código es peor que no mostrarlo, porque
    # entraría a la comparación como si fuera declarado.
    con_desconocido = SEPTIEMBRE + ["777 UN CODIGO QUE NO CONOCEMOS 123.456"]

    codigos = leer_f29_pdf(_pdf(con_desconocido), LEIBLES)["codigos"]

    assert "777" not in codigos
    # Y lo que sí se sabe leer sigue leyéndose
    assert codigos["502"] == 95961778


def test_un_pdf_sin_texto_lo_dice(client):
    # El caso real: un F29 reimpreso, donde los números quedan dibujados como
    # trazos y no hay texto que leer.
    with pytest.raises(ArchivoInvalido) as error:
        leer_f29_pdf(_pdf([]), LEIBLES)

    assert "no tiene texto" in str(error.value)


def test_un_pdf_que_no_es_un_f29_lo_dice():
    with pytest.raises(ArchivoInvalido) as error:
        leer_f29_pdf(_pdf(["UNA BOLETA CUALQUIERA", "503 ALGO 29"]), LEIBLES)

    assert "Formulario 29" in str(error.value)


def test_un_f29_sin_periodo_lo_dice():
    sin_periodo = [linea for linea in SEPTIEMBRE if not linea.startswith("PERIODO")]

    with pytest.raises(ArchivoInvalido) as error:
        leer_f29_pdf(_pdf(sin_periodo), LEIBLES)

    assert "período" in str(error.value)


# ---------- Comparar ----------

def _lineas(**valores):
    return [
        {"codigo": codigo, "glosa": GLOSAS[codigo], "valor": valor,
         "de": "", "clase": "monto", "detalle": []}
        for codigo, valor in valores.items()
    ]


def test_lo_que_calza_y_lo_que_no():
    comparacion = comparar_con_declarado(
        _lineas(**{"502": 95961778, "520": 9000000}),
        {"502": 95961778, "520": 9167806},
    )

    assert comparacion["calzan"] == 1
    assert comparacion["distintos"] == 1
    distinto = next(f for f in comparacion["filas"] if f["codigo"] == "520")
    assert distinto["diferencia"] == 9000000 - 9167806


def test_un_peso_de_redondeo_no_es_una_diferencia():
    # El IVA se redondea documento por documento: la suma de las facturas
    # puede quedar a un peso de lo que informa el SII.
    comparacion = comparar_con_declarado(_lineas(**{"520": 9167807}), {"520": 9167806})

    assert comparacion["distintos"] == 0
    assert comparacion["filas"][0]["estado"] == "calza"


def test_el_codigo_que_no_esta_en_el_formulario_queda_dicho():
    comparacion = comparar_con_declarado(_lineas(**{"502": 100}), {})

    assert comparacion["filas"][0]["estado"] == "no_declarado"
    assert comparacion["filas"][0]["declarado"] is None


def test_lo_declarado_que_la_propuesta_no_calcula_queda_aparte():
    # La base imponible del PPM o el IVA de documentos electrónicos: están en
    # el formulario y no salen de estas cuentas. Se muestran sin comparar en
    # vez de esconderlos.
    comparacion = comparar_con_declarado(
        _lineas(**{"502": 100}), {"502": 100, "563": 504221989},
    )

    assert [c["codigo"] for c in comparacion["sin_comparar"]] == ["563"]
    assert comparacion["sin_comparar"][0]["declarado"] == 504221989


# ---------- La pantalla ----------

def _subir(client, lineas=None, nombre="f29.pdf"):
    return client.post(
        "/contabilidad/f29/declarado",
        data={"f29": [(_pdf(SEPTIEMBRE if lineas is None else lineas), nombre)]},
        content_type="multipart/form-data", follow_redirects=True,
    )


def test_subir_el_f29_lo_guarda_en_su_mes(client, db, empresa, usuario_admin):
    # El mes lo dice el propio formulario: no hay que elegirlo.
    login(client, "admin@test.cl")

    _subir(client)

    declarado = F29Declarado.query.one()
    assert declarado.mes == "2026-09"
    assert declarado.folio == "9383590556"
    assert declarado.por_codigo["537"] == 28343370


def test_volver_a_subirlo_reemplaza_al_anterior(client, db, empresa, usuario_admin):
    # Que es lo que pasa cuando se rectifica el mes.
    login(client, "admin@test.cl")
    _subir(client)
    rectificado = [
        linea.replace("95.961.778", "90.000.000") for linea in SEPTIEMBRE
    ]
    _subir(client, rectificado)

    declarado = F29Declarado.query.one()
    assert declarado.por_codigo["502"] == 90000000
    assert len(declarado.codigos) == len(leer_f29_pdf(_pdf(SEPTIEMBRE), LEIBLES)["codigos"])


def test_un_pdf_que_no_se_puede_leer_se_dice_con_su_nombre(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    r = _subir(client, ["UNA BOLETA CUALQUIERA"], nombre="lo_que_sea.pdf")

    cuerpo = r.get_data(as_text=True)
    assert "lo_que_sea.pdf" in cuerpo
    assert F29Declarado.query.count() == 0


def test_quitar_el_f29_del_mes(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    _subir(client)
    declarado = F29Declarado.query.one()

    client.post(
        f"/contabilidad/f29/declarado/{declarado.id}/eliminar", follow_redirects=True
    )

    assert F29Declarado.query.count() == 0


def test_la_pantalla_pone_lado_a_lado_la_propuesta_y_lo_declarado(
    client, db, empresa, usuario_admin
):
    from tests.test_f29 import ANALISIS, _informe

    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/f29/cargar",
        data={"mayor": [(_informe(), "informe.xlsx")]},
        content_type="multipart/form-data", follow_redirects=True,
    )
    # El mismo mes del informe de ejemplo, con sus débitos declarados igual.
    declarado = [
        "FORMULARIO 29", "FOLIO [07] 1234", "PERIODO [15] 202609",
        "502 DEBITOS FACTURAS EMITIDAS 95.961.778",
        "520 CREDITO REC. Y REINT./FACT. DEL GIRO 1.000.000",
    ]
    _subir(client, declarado)

    cuerpo = client.get(
        "/contabilidad/f29?mes=2026-09&vista=comparacion"
    ).get_data(as_text=True)

    assert "códigos calzan" in cuerpo
    # El 520 declarado no es el que sale de las cuentas: se marca y se dice de
    # qué está hecho, para poder ir a buscar la diferencia.
    assert "De qué está hecho" in cuerpo
    assert "Cpra_FCA" in cuerpo
    assert ANALISIS[0][3] == "Cpra_FCA"


# ---------- Las pestañas ----------
#
# La pantalla tenía todo apilado: los dos cargadores, las cuentas, la
# propuesta y la comparación, uno debajo del otro. Separada en pestañas, cada
# cosa está donde se la busca.

def test_sin_nada_cargado_se_entra_por_los_archivos(client, db, empresa, usuario_admin):
    # No hay nada que proponer todavía: lo primero es subir los archivos.
    login(client, "admin@test.cl")

    cuerpo = client.get("/contabilidad/f29").get_data(as_text=True)

    assert "Las cuentas de la contabilidad" in cuerpo
    assert "El F29 que presentaste" in cuerpo


def test_con_cuentas_cargadas_se_entra_por_la_propuesta(client, db, empresa, usuario_admin):
    from tests.test_f29 import _informe

    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/f29/cargar",
        data={"mayor": [(_informe(), "informe.xlsx")]},
        content_type="multipart/form-data", follow_redirects=True,
    )

    cuerpo = client.get("/contabilidad/f29").get_data(as_text=True)

    assert "Lo que habría que declarar" in cuerpo


def test_sin_el_f29_del_mes_la_comparacion_dice_que_falta(client, db, empresa, usuario_admin):
    # Era lo que no se entendía: la comparación no aparecía por ninguna parte
    # y no había cómo saber que faltaba subir el PDF.
    from tests.test_f29 import _informe

    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/f29/cargar",
        data={"mayor": [(_informe(), "informe.xlsx")]},
        content_type="multipart/form-data", follow_redirects=True,
    )

    cuerpo = client.get(
        "/contabilidad/f29?mes=2026-09&vista=comparacion"
    ).get_data(as_text=True)

    assert "Todavía no subes el F29" in cuerpo


def test_el_periodo_se_mantiene_al_cambiar_de_pestana(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    _subir(client)

    cuerpo = client.get(
        "/contabilidad/f29?mes=2026-09&vista=detalle"
    ).get_data(as_text=True)

    assert 'href="/contabilidad/f29?mes=2026-09&amp;vista=propuesta"' in cuerpo


def test_los_periodos_se_agrupan_por_año_del_mas_nuevo_al_mas_viejo(db):
    from app.contabilidad.routes import _meses_por_anio

    agrupados = _meses_por_anio(["2025-01", "2026-10", "2024-07", "2026-09"])

    assert [anio for anio, _meses in agrupados] == ["2026", "2025", "2024"]
    assert agrupados[0][1] == [("2026-10", "Octubre"), ("2026-09", "Septiembre")]


def test_la_pantalla_lista_los_años_en_el_selector(client, db, empresa, usuario_admin):
    # No sólo un año: los períodos se van acumulando y tienen que verse todos,
    # cada uno bajo el suyo.
    login(client, "admin@test.cl")
    _subir(client)
    _subir(client, [linea.replace("202609", "202512") for linea in SEPTIEMBRE])

    cuerpo = client.get("/contabilidad/f29").get_data(as_text=True)

    assert '<optgroup label="2026">' in cuerpo
    assert '<optgroup label="2025">' in cuerpo
    assert "Septiembre 2026" in cuerpo
    assert "Diciembre 2025" in cuerpo


def test_una_pestaña_que_no_existe_cae_en_una_que_si(client, db, empresa, usuario_admin):
    # Un enlace viejo o una dirección escrita a mano no pueden dejar la
    # pantalla en blanco.
    from tests.test_f29 import _informe

    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/f29/cargar",
        data={"mayor": [(_informe(), "informe.xlsx")]},
        content_type="multipart/form-data", follow_redirects=True,
    )

    cuerpo = client.get("/contabilidad/f29?vista=loquesea").get_data(as_text=True)

    assert "Lo que habría que declarar" in cuerpo


def test_la_comparacion_muestra_la_cuenta_contable(client, db, empresa, usuario_admin):
    # Para ir a buscar la diferencia hay que saber en qué cuenta mirar.
    from tests.test_f29 import _informe

    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/f29/cargar",
        data={"mayor": [(_informe(), "informe.xlsx")]},
        content_type="multipart/form-data", follow_redirects=True,
    )
    _subir(client, ["FORMULARIO 29", "PERIODO [15] 202609",
                    "502 DEBITOS FACTURAS EMITIDAS 95.961.778"])

    cuerpo = client.get(
        "/contabilidad/f29?mes=2026-09&vista=comparacion"
    ).get_data(as_text=True)

    assert "Cuenta contable" in cuerpo
    assert "2120301001 IVA DEBITO FISCAL" in cuerpo


def test_un_documento_de_diferencia_no_es_redondeo():
    # El peso de redondeo se perdona en la plata; en las cantidades no, porque
    # un documento de diferencia es un documento que falta o que sobra.
    lineas = [
        {"codigo": "503", "glosa": GLOSAS["503"], "valor": 56,
         "de": "", "clase": "cantidad", "detalle": []},
        {"codigo": "502", "glosa": GLOSAS["502"], "valor": 95961778,
         "de": "", "clase": "monto", "detalle": []},
    ]

    comparacion = comparar_con_declarado(lineas, {"503": 55, "502": 95961779})

    por_codigo = {f["codigo"]: f for f in comparacion["filas"]}
    assert por_codigo["503"]["estado"] == "distinto"
    assert por_codigo["502"]["estado"] == "calza"
