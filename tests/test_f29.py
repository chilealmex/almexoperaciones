"""La propuesta del F29, armada con el Libro Mayor.

El formulario se llena con lo que las cuentas de impuestos movieron en el mes.
Los números de estas pruebas son los del F29 de septiembre de 2026 (folio
9383590556) y los del mayor de la cuenta de IVA crédito fiscal del mismo mes:

    código 519  113 documentos     mayor  112 FCA + 1 FCEDIESEL
    código 520  9.167.806          mayor  8.990.287 + 177.520
    código 527  1 nota de crédito  mayor  1 NCC
    código 528  27.574             mayor  27.574
    código 534  3 formularios      mayor  3 DI
    código 535  19.203.138         mayor  19.203.138
    código 537  28.343.370         mayor  el traspaso del mes
"""

import io

import pytest

from app.models.contabilidad import F29Cuenta
from app.utils.conciliacion_sii import leer_cuentas_mayor
from app.utils.f29 import concepto_de_cuenta, propuesta_f29
from tests.conftest import login


def _mayor(*cuentas):
    """Un Libro Mayor de Defontana: un ".xls" que en realidad es HTML."""
    cuerpo = ""
    for cuenta, nombre, lineas in cuentas:
        cuerpo += f"<tr><td>{cuenta} {nombre}</td></tr>"
        cuerpo += "<tr><td>Saldo Anterior</td><td>0</td><td>0</td></tr>"
        cuerpo += "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in fila) + "</tr>" for fila in lineas
        )
        cuerpo += "<tr><td>Total</td><td>0</td><td>0</td><td>0</td><td>0</td></tr>"
    html = f"""<html><head><title>Libro Mayor</title></head><body>
    <table><tr><td>Shaw Almex Chile SpA</td><td>Fecha :05/11/2026</td></tr></table>
    <table>
      <tr><td>Libro Mayor</td></tr>
      <tr><td>Fecha</td><td>Número</td><td>Tipo</td><td>Descripción</td>
          <td>Débito $</td><td>Crédito $</td><td>Deudor $</td><td>Acreedor $</td></tr>
      {cuerpo}
    </table></body></html>"""
    return io.BytesIO(html.encode("cp1252"))


def _linea(fecha, tipo, desc, debito="0", credito="0"):
    return [fecha, "260900001", tipo, desc, debito, credito, "0", "0"]


def _doc(folio, rut="76.124.890-1"):
    return f"FCA#{folio} Proveedor {rut} UN PROVEEDOR"


# La cuenta de IVA crédito de septiembre, en chico: dos facturas del giro, una
# de importación, una nota de crédito y el traspaso del saldo al cierre.
CREDITO = (
    "1.1.1090.10.01", "IVA CREDITO FISCAL", [
        _linea("02/09/2026", "Cpra_FCA", _doc("1001"), debito="8,990,287"),
        _linea("03/09/2026", "Cpra_FCEDIESEL", "FCEDIESEL#1002 Proveedor 99.520.000-7 COPEC",
               debito="177,520"),
        _linea("10/09/2026", "Cpra_DI", "DI#1003 Proveedor 60.803.000-K ADUANA",
               debito="19,203,138"),
        _linea("20/09/2026", "Cpra_NCC", "NCC#1004 Proveedor 90.844.000-1 EMPRESA",
               credito="27,574"),
        _linea("30/09/2026", "TRASPASO", "Traspaso a IVA por pagar", credito="28,343,371"),
    ],
)
DEBITO = (
    "2.1.2030.10.01", "IVA DEBITO FISCAL", [
        _linea("05/09/2026", "Vta_FVA", "FVA#5001 Cliente 96.000.000-1 UN CLIENTE",
               credito="95,961,778"),
        _linea("25/09/2026", "Vta_NCV", "NCV#5002 Cliente 96.000.000-1 UN CLIENTE",
               debito="159,600"),
    ],
)


def _cuentas(*definiciones, mes="2026-09"):
    """Lo que la pantalla le pasa a la propuesta: las cuentas de un mes."""
    cuentas = []
    for leida in leer_cuentas_mayor(_mayor(*definiciones)):
        movimientos = [
            {"tipo": tipo, **datos}
            for (m, tipo), datos in leida["movimientos"].items() if m == mes
        ]
        cuentas.append({
            "cuenta": leida["cuenta"], "nombre": leida["nombre"], "signo": leida["signo"],
            "concepto": concepto_de_cuenta(leida["nombre"]), "movimientos": movimientos,
        })
    return cuentas


