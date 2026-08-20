"""Cruce entre el RCV del SII y los libros de Defontana.

Se prueba el motor con los dos formatos reales: el .csv separado por punto y
coma del SII, y el ".xls" de Defontana que en realidad es HTML.
"""

import io

import pytest
from werkzeug.datastructures import FileStorage

from app.utils.conciliacion_sii import (
    COLUMNAS_MONTO,
    ArchivoInvalido,
    a_monto,
    cruzar,
    describir_diferencia,
    diferencias_de,
    leer_libro_defontana,
    leer_rcv_sii,
    normalizar_folio,
    normalizar_nombre,
    normalizar_rut,
)


# --- Interpretar los importes ---


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("1234567", 1234567),
        ("1.234.567", 1234567),      # separador de miles chileno
        ("1,234,567", 1234567),      # separador de miles inglés
        ("1234567,89", 1234568),     # con decimales: se redondea a pesos
        ("(1.234)", -1234),          # paréntesis contable = negativo
        ("-1234", -1234),
        ("$ 1.234", 1234),
        ("", 0),
        (None, 0),
        ("-", 0),
        (1234, 1234),
        (1234.6, 1235),
    ],
)
def test_a_monto_interpreta_los_formatos_de_las_planillas(entrada, esperado):
    assert a_monto(entrada) == esperado


def test_normalizar_rut_y_folio():
    assert normalizar_rut(" 76.123.456-7 ") == "76123456-7"
    # Un folio con ceros de relleno es el mismo documento que sin ellos.
    assert normalizar_folio("00123") == "123"
    assert normalizar_folio("123") == "123"
    # Si lleva letras, el cero inicial es parte del dato y no se toca.
    assert normalizar_folio("0A12") == "0A12"


# --- Leer el RCV del SII ---


CSV_COMPRA = (
    "Nro;Tipo Doc;Tipo Compra;RUT Proveedor;Razon Social;Folio;Fecha Docto;"
    "Monto Exento;Monto Neto;Monto IVA Recuperable;Monto Total\r\n"
    "1;33;Del Giro;76.123.456-7;PROVEEDOR UNO SPA;1001;05/08/2026;0;100000;19000;119000\r\n"
    "2;33;Del Giro;77.222.333-4;PROVEEDOR DOS LTDA;2002;12/08/2026;0;50000;9500;59500\r\n"
    "3;61;Del Giro;76.123.456-7;PROVEEDOR UNO SPA;900;20/08/2026;0;10000;1900;11900\r\n"
)

CSV_VENTA = (
    "Nro;Tipo Doc;Rut cliente;Razon Social;Folio;Fecha Docto;"
    "Monto Exento;Monto Neto;Monto IVA;Monto total\r\n"
    "1;33;60.111.222-3;CLIENTE UNO SA;5001;03/08/2026;0;200000;38000;238000\r\n"
)


def _archivo(texto, nombre, codificacion="utf-8"):
    return FileStorage(stream=io.BytesIO(texto.encode(codificacion)), filename=nombre)


def test_leer_rcv_compra(db):
    docs = leer_rcv_sii(_archivo(CSV_COMPRA, "compra.csv"), "compra")

    assert len(docs) == 3
    primero = docs[0]
    assert primero["tipo_doc"] == "33"
    assert primero["folio"] == "1001"
    assert primero["rut"] == "76123456-7"
    assert primero["contraparte"] == "PROVEEDOR UNO SPA"
    assert primero["neto"] == 100000
    assert primero["iva"] == 19000
    assert primero["total"] == 119000


def test_leer_rcv_venta_usa_las_columnas_del_libro_de_ventas(db):
    """En ventas el SII escribe 'Rut cliente' y 'Monto IVA', no los de compras."""
    docs = leer_rcv_sii(_archivo(CSV_VENTA, "venta.csv"), "venta")

    assert len(docs) == 1
    assert docs[0]["rut"] == "60111222-3"
    assert docs[0]["iva"] == 38000
    assert docs[0]["total"] == 238000


