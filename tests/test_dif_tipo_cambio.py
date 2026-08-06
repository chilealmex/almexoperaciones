"""Submódulo Contabilidad > Dif TC PR/CL: períodos mensuales y diferencia de cambio."""

import io
from datetime import date

from openpyxl import Workbook

from app.extensions import db as _db
from app.models.contabilidad import LineaDifTc, PeriodoDifTc, TipoCambioDifTc
from app.utils.dif_tipo_cambio import (
    diferencia_de_cambio,
    porcentaje_variacion,
    recalcular_periodo,
    totales_periodo,
    valor_en_pesos,
)
from app.utils.dif_tipo_cambio_excel import PlanillaInvalida, leer_mayor
from tests.conftest import login

TITULOS = [
    "Cuenta", "Descripción", "Fecha", "Tipo", "Número", "ID Ficha", "Ficha",
    "Cargo ($)", "Abono ($)", "Saldo ($)", "Código Doc.", "Documento", "Vencimiento",
    "Número Doc.", "Tipo Mov.", "Serie", "Número Mov.", "Moneda Ref.", "Comentario",
    "Doc. Pago", "Número Doc. Pago", "Serie Doc. Pago.", "TIPO MONEDA", "Mon Orig",
    "Valor en $", "Dif de cambio", "% Dif Variación", None, "Moneda", "Tipo de Cambio",
]
COL_MONEDA_TABLA, COL_TC_TABLA = 28, 29   # el bloque amarillo al costado


def _mayor(filas, tipos_cambio=None):
    """Arma un xlsx como control_AJ_TC.xlsx: el mayor y, al costado, la tabla de cambio."""
    tabla = list((tipos_cambio or {"USD": 925.48, "EUR": 925.48}).items())
    libro = Workbook()
    ws = libro.active
    ws.append(TITULOS)
    for indice, fila in enumerate(filas):
        completa = list(fila) + [None] * (30 - len(fila))
        if indice < len(tabla):
            completa[COL_MONEDA_TABLA], completa[COL_TC_TABLA] = tabla[indice]
        ws.append(completa)
    # Si hay más monedas que líneas, el resto de la tabla va en filas sueltas.
    for moneda, valor in tabla[len(filas):]:
        extra = [None] * 30
        extra[COL_MONEDA_TABLA], extra[COL_TC_TABLA] = moneda, valor
        ws.append(extra)
    memoria = io.BytesIO()
    libro.save(memoria)
    memoria.seek(0)
    return memoria


# Cuenta, Desc, Fecha, Tipo, Núm, IDFicha, Ficha, Cargo, Abono, Saldo, ... , Mon Orig (índice 22)
FILA_A = ["2120102001", "CUENTAS POR PAGAR", date(2026, 3, 6), "EGRESO", "155", "100-6",
          "ALMEX CANADA LIMITED", 47248294, 0, -47248294, "INVOICE", "Factura Invoice",
          "25/11/2025", "100108", None, "100108", None, None, "APLICA NC", None, None, None,
          "USD", -55309.68]
FILA_B = ["1110701001", "CUENTAS POR COBRAR", date(2024, 1, 1), "APERTURA", "1", "6-1",
          "FONMAR GROUP S.L", 172223, 0, 172223, "FACTEXPELECTR", "110 Factura Exportacion",
          "29/11/2022", "1516", None, None, None, None, "Apertura", None, None, None,
          "USD", 196]


# --- Fórmulas ------------------------------------------------------------


def test_las_formulas_reproducen_la_planilla():
    """Los tres cálculos de control.xlsx, con los números reales de la primera línea."""
    tc = 925.48
    valor = valor_en_pesos(-55309.68, tc)
    assert abs(valor - (-51188002.6464)) < 0.01

    # Saldo y valor tienen el mismo signo (ambos negativos): se restan.
    dif = diferencia_de_cambio(-47248294, valor)
    assert abs(dif - 3939708.6464) < 0.01
    assert abs(porcentaje_variacion(dif, -47248294) - (-0.08338308778725438)) < 1e-9


def test_con_signos_distintos_la_diferencia_se_suma():
    """Es lo que hace la fórmula Y de la planilla cuando saldo y valor no coinciden en signo."""
    assert diferencia_de_cambio(100, -30) == 70
    assert diferencia_de_cambio(-100, 30) == -70


def test_porcentaje_con_saldo_cero_no_revienta():
    assert porcentaje_variacion(500, 0) == 0.0


# --- Lectura del mayor ---------------------------------------------------


def test_leer_mayor_trae_las_lineas_y_el_tipo_de_cambio():
    lineas, tipos_cambio = leer_mayor(_mayor([FILA_A, FILA_B]))
    assert tipos_cambio == {"USD": 925.48, "EUR": 925.48}
    assert len(lineas) == 2
    assert lineas[0]["cuenta"] == "2120102001"
    assert lineas[0]["saldo"] == -47248294
    assert lineas[0]["mon_orig"] == -55309.68
    assert lineas[0]["fecha"] == date(2026, 3, 6)