def _valor(propuesta, codigo):
    for linea in propuesta["lineas"]:
        if linea["codigo"] == codigo:
            return linea["valor"]
    raise AssertionError(f"la propuesta no trae el código {codigo}")


# ---------- Qué aporta cada cuenta ----------

def test_cada_cuenta_se_reconoce_por_su_nombre():
    # Por el nombre y no por el código: el código del plan de cuentas cambia
    # de una empresa a otra.
    assert concepto_de_cuenta("IVA CREDITO FISCAL") == "iva_credito"
    assert concepto_de_cuenta("IVA DEBITO FISCAL") == "iva_debito"
    assert concepto_de_cuenta("IVA RETENIDO POR PAGAR") == "iva_retenido"
    assert concepto_de_cuenta("PPM POR PAGAR") == "ppm"
    assert concepto_de_cuenta("RETENCION HONORARIOS") == "honorarios"
    assert concepto_de_cuenta("IMPUESTO UNICO TRABAJADORES") == "impuesto_unico"
    assert concepto_de_cuenta("BANCO ESTADO") == ""


# ---------- Los créditos ----------

def test_las_facturas_del_giro_van_al_520_y_se_cuentan_en_el_519():
    propuesta = propuesta_f29(_cuentas(CREDITO))

    assert _valor(propuesta, "520") == 8990287 + 177520
    assert _valor(propuesta, "519") == 2


def test_una_factura_en_dos_lineas_se_cuenta_una_sola_vez():
    # El formulario pide la cantidad de facturas, no de líneas contables, y
    # una factura puede quedar partida en dos líneas de la misma cuenta.
    partida = ("1.1.1090.10.01", "IVA CREDITO FISCAL", [
        _linea("02/09/2026", "Cpra_FCA", _doc("1001"), debito="1,000"),
        _linea("02/09/2026", "Cpra_FCA", _doc("1001"), debito="500"),
    ])

    propuesta = propuesta_f29(_cuentas(partida))

    assert _valor(propuesta, "519") == 1
    assert _valor(propuesta, "520") == 1500


def test_las_de_importacion_van_al_535_y_no_al_520():
    # Son dos códigos distintos del formulario: el crédito de las facturas del
    # giro y el de los formularios de pago de importación.
    propuesta = propuesta_f29(_cuentas(CREDITO))

    assert _valor(propuesta, "535") == 19203138
    assert _valor(propuesta, "534") == 1
    assert 19203138 not in (_valor(propuesta, "520"),)


def test_la_nota_de_credito_recibida_va_al_528_en_positivo():
    # Mueve la cuenta al revés que una factura, pero el formulario la pide en
    # positivo para restarla en el total.
    propuesta = propuesta_f29(_cuentas(CREDITO))

    assert _valor(propuesta, "528") == 27574
    assert _valor(propuesta, "527") == 1


def test_el_total_de_creditos_resta_las_notas_y_suma_las_importaciones():
    propuesta = propuesta_f29(_cuentas(CREDITO))

    assert _valor(propuesta, "537") == 9167807 - 27574 + 19203138


def test_el_traspaso_del_cierre_no_es_credito_de_nadie():
    # Al cierre del mes el saldo de la cuenta se traspasa a IVA por pagar. Esa
    # línea no nombra documento y no se declara: sumándola, el crédito del mes
    # saldría al doble.
    propuesta = propuesta_f29(_cuentas(CREDITO, DEBITO))

    assert _valor(propuesta, "520") == 9167807
    assert not propuesta["avisos"]


def test_si_el_traspaso_no_calza_con_el_total_se_avisa():
    # El traspaso lleva el saldo de la cuenta a IVA por pagar, así que tiene
    # que ser el mismo total de créditos. Si no lo es, falta un documento.
    cuenta, nombre, lineas = CREDITO
    torcido = (cuenta, nombre, lineas[:-1] + [
        _linea("30/09/2026", "TRASPASO", "Traspaso a IVA por pagar", credito="30,000,000"),
    ])

    propuesta = propuesta_f29(_cuentas(torcido))

    assert any("traspaso" in a.lower() for a in propuesta["avisos"])


# ---------- Los débitos ----------