def test_un_csv_que_no_es_del_sii_avisa_en_vez_de_reventar(db):
    with pytest.raises(ArchivoInvalido) as error:
        leer_rcv_sii(_archivo("a;b;c\r\n1;2;3\r\n", "cualquiera.csv"), "compra")
    assert "Tipo Doc" in str(error.value)


# --- Leer el libro de Defontana ---


LIBRO_DEFONTANA = """<html><body>
<table><tr><td>Shaw Almex</td></tr><tr><td>Libro de Compras Agosto 2026</td></tr></table>
<table>
  <tr><td>Documento: 33</td></tr>
  <tr><td>Folio</td><td>Fecha</td><td>RUT</td><td>Razon Social</td>
      <td>Neto</td><td>Exento</td><td>IVA</td><td>Total</td></tr>
  <tr><td>1001</td><td>05/08/2026</td><td>76.123.456-7</td><td>PROVEEDOR UNO SPA</td>
      <td>100.000</td><td>0</td><td>19.000</td><td>119.000</td></tr>
  <tr><td>3003</td><td>18/08/2026</td><td>78.999.888-1</td><td>PROVEEDOR TRES</td>
      <td>30.000</td><td>0</td><td>5.700</td><td>35.700</td></tr>
  <tr><td>Total Documento 33</td><td></td><td></td><td></td>
      <td>130.000</td><td>0</td><td>24.700</td><td>154.700</td></tr>
  <tr><td>Documento: 61</td></tr>
  <tr><td>900</td><td>20/08/2026</td><td>76.123.456-7</td><td>PROVEEDOR UNO SPA</td>
      <td>(10.000)</td><td>0</td><td>(1.900)</td><td>(11.900)</td></tr>
</table>
</body></html>"""


def test_leer_libro_defontana(db):
    docs = leer_libro_defontana(_archivo(LIBRO_DEFONTANA, "compras.xls", "cp1252"))

    assert len(docs) == 3
    por_folio = {d["folio"]: d for d in docs}

    assert por_folio["1001"]["tipo_doc"] == "33"
    assert por_folio["1001"]["total"] == 119000
    assert por_folio["1001"]["rut"] == "76123456-7"
    # El tipo se arrastra del encabezado "Documento: NN" que va más arriba
    assert por_folio["900"]["tipo_doc"] == "61"
    # Y los paréntesis de la nota de crédito son un monto negativo
    assert por_folio["900"]["total"] == -11900


def test_las_filas_de_total_no_se_cuentan_como_documentos(db):
    docs = leer_libro_defontana(_archivo(LIBRO_DEFONTANA, "compras.xls", "cp1252"))
    assert all(not d["folio"].lower().startswith("total") for d in docs)
    assert "154700" not in [str(d["total"]) for d in docs]


def test_un_html_sin_la_tabla_esperada_avisa(db):
    html = "<html><body><table><tr><td>Hola</td></tr></table></body></html>"
    with pytest.raises(ArchivoInvalido) as error:
        leer_libro_defontana(_archivo(html, "otro.xls", "cp1252"))
    assert "Defontana" in str(error.value)


# --- El cruce ---


def _cruce_de_prueba():
    sii = leer_rcv_sii(_archivo(CSV_COMPRA, "compra.csv"), "compra")
    defo = leer_libro_defontana(_archivo(LIBRO_DEFONTANA, "compras.xls", "cp1252"))
    return cruzar(sii, defo, "compra")


def test_el_cruce_clasifica_cada_documento(db):
    resultado = _cruce_de_prueba()
    por_folio = {f["folio"]: f for f in resultado["filas"]}

    # 1001 está en los dos por el mismo monto
    assert por_folio["1001"]["estado"] == "coincide"
    # 2002 sólo lo tiene el SII: falta contabilizarlo
    assert por_folio["2002"]["estado"] == "solo_sii"
    # 3003 sólo lo tiene Defontana: se contabilizó algo que el SII no conoce
    assert por_folio["3003"]["estado"] == "solo_defontana"
    # La nota de crédito 900 calza una vez que se le da vuelta el signo al SII
    assert por_folio["900"]["estado"] == "coincide"
    assert por_folio["900"]["total_sii"] == -11900

    assert resultado["conteos"] == {
        "coincide": 2, "solo_sii": 1, "solo_defontana": 1, "dif_monto": 0, "dif_datos": 0
    }