def test_se_ignoran_las_filas_sin_cuenta():
    lineas, _ = leer_mayor(_mayor([FILA_A, [None] * 24]))
    assert len(lineas) == 1


def test_una_planilla_sin_las_columnas_obligatorias_avisa():
    libro = Workbook()
    libro.active.append(["Otra cosa", "Y otra"])
    memoria = io.BytesIO()
    libro.save(memoria)
    memoria.seek(0)
    try:
        leer_mayor(memoria)
        assert False, "debería haber avisado que faltan columnas"
    except PlanillaInvalida as error:
        assert "Cuenta" in str(error)


# --- Permisos ------------------------------------------------------------


def test_bodega_no_puede_ver_dif_tc(client, usuario_bodega):
    login(client, "bodega@test.cl")
    assert client.get("/contabilidad/dif-tc").status_code == 403


# --- Períodos ------------------------------------------------------------


def _crear_periodo(client, mes=5, anio=2026, usd="925,48", eur="925,48"):
    return client.post(
        "/contabilidad/dif-tc/nuevo",
        data={"mes": mes, "anio": anio, "tipo_cambio_usd": usd, "tipo_cambio_eur": eur},
        follow_redirects=True,
    )


def test_crear_un_periodo_mensual(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    assert (periodo.mes, periodo.anio) == (5, 2026)
    assert periodo.tipo_cambio_de("USD") == 925.48
    assert periodo.tipo_cambio_de("EUR") == 925.48
    assert periodo.estado == "en_proceso"


def test_no_se_puede_repetir_el_mismo_mes(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    respuesta = _crear_periodo(client)
    assert "Ya existe el período" in respuesta.get_data(as_text=True)
    assert PeriodoDifTc.query.filter_by(empresa_id=empresa.id).count() == 1


def test_importar_el_mayor_carga_y_calcula(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()

    client.post(
        f"/contabilidad/dif-tc/{periodo.id}/importar",
        data={"archivo": (_mayor([FILA_A, FILA_B]), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    _db.session.refresh(periodo)
    assert len(periodo.lineas) == 2

    primera = periodo.lineas[0]
    assert primera.valor_clp == -51188003          # -55309,68 x 925,48
    assert primera.dif_cambio == 3939709
    assert abs(primera.pct_variacion - (-0.0833830)) < 1e-5


def test_cambiar_el_tipo_de_cambio_recalcula_todo(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    client.post(
        f"/contabilidad/dif-tc/{periodo.id}/importar",
        data={"archivo": (_mayor([FILA_A]), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    _db.session.refresh(periodo)
    antes = periodo.lineas[0].valor_clp

    usd = next(tc for tc in periodo.tipos_cambio if tc.moneda == "USD")
    client.post(f"/contabilidad/dif-tc/{periodo.id}/guardar",
                data={f"tc-{usd.id}-valor": "950"}, follow_redirects=True)
    _db.session.refresh(periodo)
    assert periodo.tipo_cambio_de("USD") == 950
    assert periodo.lineas[0].valor_clp != antes
    assert periodo.lineas[0].valor_clp == round(-55309.68 * 950)


def test_se_puede_escribir_el_mon_orig_a_mano(client, usuario_admin, empresa, db):
    """Mon Orig es una de las dos columnas amarillas de la planilla."""
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    sin_mon_orig = list(FILA_A)
    sin_mon_orig[23] = None
    client.post(
        f"/contabilidad/dif-tc/{periodo.id}/importar",
        data={"archivo": (_mayor([sin_mon_orig]), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    _db.session.refresh(periodo)
    linea = periodo.lineas[0]
    assert linea.mon_orig is None

    client.post(
        f"/contabilidad/dif-tc/{periodo.id}/guardar",
        data={f"linea-{linea.id}-mon_orig": "-55309,68", f"linea-{linea.id}-tipo_moneda": "USD"},
        follow_redirects=True,
    )
    _db.session.refresh(linea)
    assert linea.mon_orig == -55309.68
    assert linea.valor_clp == -51188003


def test_cada_mes_guarda_su_propia_base_y_su_tipo_de_cambio(client, usuario_admin, empresa, db):
    """Lo pedido: la base se guarda mensualmente y el tipo de cambio va cambiando."""
    login(client, "admin@test.cl")
    _crear_periodo(client, mes=5, anio=2026, usd="925,48", eur="925,48")
    mayo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id, mes=5).one()
    client.post(
        f"/contabilidad/dif-tc/{mayo.id}/importar",
        data={"archivo": (_mayor([FILA_A]), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )

    _crear_periodo(client, mes=6, anio=2026, usd="960", eur="960")
    junio = PeriodoDifTc.query.filter_by(empresa_id=empresa.id, mes=6).one()
    client.post(
        f"/contabilidad/dif-tc/{junio.id}/importar",
        data={"archivo": (_mayor([FILA_A], {"USD": 960, "EUR": 960}), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )

    _db.session.refresh(mayo)
    _db.session.refresh(junio)
    # Junio no alteró a mayo: cada mes conserva lo suyo.
    assert mayo.tipo_cambio_de("USD") == 925.48
    assert junio.tipo_cambio_de("USD") == 960
    assert mayo.lineas[0].valor_clp == round(-55309.68 * 925.48)
    assert junio.lineas[0].valor_clp == round(-55309.68 * 960)


def test_reimportar_reemplaza_el_mayor_del_mes_sin_duplicar(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    for _ in range(2):
        client.post(
            f"/contabilidad/dif-tc/{periodo.id}/importar",
            data={"archivo": (_mayor([FILA_A, FILA_B]), "control.xlsx")},
            content_type="multipart/form-data", follow_redirects=True,
        )
    _db.session.refresh(periodo)
    assert len(periodo.lineas) == 2
    assert LineaDifTc.query.count() == 2


# --- Cierre del período --------------------------------------------------


def test_un_periodo_cerrado_no_se_puede_editar(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    client.post(f"/contabilidad/dif-tc/{periodo.id}/estado", data={"estado": "cerrado"}, follow_redirects=True)
    _db.session.refresh(periodo)
    assert periodo.estado == "cerrado"

    usd = next(tc for tc in periodo.tipos_cambio if tc.moneda == "USD")
    client.post(f"/contabilidad/dif-tc/{periodo.id}/guardar",
                data={f"tc-{usd.id}-valor": "1000"}, follow_redirects=True)
    _db.session.refresh(periodo)
    assert periodo.tipo_cambio_de("USD") == 925.48  # no se movió


def test_solo_un_superadmin_reabre_un_periodo_cerrado(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    client.post(f"/contabilidad/dif-tc/{periodo.id}/estado", data={"estado": "cerrado"}, follow_redirects=True)

    respuesta = client.post(f"/contabilidad/dif-tc/{periodo.id}/estado",
                            data={"estado": "en_proceso"}, follow_redirects=True)
    _db.session.refresh(periodo)
    assert periodo.estado == "cerrado"
    assert "superadmin" in respuesta.get_data(as_text=True)


# --- Pantalla y descarga -------------------------------------------------


def test_la_pantalla_muestra_las_columnas_de_la_planilla(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    client.post(
        f"/contabilidad/dif-tc/{periodo.id}/importar",
        data={"archivo": (_mayor([FILA_A]), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    texto = client.get(f"/contabilidad/dif-tc/{periodo.id}").get_data(as_text=True)
    for titulo in ("Cuenta", "Saldo ($)", "Mon Orig", "Valor en $", "Dif de cambio", "% Dif Variación"):
        assert titulo in texto
    assert "ALMEX CANADA LIMITED" in texto


def test_exportar_devuelve_un_excel(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    respuesta = client.get(f"/contabilidad/dif-tc/{periodo.id}/exportar.xlsx")
    assert respuesta.status_code == 200
    assert "spreadsheetml" in respuesta.headers["Content-Type"]


def test_totales_del_periodo(db, empresa):
    periodo = PeriodoDifTc(empresa_id=empresa.id, anio=2026, mes=5, tipo_cambio=925.48)
    _db.session.add(periodo)
    _db.session.flush()
    _db.session.add_all([
        LineaDifTc(periodo_id=periodo.id, orden=0, saldo=-47248294, mon_orig=-55309.68),
        LineaDifTc(periodo_id=periodo.id, orden=1, saldo=172223, mon_orig=None),
    ])
    _db.session.commit()
    recalcular_periodo(periodo)
    _db.session.commit()

    totales = totales_periodo(periodo)
    assert totales["lineas"] == 2
    assert totales["sin_mon_orig"] == 1
    assert totales["saldo"] == -47248294 + 172223


# --- Tipo de cambio por moneda ------------------------------------------

FILA_EUR = ["1110701001", "CUENTAS POR COBRAR", date(2026, 4, 29), "Vta_FACTEXPELECTR", "1613",
            "55.555.555-5", "ALMEX CANADA LIMITED", 3575160, 0, 3575160, "FACTEXPELECTR",
            "110 Factura Exportacion", "29/05/2026", "1613", None, None, None, None,
            "110 Factura", None, None, None, "EUR", 3990]


def test_cada_linea_usa_el_tipo_de_cambio_de_su_moneda(client, usuario_admin, empresa, db):
    """La planilla lo resuelve con un VLOOKUP contra la tabla Moneda / Tipo de Cambio."""
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    client.post(
        f"/contabilidad/dif-tc/{periodo.id}/importar",
        data={"archivo": (_mayor([FILA_A, FILA_EUR], {"USD": 900, "EUR": 1000}), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    _db.session.refresh(periodo)
    en_usd = next(l for l in periodo.lineas if l.tipo_moneda == "USD")
    en_eur = next(l for l in periodo.lineas if l.tipo_moneda == "EUR")

    assert en_usd.valor_clp == round(-55309.68 * 900)
    assert en_eur.valor_clp == round(3990 * 1000)


def test_al_importar_se_cargan_los_tipos_de_cambio_de_la_planilla(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post("/contabilidad/dif-tc/nuevo", data={"mes": 5, "anio": 2026}, follow_redirects=True)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    client.post(
        f"/contabilidad/dif-tc/{periodo.id}/importar",
        data={"archivo": (_mayor([FILA_A, FILA_EUR], {"USD": 930.048, "EUR": 1015.5}), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    _db.session.refresh(periodo)
    assert periodo.tipo_cambio_de("USD") == 930.048
    assert periodo.tipo_cambio_de("EUR") == 1015.5


def test_cambiar_el_tipo_de_cambio_de_una_moneda_no_toca_las_otras(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    client.post(
        f"/contabilidad/dif-tc/{periodo.id}/importar",
        data={"archivo": (_mayor([FILA_A, FILA_EUR], {"USD": 900, "EUR": 1000}), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    _db.session.refresh(periodo)
    eur_antes = next(l for l in periodo.lineas if l.tipo_moneda == "EUR").valor_clp

    usd = next(tc for tc in periodo.tipos_cambio if tc.moneda == "USD")
    client.post(f"/contabilidad/dif-tc/{periodo.id}/guardar",
                data={f"tc-{usd.id}-valor": "1200"}, follow_redirects=True)
    _db.session.refresh(periodo)

    assert next(l for l in periodo.lineas if l.tipo_moneda == "USD").valor_clp == round(-55309.68 * 1200)
    assert next(l for l in periodo.lineas if l.tipo_moneda == "EUR").valor_clp == eur_antes


def test_se_puede_agregar_otra_moneda_a_la_tabla(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    assert {tc.moneda for tc in periodo.tipos_cambio} == {"USD", "EUR"}

    client.post(f"/contabilidad/dif-tc/{periodo.id}/guardar",
                data={"nueva_moneda": "cad", "nuevo_tipo_cambio": "680,5"}, follow_redirects=True)
    _db.session.refresh(periodo)
    assert periodo.tipo_cambio_de("CAD") == 680.5   # se guarda en mayúsculas


def test_se_puede_cambiar_la_moneda_de_una_linea(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    client.post(
        f"/contabilidad/dif-tc/{periodo.id}/importar",
        data={"archivo": (_mayor([FILA_A], {"USD": 900, "EUR": 1000}), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    _db.session.refresh(periodo)
    linea = periodo.lineas[0]
    assert linea.tipo_moneda == "USD"

    client.post(
        f"/contabilidad/dif-tc/{periodo.id}/guardar",
        data={f"linea-{linea.id}-mon_orig": "-55309,68", f"linea-{linea.id}-tipo_moneda": "EUR"},
        follow_redirects=True,
    )
    _db.session.refresh(linea)
    assert linea.tipo_moneda == "EUR"
    assert linea.valor_clp == round(-55309.68 * 1000)


def test_una_moneda_sin_tipo_de_cambio_se_avisa_en_pantalla(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post("/contabilidad/dif-tc/nuevo", data={"mes": 5, "anio": 2026}, follow_redirects=True)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    sin_tabla = list(FILA_A)
    sin_tabla[22] = "GBP"   # una moneda que no está en la tabla del mes
    client.post(
        f"/contabilidad/dif-tc/{periodo.id}/importar",
        data={"archivo": (_mayor([sin_tabla], {"USD": 900}), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    texto = client.get(f"/contabilidad/dif-tc/{periodo.id}").get_data(as_text=True)
    assert "sin tipo de cambio" in texto


def test_la_pantalla_muestra_la_tabla_de_monedas_y_la_columna_tipo_moneda(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    client.post(
        f"/contabilidad/dif-tc/{periodo.id}/importar",
        data={"archivo": (_mayor([FILA_A, FILA_EUR]), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    texto = client.get(f"/contabilidad/dif-tc/{periodo.id}").get_data(as_text=True)
    assert "Tipos de cambio del mes" in texto
    assert "Tipo moneda" in texto
    assert TipoCambioDifTc.query.filter_by(periodo_id=periodo.id).count() >= 2