def test_las_facturas_emitidas_van_al_502_y_las_notas_al_510():
    propuesta = propuesta_f29(_cuentas(DEBITO))

    assert _valor(propuesta, "502") == 95961778
    assert _valor(propuesta, "503") == 1
    assert _valor(propuesta, "510") == 159600
    assert _valor(propuesta, "509") == 1
    assert _valor(propuesta, "538") == 95961778 - 159600


# ---------- Lo determinado ----------

def test_el_impuesto_determinado_es_el_debito_menos_el_credito():
    propuesta = propuesta_f29(_cuentas(CREDITO, DEBITO))

    assert _valor(propuesta, "089") == 95802178 - (9167807 - 27574 + 19203138)


def test_las_retenciones_y_el_ppm_se_suman_al_total_a_pagar():
    cuentas = _cuentas(
        CREDITO, DEBITO,
        ("2.1.2040.10.01", "IMPUESTO UNICO TRABAJADORES", [
            _linea("30/09/2026", "SUELDOS", "Remuneraciones septiembre", credito="2,370,462")]),
        ("2.1.2040.10.02", "RETENCION HONORARIOS", [
            _linea("30/09/2026", "SUELDOS", "Boletas de honorarios", credito="405,548")]),
        ("1.1.2010.10.01", "PPM POR PAGAR", [
            _linea("30/09/2026", "TRASPASO", "PPM del mes", debito="5,042,220")]),
    )

    propuesta = propuesta_f29(cuentas)

    assert _valor(propuesta, "048") == 2370462
    assert _valor(propuesta, "151") == 405548
    assert _valor(propuesta, "062") == 5042220
    assert _valor(propuesta, "595") == _valor(propuesta, "089") + 5042220 + 2370462 + 405548
    assert _valor(propuesta, "547") == _valor(propuesta, "595")
    assert _valor(propuesta, "091") == _valor(propuesta, "595")
    assert propuesta["a_pagar"] == _valor(propuesta, "595")


def test_lo_retenido_en_el_mes_no_se_resta_con_el_pago_del_mes_anterior():
    # En la misma cuenta conviven lo retenido en septiembre (al haber) y el
    # pago de lo de agosto (al debe). Lo que se declara es lo retenido, no la
    # diferencia, que daría casi cero.
    cuentas = _cuentas(
        ("2.1.2040.10.01", "IMPUESTO UNICO TRABAJADORES", [
            _linea("12/09/2026", "EGRESO", "Pago impuesto único agosto", debito="2,300,000"),
            _linea("30/09/2026", "SUELDOS", "Remuneraciones septiembre", credito="2,370,462")]),
    )

    assert _valor(propuesta_f29(cuentas), "048") == 2370462


def test_si_el_credito_supera_al_debito_el_mes_queda_con_remanente():
    poco = ("2.1.2030.10.01", "IVA DEBITO FISCAL", [
        _linea("05/09/2026", "Vta_FVA", "FVA#5001 Cliente 96.000.000-1 UN CLIENTE",
               credito="1,000,000")])

    propuesta = propuesta_f29(_cuentas(CREDITO, poco))

    assert _valor(propuesta, "089") == 0
    assert any("remanente" in a.lower() for a in propuesta["avisos"])


def test_sin_la_cuenta_de_debito_no_se_avisa_un_remanente_que_no_se_sabe():
    # Con los débitos en cero por falta del archivo, cualquier mes parecería
    # quedar con remanente. Lo que pasa ahí es que falta la cuenta.
    propuesta = propuesta_f29(_cuentas(CREDITO))

    assert not propuesta["avisos"]
    assert "IVA débito fiscal" in propuesta["faltan"]


# ---------- Lo que falta ----------

def test_sin_la_cuenta_de_iva_debito_se_dice_que_falta():
    propuesta = propuesta_f29(_cuentas(CREDITO))

    assert "IVA débito fiscal" in propuesta["faltan"]


def test_el_iva_retenido_se_muestra_aparte_porque_no_se_sabe_su_codigo():
    # Hace falta un F29 de un mes que la traiga declarada para saber en qué
    # código va. Mientras tanto se muestra con su monto, no se esconde.
    cuentas = _cuentas(
        ("2.1.2030.10.05", "IVA RETENIDO POR PAGAR", [
            _linea("06/09/2026", "Cpra_FCEDIESEL",
                   "FCEDIESEL#337537 Proveedor 76497541-3 COMERCIAL", credito="17,970")]),
    )

    propuesta = propuesta_f29(cuentas)

    assert propuesta["sin_codigo"] == [
        {"nombre": "IVA RETENIDO POR PAGAR", "valor": 17970}
    ]