def test_primero_se_muestra_lo_que_hay_que_trabajar(db):
    estados = [f["estado"] for f in _cruce_de_prueba()["filas"]]
    # Lo que cuadra va al final; arriba lo que exige revisión.
    assert estados.index("solo_sii") < estados.index("coincide")
    assert estados.index("solo_defontana") < estados.index("coincide")


def test_los_totales_permiten_cuadrar_contra_la_declaracion(db):
    totales = _cruce_de_prueba()["totales"]

    # SII: 119.000 + 59.500 - 11.900 (nota de crédito)
    assert totales["total_sii"] == 166600
    # Defontana: 119.000 + 35.700 - 11.900
    assert totales["total_defontana"] == 142800
    assert totales["diferencia"] == 166600 - 142800
    assert totales["documentos"] == 4


def test_hay_un_total_para_cada_columna_de_plata(db):
    """Lo que pidió la usuaria: los valores totales por columna, no sólo el total."""
    resultado = _cruce_de_prueba()
    totales = resultado["totales"]

    for campo, _etiqueta in COLUMNAS_MONTO:
        assert campo in totales, f"falta el total de la columna {campo}"
        # Y cada total es de verdad la suma de esa columna
        assert totales[campo] == sum(f[campo] for f in resultado["filas"])


def test_la_diferencia_se_desglosa_por_columna(db):
    sii = [{"tipo_doc": "33", "folio": "1", "rut": "76123456-7", "contraparte": "X",
            "fecha": "01/08/2026", "neto": 100000, "exento": 5000, "iva": 19000, "total": 124000}]
    defo = [{"tipo_doc": "33", "folio": "1", "rut": "76123456-7", "contraparte": "X",
             "fecha": "01/08/2026", "neto": 90000, "exento": 5000, "iva": 17100, "total": 112100}]

    fila = cruzar(sii, defo, "compra")["filas"][0]

    assert fila["dif_neto"] == 10000
    assert fila["dif_exento"] == 0      # el exento calza
    assert fila["dif_iva"] == 1900
    assert fila["diferencia"] == 11900


# --- Explicar en qué se diferencian ---


def test_una_diferencia_de_monto_dice_en_que_columna_esta(db):
    sii = [{"tipo_doc": "33", "folio": "1", "rut": "76123456-7", "contraparte": "X",
            "fecha": "01/08/2026", "neto": 100000, "exento": 0, "iva": 19000, "total": 119000}]
    defo = [{"tipo_doc": "33", "folio": "1", "rut": "76123456-7", "contraparte": "X",
             "fecha": "01/08/2026", "neto": 90000, "exento": 0, "iva": 17100, "total": 107100}]

    fila = cruzar(sii, defo, "compra")["filas"][0]

    assert fila["estado"] == "dif_monto"
    campos = [d["campo"] for d in fila["detalles_diferencia"]]
    assert campos == ["neto", "iva", "total"]  # el exento calza, no se menciona

    detalle_neto = fila["detalles_diferencia"][0]
    assert detalle_neto["sii"] == 100000
    assert detalle_neto["defontana"] == 90000
    assert detalle_neto["diferencia"] == 10000

    assert "Neto: $100.000 vs $90.000" in fila["diferencia_descrita"]
    assert "IVA" in fila["diferencia_descrita"]


def test_un_documento_que_falta_muestra_el_monto_que_falta(db):
    """Lo que pidió la usuaria: ver el monto, no sólo que falta."""
    sii = [{"tipo_doc": "33", "folio": "7", "rut": "76123456-7", "contraparte": "X",
            "fecha": "01/08/2026", "neto": 50000, "exento": 0, "iva": 9500, "total": 59500}]

    fila = cruzar(sii, [], "compra")["filas"][0]

    assert fila["estado"] == "solo_sii"
    assert fila["total_sii"] == 59500
    assert fila["total_defontana"] == 0
    assert "$59.500 vs $0" in fila["diferencia_descrita"]


