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