def test_una_cuenta_que_no_se_reconoce_queda_a_la_vista():
    propuesta = propuesta_f29(_cuentas(
        ("1.1.1010.10.01", "BANCO ESTADO", [
            _linea("02/09/2026", "EGRESO", "Pago a proveedores", credito="100")]),
    ))

    assert propuesta["sin_clasificar"] == [
        {"cuenta": "1.1.1010.10.01", "nombre": "BANCO ESTADO"}
    ]


# ---------- La pantalla ----------

def _subir(client, *definiciones, nombre="mayor.xls"):
    return client.post(
        "/contabilidad/f29/cargar",
        data={"mayor": [(_mayor(*definiciones), nombre)]},
        content_type="multipart/form-data", follow_redirects=True,
    )


def test_las_cuentas_se_van_sumando_a_las_que_ya_estaban(client, db, empresa, usuario_admin):
    # El mayor se baja de Defontana cuenta por cuenta, así que se suben de a
    # una: subir la segunda no puede borrar la primera.
    login(client, "admin@test.cl")

    _subir(client, CREDITO, nombre="mayor-credito.xls")
    _subir(client, DEBITO, nombre="mayor-debito.xls")

    cargadas = {c.nombre: c for c in F29Cuenta.query.all()}
    assert set(cargadas) == {"IVA CREDITO FISCAL", "IVA DEBITO FISCAL"}
    assert cargadas["IVA CREDITO FISCAL"].concepto == "iva_credito"
    assert cargadas["IVA DEBITO FISCAL"].signo == -1


def test_volver_a_subir_la_misma_cuenta_la_reemplaza(client, db, empresa, usuario_admin):
    # El mayor es una foto de la contabilidad: el de hoy manda sobre el de
    # ayer, y sus movimientos no se suman a los de antes.
    login(client, "admin@test.cl")
    _subir(client, CREDITO)
    _subir(client, CREDITO)

    cuentas = F29Cuenta.query.all()
    assert len(cuentas) == 1
    assert cuentas[0].cargas == 2
    assert len(cuentas[0].movimientos) == 5