def test_un_rut_distinto_se_informa_aunque_los_montos_calcen(db):
    comun = {"tipo_doc": "33", "folio": "1", "contraparte": "X", "fecha": "01/08/2026",
             "neto": 100000, "exento": 0, "iva": 19000, "total": 119000}
    sii = [dict(comun, rut="76123456-7")]
    defo = [dict(comun, rut="77999888-6")]

    fila = cruzar(sii, defo, "compra")["filas"][0]

    # La plata cuadra, pero el documento está a nombre de otro: no es "Coincide".
    assert fila["estado"] == "dif_datos"
    assert "RUT distinto" in fila["diferencia_descrita"]


def test_con_el_mismo_rut_un_nombre_distinto_no_es_diferencia(db):
    """Defontana abrevia y recorta la razón social; el RUT es la identidad real.

    Sobre datos reales esto generaba 71 avisos falsos contra 4 diferencias de
    monto verdaderas, y las tapaba por completo.
    """
    comun = {"tipo_doc": "33", "folio": "1", "rut": "78205293-4", "fecha": "01/08/2026",
             "neto": 100000, "exento": 0, "iva": 19000, "total": 119000}
    sii = [dict(comun, contraparte="SOCIEDAD ESTACIONES DE SERVICIO ARAGON LIMITADA")]
    defo = [dict(comun, contraparte="SOC ESTA DE SERV A RAGON LTDA")]

    fila = cruzar(sii, defo, "compra")["filas"][0]

    assert fila["estado"] == "coincide"
    assert fila["diferencia_descrita"] == ""


def test_sin_rut_para_comparar_el_nombre_si_se_informa(db):
    """Si falta el RUT en un lado, la razón social es la única señal de identidad."""
    comun = {"tipo_doc": "33", "folio": "1", "fecha": "01/08/2026",
             "neto": 100000, "exento": 0, "iva": 19000, "total": 119000}
    sii = [dict(comun, rut="76123456-7", contraparte="COMERCIAL ALFA SPA")]
    defo = [dict(comun, rut="", contraparte="DISTRIBUIDORA BETA LTDA")]

    fila = cruzar(sii, defo, "compra")["filas"][0]

    assert fila["estado"] == "dif_datos"
    assert "Razón social" in fila["diferencia_descrita"]


def test_con_ruts_distintos_se_informan_los_dos_datos(db):
    comun = {"tipo_doc": "33", "folio": "1", "fecha": "01/08/2026",
             "neto": 100000, "exento": 0, "iva": 19000, "total": 119000}
    sii = [dict(comun, rut="76123456-7", contraparte="COMERCIAL ALFA SPA")]
    defo = [dict(comun, rut="77999888-6", contraparte="DISTRIBUIDORA BETA LTDA")]

    fila = cruzar(sii, defo, "compra")["filas"][0]

    assert fila["estado"] == "dif_datos"
    assert "RUT distinto" in fila["diferencia_descrita"]
    assert "Razón social" in fila["diferencia_descrita"]


def test_el_mismo_nombre_escrito_distinto_no_es_una_diferencia(db):
    """Los dos sistemas escriben la razón social a su manera; eso no es un error."""
    comun = {"tipo_doc": "33", "folio": "1", "rut": "76123456-7", "fecha": "01/08/2026",
             "neto": 100000, "exento": 0, "iva": 19000, "total": 119000}
    sii = [dict(comun, contraparte="COMERCIAL ALFA S.P.A.")]
    defo = [dict(comun, contraparte="Comercial  Alfa SPA")]

    assert cruzar(sii, defo, "compra")["filas"][0]["estado"] == "coincide"


def test_normalizar_nombre_ignora_puntuacion_acentos_y_espacios():
    assert normalizar_nombre("COMERCIAL ALFA S.P.A.") == normalizar_nombre("Comercial  Alfa SPA")
    assert normalizar_nombre("LOGÍSTICA ÑUÑOA") == normalizar_nombre("Logistica  Nunoa")
    assert normalizar_nombre("TRANSPORTES DEL SUR LTDA.") == normalizar_nombre("Transportes del Sur Ltda")
    assert normalizar_nombre("ALFA") != normalizar_nombre("BETA")


