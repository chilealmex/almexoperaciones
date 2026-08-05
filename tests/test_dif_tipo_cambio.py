"""Submódulo Contabilidad > Dif TC PR/CL: períodos mensuales y diferencia de cambio."""

import io
from datetime import date

from openpyxl import Workbook

from app.extensions import db as _db
from app.models.contabilidad import LineaDifTc, PeriodoDifTc
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
    "Doc. Pago", "Número Doc. Pago", "Serie Doc. Pago.", "Mon Orig", "Valor en $",
    "Dif de cambio", "% Dif Variación", None, "Tipo de Cambio",
]


def _mayor(filas, tipo_cambio=925.48):
    """Arma un xlsx con la forma de control.xlsx: títulos en la fila 1, datos desde la 2."""
    libro = Workbook()
    ws = libro.active
    ws.append(TITULOS)
    for indice, fila in enumerate(filas):
        completa = list(fila) + [None] * (28 - len(fila))
        if indice == 0:
            completa[27] = tipo_cambio  # el T/C vive en la primera fila de datos
        ws.append(completa)
    memoria = io.BytesIO()
    libro.save(memoria)
    memoria.seek(0)
    return memoria


# Cuenta, Desc, Fecha, Tipo, Núm, IDFicha, Ficha, Cargo, Abono, Saldo, ... , Mon Orig (índice 22)
FILA_A = ["2120102001", "CUENTAS POR PAGAR", date(2026, 3, 6), "EGRESO", "155", "100-6",
          "ALMEX CANADA LIMITED", 47248294, 0, -47248294, "INVOICE", "Factura Invoice",
          "25/11/2025", "100108", None, "100108", None, None, "APLICA NC", None, None, None, -55309.68]
FILA_B = ["1110701001", "CUENTAS POR COBRAR", date(2024, 1, 1), "APERTURA", "1", "6-1",
          "FONMAR GROUP S.L", 172223, 0, 172223, "FACTEXPELECTR", "110 Factura Exportacion",
          "29/11/2022", "1516", None, None, None, None, "Apertura", None, None, None, 196]


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
    lineas, tipo_cambio = leer_mayor(_mayor([FILA_A, FILA_B]))
    assert tipo_cambio == 925.48
    assert len(lineas) == 2
    assert lineas[0]["cuenta"] == "2120102001"
    assert lineas[0]["saldo"] == -47248294
    assert lineas[0]["mon_orig"] == -55309.68
    assert lineas[0]["fecha"] == date(2026, 3, 6)


def test_se_ignoran_las_filas_sin_cuenta():
    lineas, _ = leer_mayor(_mayor([FILA_A, [None] * 23]))
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


def _crear_periodo(client, mes=5, anio=2026, tipo_cambio="925,48"):
    return client.post(
        "/contabilidad/dif-tc/nuevo",
        data={"mes": mes, "anio": anio, "tipo_cambio": tipo_cambio},
        follow_redirects=True,
    )


def test_crear_un_periodo_mensual(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    assert (periodo.mes, periodo.anio) == (5, 2026)
    assert periodo.tipo_cambio == 925.48
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

    client.post(f"/contabilidad/dif-tc/{periodo.id}/guardar",
                data={"tipo_cambio": "950"}, follow_redirects=True)
    _db.session.refresh(periodo)
    assert periodo.tipo_cambio == 950
    assert periodo.lineas[0].valor_clp != antes
    assert periodo.lineas[0].valor_clp == round(-55309.68 * 950)


def test_se_puede_escribir_el_mon_orig_a_mano(client, usuario_admin, empresa, db):
    """Mon Orig es una de las dos columnas amarillas de la planilla."""
    login(client, "admin@test.cl")
    _crear_periodo(client)
    periodo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id).one()
    sin_mon_orig = list(FILA_A)
    sin_mon_orig[22] = None
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
        data={"tipo_cambio": "925,48", f"linea-{linea.id}-mon_orig": "-55309,68"},
        follow_redirects=True,
    )
    _db.session.refresh(linea)
    assert linea.mon_orig == -55309.68
    assert linea.valor_clp == -51188003


def test_cada_mes_guarda_su_propia_base_y_su_tipo_de_cambio(client, usuario_admin, empresa, db):
    """Lo pedido: la base se guarda mensualmente y el tipo de cambio va cambiando."""
    login(client, "admin@test.cl")
    _crear_periodo(client, mes=5, anio=2026, tipo_cambio="925,48")
    mayo = PeriodoDifTc.query.filter_by(empresa_id=empresa.id, mes=5).one()
    client.post(
        f"/contabilidad/dif-tc/{mayo.id}/importar",
        data={"archivo": (_mayor([FILA_A]), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )

    _crear_periodo(client, mes=6, anio=2026, tipo_cambio="960")
    junio = PeriodoDifTc.query.filter_by(empresa_id=empresa.id, mes=6).one()
    client.post(
        f"/contabilidad/dif-tc/{junio.id}/importar",
        data={"archivo": (_mayor([FILA_A], tipo_cambio=960), "control.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )

    _db.session.refresh(mayo)
    _db.session.refresh(junio)
    # Junio no alteró a mayo: cada mes conserva lo suyo.
    assert mayo.tipo_cambio == 925.48
    assert junio.tipo_cambio == 960
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

    client.post(f"/contabilidad/dif-tc/{periodo.id}/guardar", data={"tipo_cambio": "1000"}, follow_redirects=True)
    _db.session.refresh(periodo)
    assert periodo.tipo_cambio == 925.48  # no se movió


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