def test_la_pantalla_muestra_el_formulario_del_mes(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    _subir(client, CREDITO, nombre="mayor-credito.xls")
    _subir(client, DEBITO, nombre="mayor-debito.xls")

    cuerpo = client.get("/contabilidad/f29?mes=2026-09").get_data(as_text=True)

    assert "TOTAL CRÉDITOS" in cuerpo
    assert "28.343.371" in cuerpo
    assert "95.802.178" in cuerpo


def test_la_propuesta_sale_en_excel(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    _subir(client, CREDITO)

    r = client.get("/contabilidad/f29/propuesta.xlsx?mes=2026-09")

    assert r.status_code == 200
    assert "spreadsheet" in r.headers["Content-Type"]


def test_quitar_una_cuenta_la_saca_de_la_propuesta(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    _subir(client, CREDITO)
    cuenta = F29Cuenta.query.first()

    client.post(f"/contabilidad/f29/{cuenta.id}/eliminar", follow_redirects=True)

    assert F29Cuenta.query.count() == 0


def test_el_f29_pide_permiso_de_contabilidad(client, db, empresa, usuario_bodega):
    login(client, "bodega@test.cl")

    assert client.get("/contabilidad/f29").status_code == 403


# ---------- El Informe por Análisis ----------
#
# Defontana lo exporta en .xlsx de verdad, con todas las cuentas juntas y una
# columna "Cuenta" en cada línea, en vez de un título por cuenta. Para el F29
# es el archivo cómodo: las siete cuentas de impuestos salen de una descarga.
#
# Su código de cuenta viene sin puntos —"1110901001"— y el documento va en la
# columna "Comentario". En ventas lo nombra de otra forma: "33 Factura
# Electronica Nº 5526" en vez de "FCA#1043902 Proveedor 76.754.296-8".

ANALISIS = [
    ["1110901001", "IVA CREDITO FISCAL", "02/09/2026", "Cpra_FCA", "260900001",
     8990287, 0, "FCA#1001 Proveedor 76.124.890-1 UN PROVEEDOR"],
    ["1110901001", "IVA CREDITO FISCAL", "30/09/2026", "TRASPASO", "260900900",
     0, 8990287, None],
    ["2120301001", "IVA DEBITO FISCAL", "05/09/2026", "Vta_FVAELECT", "260900500",
     0, 95961778, "33 Factura Electronica Nº 5526"],
    ["2120301001", "IVA DEBITO FISCAL", "25/09/2026", "Vta_NCVELECT", "260900501",
     159600, 0, "61 Nota de Credito Electronica Nº 220"],
    ["2120301002", "IMPUESTO 2 CATEGORIA", "30/09/2026", "HONORARIOS", "260900700",
     0, 405548, None],
    # Lo que hay que pagar: 95.802.178 de débitos − 8.990.287 de créditos
    # + 405.548 de retención de honorarios.
    ["2120301004", "IMPUESTO POR PAGAR", "30/09/2026", "TRASPASO", "260900999",
     0, 87217439, None],
]


def _informe(filas=None, encabezado=None):
    """El .xlsx tal como lo exporta Defontana, con su membrete arriba."""
    import openpyxl

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["Shaw Almex Chile SpA", "", "", "Fecha: 06/11/2026"])
    hoja.append(["99578050-k"])
    hoja.append(["Informe por Análisis", "", "", "Período: 01/01/2026 - 06/11/2026"])
    hoja.append(encabezado or [
        "Cuenta", "Descripción", "Fecha", "Tipo", "Número",
        "Cargo ($)", "Abono ($)", "Comentario",
    ])
    for fila in (ANALISIS if filas is None else filas):
        hoja.append(fila)
    memoria = io.BytesIO()
    libro.save(memoria)
    memoria.seek(0)
    return memoria


def _cuentas_del_informe(mes="2026-09", **kwargs):
    from app.utils.conciliacion_sii import leer_cuentas_contables

    cuentas = []
    for leida in leer_cuentas_contables(_informe(**kwargs), "informe.xlsx"):
        movimientos = [
            {"tipo": tipo, **datos}
            for (m, tipo), datos in leida["movimientos"].items() if m == mes
        ]
        cuentas.append({
            "cuenta": leida["cuenta"], "nombre": leida["nombre"], "signo": leida["signo"],
            "concepto": concepto_de_cuenta(leida["nombre"]), "movimientos": movimientos,
        })
    return cuentas


def test_se_leen_todas_las_cuentas_del_informe_en_una_sola_pasada():
    from app.utils.conciliacion_sii import leer_cuentas_contables

    cuentas = leer_cuentas_contables(_informe(), "informe.xlsx")

    assert [c["cuenta"] for c in cuentas] == [
        "1110901001", "2120301001", "2120301002", "2120301004"
    ]
    # El código viene sin puntos y el signo igual sale de su primer dígito
    assert cuentas[0]["signo"] == 1
    assert cuentas[1]["signo"] == -1


def test_la_factura_de_venta_se_reconoce_aunque_se_escriba_distinto():
    # "33 Factura Electronica Nº 5526" y no "FCA#1043902 Proveedor ...".
    propuesta = propuesta_f29(_cuentas_del_informe())

    assert _valor(propuesta, "502") == 95961778
    assert _valor(propuesta, "503") == 1
    assert _valor(propuesta, "510") == 159600
    assert _valor(propuesta, "509") == 1


def test_una_factura_de_venta_en_dos_lineas_se_cuenta_una_sola_vez():
    # Es lo que obliga a leer el folio de la glosa y no a contar líneas: el
    # formulario pide cuántas facturas se emitieron, y una factura puede
    # quedar partida en dos líneas del mismo asiento.
    partida = [
        ["2120301001", "IVA DEBITO FISCAL", "05/09/2026", "Vta_FVAELECT", "260900500",
         0, 100000, "33 Factura Electronica Nº 5526"],
        ["2120301001", "IVA DEBITO FISCAL", "05/09/2026", "Vta_FVAELECT", "260900500",
         0, 50000, "33 Factura Electronica Nº 5526"],
        ["2120301001", "IVA DEBITO FISCAL", "06/09/2026", "Vta_FVAELECT", "260900502",
         0, 70000, "33 Factura Electronica Nº 5527"],
    ]

    propuesta = propuesta_f29(_cuentas_del_informe(filas=partida))

    assert _valor(propuesta, "503") == 2
    assert _valor(propuesta, "502") == 220000


def test_la_cuenta_de_segunda_categoria_es_la_retencion_de_honorarios():
    assert concepto_de_cuenta("IMPUESTO 2 CATEGORIA") == "honorarios"
    assert _valor(propuesta_f29(_cuentas_del_informe()), "151") == 405548


def test_el_traspaso_del_cierre_comprueba_la_propuesta():
    propuesta = propuesta_f29(_cuentas_del_informe())

    control = next(c for c in propuesta["controles"] if "POR PAGAR" in c["cuenta"])
    assert control["traspasado"] == 87217439
    assert control["propuesto"] == _valor(propuesta, "595")
    assert control["calza"] is True
    assert not propuesta["avisos"]


def test_si_el_traspaso_no_calza_con_la_propuesta_se_avisa():
    torcido = [f for f in ANALISIS if "POR PAGAR" not in f[1]] + [
        ["2120301004", "IMPUESTO POR PAGAR", "30/09/2026", "TRASPASO", "260900999",
         0, 99000000, None],
    ]

    propuesta = propuesta_f29(_cuentas_del_informe(filas=torcido))

    control = next(c for c in propuesta["controles"] if "POR PAGAR" in c["cuenta"])
    assert control["calza"] is False
    assert any("no calzan" in a for a in propuesta["avisos"])


def test_un_mes_sin_cerrar_no_tiene_traspaso_y_no_se_dice_nada():
    # El traspaso es el asiento del cierre: mientras el mes no se cierre no
    # existe, y eso no es una diferencia.
    sin_cerrar = [f for f in ANALISIS if f[3] != "TRASPASO"]

    propuesta = propuesta_f29(_cuentas_del_informe(filas=sin_cerrar))

    assert propuesta["controles"] == []
    assert not propuesta["avisos"]


def test_el_asiento_del_cierre_no_es_un_documento():
    # Se distingue por el tipo: los de documento llevan el libro adelante
    # ("Cpra_FCA", "Vta_FVAELECT") y los del cierre son una sola palabra.
    from app.utils.f29 import es_de_documento

    assert es_de_documento("Cpra_FCA") is True
    assert es_de_documento("Vta_FVAELECT") is True
    assert es_de_documento("TRASPASO") is False
    assert es_de_documento("EGRESO") is False
    # Lo decide el tipo y nada más: que la glosa nombre un documento no
    # alcanza. En julio de 2026 dos líneas de TRASPASO dicen
    # "DI#5110087129 Proveedor 60.804.000-5 SERVICIO NACIONAL DE ADUANA" —una
    # corrección que entra y sale por el mismo monto— y con eso el traspaso de
    # cierre entero se metía en el código 520 y lo dejaba en negativo.
    assert es_de_documento("TRASPASO", documentos=1) is False


def test_un_excel_que_no_es_el_informe_avisa_en_vez_de_reventar():
    from app.utils.conciliacion_sii import ArchivoInvalido, leer_cuentas_contables

    with pytest.raises(ArchivoInvalido) as error:
        leer_cuentas_contables(
            _informe(encabezado=["a", "b", "c", "d", "e", "f", "g", "h"]), "otro.xlsx"
        )

    assert "Informe por Análisis" in str(error.value)


def test_el_informe_tambien_se_sube_desde_la_pantalla(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    client.post(
        "/contabilidad/f29/cargar",
        data={"mayor": [(_informe(), "Informe_por_analisis.xlsx")]},
        content_type="multipart/form-data", follow_redirects=True,
    )

    cargadas = {c.nombre: c.concepto for c in F29Cuenta.query.all()}
    assert cargadas == {
        "IVA CREDITO FISCAL": "iva_credito",
        "IVA DEBITO FISCAL": "iva_debito",
        "IMPUESTO 2 CATEGORIA": "honorarios",
        "IMPUESTO POR PAGAR": "impuesto_por_pagar",
    }


# ---------- La cuenta contable de cada línea ----------

def test_cada_codigo_dice_de_que_cuenta_sale_con_su_codigo():
    # El nombre solo no basta para ir a buscarla: el plan de cuentas se navega
    # por código y hay cuentas que se llaman parecido.
    propuesta = propuesta_f29(_cuentas(CREDITO, DEBITO))

    de_520 = next(l for l in propuesta["lineas"] if l["codigo"] == "520")
    de_502 = next(l for l in propuesta["lineas"] if l["codigo"] == "502")

    assert de_520["de"] == "1.1.1090.10.01 IVA CREDITO FISCAL"
    assert de_502["de"] == "2.1.2030.10.01 IVA DEBITO FISCAL"


def test_el_detalle_de_un_codigo_tambien_nombra_su_cuenta():
    propuesta = propuesta_f29(_cuentas(CREDITO))

    de_520 = next(l for l in propuesta["lineas"] if l["codigo"] == "520")

    assert {d["cuenta"] for d in de_520["detalle"]} == {"1.1.1090.10.01 IVA CREDITO FISCAL"}


def test_un_total_no_sale_de_una_cuenta_sino_de_otros_codigos():
    propuesta = propuesta_f29(_cuentas(CREDITO, DEBITO))

    total = next(l for l in propuesta["lineas"] if l["codigo"] == "537")

    assert total["de"] == "código 520 − código 528 + código 535"


# ---------- El PPM ----------

def test_el_ppm_del_mes_es_su_traspaso_y_no_todo_lo_que_pasó_por_la_cuenta():
    """La cuenta junta la provisión del mes con el pago de meses anteriores.

    En julio de 2026 tiene un traspaso de 4.983.204 y dos egresos —6.212.845
    y 1.465.640, los dos con glosa "CENTRALIZA IVA MES ..."— y lo declarado en
    el código 062 fue el traspaso. En septiembre, igual.
    """
    cuentas = _cuentas(
        ("1.1.0905.00.05", "PROVISION PPM", [
            _linea("01/09/2026", "EGRESO", "CENTRALIZA IVA MES mayo 2026", debito="6,212,845"),
            _linea("30/09/2026", "TRASPASO", "CENTRALIZA IVA MES septiembre 2026",
                   debito="4,983,204"),
        ]),
    )

    assert _valor(propuesta_f29(cuentas), "062") == 4983204


def test_sin_traspaso_el_ppm_es_lo_que_movió_la_cuenta():
    # No todos los meses se contabilizan con traspaso; dejarlo en cero sería
    # esconder la provisión.
    cuentas = _cuentas(
        ("1.1.0905.00.05", "PROVISION PPM", [
            _linea("30/09/2026", "EGRESO", "CENTRALIZA IVA MES septiembre 2026",
                   debito="3,988,620"),
        ]),
    )

    assert _valor(propuesta_f29(cuentas), "062") == 3988620


def test_lo_retenido_a_sueldos_y_honorarios_es_lo_del_mes_no_su_traspaso():
    """Acá manda la retención y no el traspaso, al revés que en el PPM.

    El asiento de sueldos trae la retención del impuesto único del mes y el de
    honorarios la de segunda categoría; el traspaso que cae en el mismo mes
    está cerrando la retención del mes anterior, que es otro número.
    """
    cuentas = _cuentas(
        ("2.1.2030.10.03", "IMPUESTO UNICO", [
            _linea("30/09/2026", "SUELDOS", "CENTRALIZA REMUNERACIONES", credito="3,441,426"),
            _linea("05/09/2026", "TRASPASO", "CENTRALIZA IVA MES agosto 2026",
                   debito="3,517,537"),
        ]),
        ("2.1.2030.10.02", "IMPUESTO 2 CATEGORIA", [
            _linea("30/09/2026", "HONORARIOS", "Boletas de honorarios", credito="405,548"),
            _linea("05/09/2026", "TRASPASO", "Cierre de agosto", debito="380,000"),
        ]),
    )

    propuesta = propuesta_f29(cuentas)

    assert _valor(propuesta, "048") == 3441426
    assert _valor(propuesta, "151") == 405548


def test_las_notas_de_debito_recibidas_no_van_en_el_credito_del_giro():
    """En julio de 2026 el F29 declara 147 documentos y 57.760.490.

    Son exactamente las facturas del giro sin las cuatro notas de débito, que
    van en otro código. Se muestran con su monto para que no desaparezcan.
    """
    con_nota = ("1.1.1090.10.01", "IVA CREDITO FISCAL", [
        _linea("02/09/2026", "Cpra_FCA", _doc("1001"), debito="8,990,287"),
        _linea("03/09/2026", "Cpra_NDC", "NDC#18895 Proveedor 10.853.224-6 AGENCIA",
               debito="4"),
    ])

    propuesta = propuesta_f29(_cuentas(con_nota))

    assert _valor(propuesta, "520") == 8990287
    assert _valor(propuesta, "519") == 1
    assert any("Notas de débito" in l["nombre"] for l in propuesta["sin_codigo"])