def test_una_diferencia_de_monto_manda_sobre_una_de_datos(db):
    """Si además de la plata baila el RUT, el estado es el de monto: es lo grave."""
    comun = {"tipo_doc": "33", "folio": "1", "fecha": "01/08/2026", "contraparte": "ALFA",
             "exento": 0}
    sii = [dict(comun, rut="76123456-7", neto=100000, iva=19000, total=119000)]
    defo = [dict(comun, rut="77999888-6", neto=90000, iva=17100, total=107100)]

    fila = cruzar(sii, defo, "compra")["filas"][0]

    assert fila["estado"] == "dif_monto"
    # Pero igual se informa el RUT, que también hay que corregir.
    assert "RUT distinto" in fila["diferencia_descrita"]


def test_sin_diferencias_no_se_describe_nada(db):
    comun = {"tipo_doc": "33", "folio": "1", "rut": "76123456-7", "contraparte": "X",
             "fecha": "01/08/2026", "neto": 100000, "exento": 0, "iva": 19000, "total": 119000}

    fila = cruzar([dict(comun)], [dict(comun)], "compra")["filas"][0]

    assert fila["estado"] == "coincide"
    assert fila["diferencia_descrita"] == ""


def test_una_diferencia_de_un_peso_es_redondeo_y_no_descuadre(db):
    comun = {"tipo_doc": "33", "folio": "1", "rut": "76123456-7", "contraparte": "X",
             "fecha": "01/08/2026", "neto": 100000, "exento": 0, "iva": 19000}
    sii = [dict(comun, total=119000)]
    defo = [dict(comun, total=118999)]

    assert cruzar(sii, defo, "compra")["filas"][0]["estado"] == "coincide"


def test_en_ventas_las_notas_de_debito_se_comparan_en_positivo(db):
    sii = [{"tipo_doc": "56", "folio": "1", "rut": "60111222-3", "contraparte": "C",
            "fecha": "01/08/2026", "neto": 10000, "exento": 0, "iva": 1900, "total": 11900}]
    defo = [{"tipo_doc": "56", "folio": "1", "rut": "60111222-3", "contraparte": "C",
             "fecha": "01/08/2026", "neto": -10000, "exento": 0, "iva": -1900, "total": -11900}]

    assert cruzar(sii, defo, "venta")["filas"][0]["estado"] == "coincide"
    # En compras no se aplica ese ajuste: ahí sí sería una diferencia real.
    assert cruzar(sii, defo, "compra")["filas"][0]["estado"] == "dif_monto"


def test_un_documento_repetido_en_varias_lineas_se_suma(db):
    """Pasa en los libros: un mismo folio registrado en dos asientos."""
    sii = [{"tipo_doc": "33", "folio": "1", "rut": "76123456-7", "contraparte": "X",
            "fecha": "01/08/2026", "neto": 100000, "exento": 0, "iva": 19000, "total": 119000}]
    mitad = {"tipo_doc": "33", "folio": "1", "rut": "76123456-7", "contraparte": "X",
             "fecha": "01/08/2026", "neto": 50000, "exento": 0, "iva": 9500, "total": 59500}
    defo = [dict(mitad), dict(mitad)]

    resultado = cruzar(sii, defo, "compra")

    assert len(resultado["filas"]) == 1
    assert resultado["filas"][0]["estado"] == "coincide"
    assert resultado["filas"][0]["total_defontana"] == 119000


def test_describir_diferencia_sin_detalles_devuelve_vacio(db):
    assert describir_diferencia([]) == ""


def test_diferencias_de_ignora_las_menores_a_la_tolerancia(db):
    fila = {
        "neto_sii": 100000, "neto_defontana": 100001,
        "exento_sii": 0, "exento_defontana": 0,
        "iva_sii": 19000, "iva_defontana": 19000,
        "total_sii": 119000, "total_defontana": 119001,
        "rut_sii": "76123456-7", "rut_defontana": "76123456-7",
    }
    assert diferencias_de(fila) == []
