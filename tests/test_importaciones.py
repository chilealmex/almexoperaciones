"""Módulo de Importaciones: lógica de cálculo contable y rutas."""

from app.extensions import db as _db
from app.models.importacion import DinRegistro, Importacion, ProveedorImportacion
from app.utils import importaciones_calculo as calculo
from tests.conftest import login
from tests.test_permissions import _crear_superadmin


def _crear_importacion(db, empresa, **kwargs):
    datos = {"empresa_id": empresa.id, "monto": 0}
    datos.update(kwargs)
    importacion = Importacion(**datos)
    db.session.add(importacion)
    db.session.flush()
    calculo.sembrar_lineas_plantilla(importacion)
    calculo.recalcular(importacion)
    db.session.commit()
    return importacion


# --- Lógica de cálculo (recalcular) ---------------------------------------


def test_sembrar_lineas_plantilla_crea_las_seis_grupos_y_sus_cuentas(db, empresa):
    importacion = _crear_importacion(db, empresa)
    for tipo in calculo.TIPOS_ASIENTO:
        assert importacion.meta_de(tipo) is not None
        assert len(importacion.lineas_de(tipo)) == len(calculo.ROW_TEMPLATES[tipo])


def test_factura_agencia_calcula_iva_19_por_ciento_y_total_proveedor(db, empresa):
    importacion = _crear_importacion(db, empresa)
    importacion.linea_por_rol("factura_agencia", "fa_l1").debe = 100_000
    importacion.linea_por_rol("factura_agencia", "fa_l2").debe = 50_000
    calculo.recalcular(importacion)
    db.session.commit()

    assert importacion.linea_por_rol("factura_agencia", "fa_iva").debe == 28_500  # 19% de 150.000
    assert importacion.linea_por_rol("factura_agencia", "fa_provnac").haber == 178_500


def test_din_convierte_usd_a_clp_y_calcula_factura_por_recibir(db, empresa):
    importacion = _crear_importacion(db, empresa)
    meta = importacion.meta_de("din")
    meta.monto_usd = 1000
    meta.tipo_cambio = 900
    calculo.recalcular(importacion)
    db.session.commit()

    din_monto = importacion.linea_por_rol("din", "din_monto")
    din_fpr = importacion.linea_por_rol("din", "din_facturaporrecibir")
    din_provnac = importacion.linea_por_rol("din", "din_provnac")
    assert din_monto.debe == 900_000
    assert din_fpr.debe == round(900_000 / 0.19)
    assert din_provnac.haber == din_monto.debe + din_fpr.debe


def test_cuadratura_toma_los_totales_de_factura_agencia_din_y_saldo_anterior(db, empresa):
    importacion = _crear_importacion(db, empresa)
    importacion.linea_por_rol("factura_agencia", "fa_l1").debe = 100_000
    importacion.meta_de("din").monto_usd = 500
    importacion.meta_de("din").tipo_cambio = 900
    importacion.meta_de("cuadratura").saldo_anterior_monto = 15_000
    calculo.recalcular(importacion)
    db.session.commit()

    fa_provnac = importacion.linea_por_rol("factura_agencia", "fa_provnac")
    din_fpr = importacion.linea_por_rol("din", "din_facturaporrecibir")
    din_provnac = importacion.linea_por_rol("din", "din_provnac")

    assert importacion.linea_por_rol("cuadratura", "cua_provnac_ini").debe == fa_provnac.haber
    assert importacion.linea_por_rol("cuadratura", "cua_anticipo").haber == 15_000
    assert importacion.linea_por_rol("cuadratura", "cua_facturaporrecibir").haber == din_fpr.debe
    assert importacion.linea_por_rol("cuadratura", "cua_provnac_tesoreria").debe == din_provnac.haber


def test_costeo_diferencia_positiva_se_traslada_al_ajuste(db, empresa):
    importacion = _crear_importacion(db, empresa, monto=1_000_000)
    importacion.linea_por_rol("costeo", "costeo_invoice").haber = 700_000
    importacion.linea_por_rol("costeo", "costeo_seguro").haber = 100_000
    calculo.recalcular(importacion)
    db.session.commit()

    assert importacion.costeo_valor == 1_000_000
    assert importacion.costeo_suma == 800_000
    assert importacion.costeo_diferencia == 200_000

    aj_ext = importacion.linea_por_rol("ajuste", "aj_extransito")
    aj_adj = importacion.linea_por_rol("ajuste", "aj_ajuste")
    assert (aj_ext.debe, aj_ext.haber) == (200_000, 0)
    assert (aj_adj.debe, aj_adj.haber) == (0, 200_000)


def test_costeo_diferencia_negativa_se_traslada_al_ajuste_en_sentido_contrario(db, empresa):
    importacion = _crear_importacion(db, empresa, monto=500_000)
    importacion.linea_por_rol("costeo", "costeo_invoice").haber = 700_000
    calculo.recalcular(importacion)
    db.session.commit()

    assert importacion.costeo_diferencia == -200_000
    aj_ext = importacion.linea_por_rol("ajuste", "aj_extransito")
    aj_adj = importacion.linea_por_rol("ajuste", "aj_ajuste")
    assert (aj_ext.debe, aj_ext.haber) == (0, 200_000)
    assert (aj_adj.debe, aj_adj.haber) == (200_000, 0)


def test_costeo_valor_linea_copia_los_datos_generales_de_la_importacion(db, empresa):
    from datetime import date

    importacion = _crear_importacion(db, empresa, monto=250_000, pei="39", fecha_pei=date(2026, 3, 1), proveedor_nombre="ACME")
    linea_valor = importacion.linea_por_rol("costeo", "costeo_valor")
    assert linea_valor.debe == 250_000
    assert linea_valor.n_doc == "39"
    assert linea_valor.proveedor == "ACME"
    assert linea_valor.fecha == date(2026, 3, 1)


def test_dif_por_linea_de_costeo_es_haber_menos_ecomex(db, empresa):
    importacion = _crear_importacion(db, empresa)
    linea = importacion.linea_por_rol("costeo", "costeo_invoice")
    linea.haber = 100_000
    linea.ecomex = 90_000
    calculo.recalcular(importacion)
    assert linea.dif == 10_000


def test_descripcion_de_linea_de_plantilla_no_se_puede_editar_a_mano(db, empresa):
    importacion = _crear_importacion(db, empresa)
    assert calculo.es_campo_calculado("costeo", "costeo_invoice", "descripcion") is True
    assert calculo.es_campo_calculado("costeo", None, "descripcion") is False


def test_grupo_esta_cuadrado_y_tiene_descuadre(db, empresa):
    importacion = _crear_importacion(db, empresa)
    importacion.linea_por_rol("factura_agencia", "fa_l1").debe = 100_000
    calculo.recalcular(importacion)
    db.session.commit()
    # factura agencia siempre cuadra sola (el haber se calcula a partir del debe)
    assert calculo.grupo_esta_cuadrado(importacion, "factura_agencia") is True

    # una cuadratura desbalanceada a mano sí debe detectarse
    importacion.linea_por_rol("cuadratura", "cua_deudores").debe = 5_000
    calculo.recalcular(importacion)
    db.session.commit()
    assert calculo.tiene_descuadre(importacion) is True


def test_agregar_lineas_faltantes_no_duplica_las_existentes(db, empresa):
    importacion = _crear_importacion(db, empresa)
    total_costeo = len(importacion.lineas_de("costeo"))
    agregadas = calculo.agregar_lineas_faltantes(importacion, "costeo")
    assert agregadas == 0
    assert len(importacion.lineas_de("costeo")) == total_costeo


# --- Rutas: permisos ---------------------------------------------------


def test_las_rutas_exigen_sesion(client):
    assert client.get("/importaciones/").status_code == 302


def test_bodega_no_tiene_acceso_a_importaciones(client, usuario_bodega):
    login(client, "bodega@test.cl")
    assert client.get("/importaciones/").status_code == 403


def test_admin_ve_el_dashboard_y_las_vistas_principales(client, usuario_admin):
    login(client, "admin@test.cl")
    for ruta in (
        "/importaciones/",
        "/importaciones/resumen",
        "/importaciones/detalle",
        "/importaciones/costeo-detallado",
        "/importaciones/agencias",
        "/importaciones/proveedores",
        "/importaciones/din",
    ):
        respuesta = client.get(ruta)
        assert respuesta.status_code == 200, ruta


# --- Rutas: CRUD de importaciones --------------------------------------


def test_crear_importacion_siembra_los_asientos_y_redirige_al_detalle(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    respuesta = client.post(
        "/importaciones/resumen/nueva",
        data={
            "pei": "39",
            "imp": "1284",
            "proveedor_nombre": "ACME LTD",
            "monto": "1000000",
            "agencia": "DHL",
            "tipo_saldo": "a_favor",
            "saldo_agencia": "0",
            "estado": "pendiente",
        },
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    importacion = Importacion.query.filter_by(empresa_id=empresa.id, pei="39").first()
    assert importacion is not None
    assert len(importacion.lineas) == sum(len(v) for v in calculo.ROW_TEMPLATES.values())
    assert importacion.linea_por_rol("costeo", "costeo_valor").debe == 1_000_000


def test_detalle_por_pei_encuentra_la_importacion_por_numero(client, usuario_admin, empresa, db):
    _crear_importacion(db, empresa, pei="77")
    login(client, "admin@test.cl")
    respuesta = client.get("/importaciones/detalle?pei=77", follow_redirects=False)
    assert respuesta.status_code == 302
    assert "/importaciones/detalle/" in respuesta.headers["Location"]


def test_cuadratura_contable_se_puede_filtrar_por_estado_y_texto(client, usuario_admin, empresa, db):
    _crear_importacion(db, empresa, pei="10", proveedor_nombre="ALMEX CANADA", estado="cerrado")
    _crear_importacion(db, empresa, pei="11", proveedor_nombre="DONGGUAN FANGKUN", estado="pendiente")
    login(client, "admin@test.cl")

    respuesta = client.get("/importaciones/detalle?estado=cerrado")
    texto = respuesta.get_data(as_text=True)
    assert "ALMEX CANADA" in texto
    assert "DONGGUAN FANGKUN" not in texto

    respuesta = client.get("/importaciones/detalle?texto=DONGGUAN")
    texto = respuesta.get_data(as_text=True)
    assert "DONGGUAN FANGKUN" in texto
    assert "ALMEX CANADA" not in texto


def test_cuadratura_contable_lista_muestra_monto_y_oc(client, usuario_admin, empresa, db):
    _crear_importacion(db, empresa, pei="12", proveedor_nombre="ALMEX CANADA", monto=11574390, oc="14541")
    login(client, "admin@test.cl")
    respuesta = client.get("/importaciones/detalle")
    texto = respuesta.get_data(as_text=True)
    assert "11.574.390" in texto
    assert "14541" in texto


def test_secciones_de_asientos_muestran_alerta_de_comprobante_faltante(client, usuario_admin, empresa, db):
    importacion = _crear_importacion(db, empresa, pei="13")
    login(client, "admin@test.cl")

    respuesta = client.get(f"/importaciones/detalle/{importacion.id}")
    texto = respuesta.get_data(as_text=True)
    assert "Sin N° comprobante" in texto

    importacion.meta_de("din").cbte = "4582"
    _db.session.commit()

    respuesta = client.get(f"/importaciones/detalle/{importacion.id}")
    texto = respuesta.get_data(as_text=True)
    assert "N° comprobante 4582" in texto


def test_select_de_estado_en_resumen_tiene_la_clase_de_color_correspondiente(client, usuario_admin, empresa, db):
    _crear_importacion(db, empresa, pei="20", estado="costeando")
    login(client, "admin@test.cl")
    respuesta = client.get("/importaciones/resumen")
    assert 'select-estado estado-costeando' in respuesta.get_data(as_text=True)


def test_filtro_por_mes_no_usa_strftime_y_filtra_bien(client, usuario_admin, empresa, db):
    """func.strftime() no existe en PostgreSQL (producción) y revienta con un 500;
    el filtro debe armarse con extract(), que sí es portable entre motores."""
    from datetime import date

    _crear_importacion(db, empresa, pei="30", proveedor_nombre="ALMEX AGOSTO", fecha_pei=date(2026, 8, 15))
    _crear_importacion(db, empresa, pei="31", proveedor_nombre="ALMEX JULIO", fecha_pei=date(2026, 7, 10))
    login(client, "admin@test.cl")

    for ruta in ("/importaciones/resumen", "/importaciones/detalle", "/importaciones/agencias"):
        respuesta = client.get(ruta, query_string={"mes": "2026-08"})
        assert respuesta.status_code == 200, ruta
        texto = respuesta.get_data(as_text=True)
        assert "ALMEX AGOSTO" in texto, ruta
        assert "ALMEX JULIO" not in texto, ruta


def test_filtro_din_por_mes_no_revienta(client, usuario_admin, empresa, db):
    from datetime import date

    db.session.add(DinRegistro(empresa_id=empresa.id, numero="1", oc="14000", fecha_pago=date(2026, 8, 1)))
    db.session.commit()
    login(client, "admin@test.cl")
    respuesta = client.get("/importaciones/din", query_string={"mes": "2026-08"})
    assert respuesta.status_code == 200


def test_guardar_grupo_recalcula_y_persiste(client, usuario_admin, empresa, db):
    importacion = _crear_importacion(db, empresa)
    fa_l1 = importacion.linea_por_rol("factura_agencia", "fa_l1")
    login(client, "admin@test.cl")

    respuesta = client.post(
        f"/importaciones/detalle/{importacion.id}/grupo/factura_agencia/guardar",
        data={f"linea-{fa_l1.id}-debe": "100000", f"linea-{fa_l1.id}-cuenta": "EX. EN TRANSITO"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200

    _db.session.refresh(importacion)
    fa_iva = importacion.linea_por_rol("factura_agencia", "fa_iva")
    assert fa_iva.debe == 19_000


def test_agregar_y_eliminar_linea_libre(client, usuario_admin, empresa, db):
    importacion = _crear_importacion(db, empresa)
    login(client, "admin@test.cl")
    total_antes = len(importacion.lineas_de("costeo"))

    client.post(f"/importaciones/detalle/{importacion.id}/grupo/costeo/agregar-linea", follow_redirects=True)
    _db.session.refresh(importacion)
    assert len(importacion.lineas_de("costeo")) == total_antes + 1

    nueva = [l for l in importacion.lineas_de("costeo") if l.rol is None][0]
    client.post(f"/importaciones/detalle/linea/{nueva.id}/eliminar", follow_redirects=True)
    _db.session.expire_all()
    assert len(importacion.lineas_de("costeo")) == total_antes


def test_eliminar_importacion(client, usuario_admin, empresa, db):
    importacion = _crear_importacion(db, empresa, pei="88")
    login(client, "admin@test.cl")
    client.post(f"/importaciones/resumen/{importacion.id}/eliminar", follow_redirects=True)
    assert Importacion.query.get(importacion.id) is None


# --- Rutas: proveedores y DIN -------------------------------------------


def test_crud_proveedor_de_importacion(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/importaciones/proveedores/nuevo",
        data={"rut": "46208", "nombre": "NOVO DR LTD", "pais": "ASIA", "tratado_tlc": "NO"},
        follow_redirects=True,
    )
    proveedor = ProveedorImportacion.query.filter_by(empresa_id=empresa.id, nombre="NOVO DR LTD").first()
    assert proveedor is not None

    client.post(
        f"/importaciones/proveedores/{proveedor.id}/editar",
        data={"rut": "46208", "nombre": "NOVO DR LTD CHILE", "pais": "ASIA", "tratado_tlc": "SI"},
        follow_redirects=True,
    )
    _db.session.refresh(proveedor)
    assert proveedor.nombre == "NOVO DR LTD CHILE"
    assert proveedor.tratado_tlc == "SI"

    client.post(f"/importaciones/proveedores/{proveedor.id}/eliminar", follow_redirects=True)
    assert ProveedorImportacion.query.get(proveedor.id) is None


def test_crud_registro_din(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/importaciones/din/nueva",
        data={
            "numero": "1289",
            "oc": "14156",
            "agencia": "UPS",
            "monto_doc_agencia": "386424",
            "proveedor": "MC Master",
            "estado": "pendiente",
            "advalorem": "0",
            "total_pagado": "109170",
        },
        follow_redirects=True,
    )
    registro = DinRegistro.query.filter_by(empresa_id=empresa.id, numero="1289").first()
    assert registro is not None
    assert registro.total_pagado == 109170

    client.post(f"/importaciones/din/{registro.id}/eliminar", follow_redirects=True)
    assert DinRegistro.query.get(registro.id) is None


def test_descarga_excel_de_din(client, usuario_admin, empresa, db):
    _crear_importacion(db, empresa, pei="10", monto=100_000)
    login(client, "admin@test.cl")
    respuesta = client.get("/importaciones/din.xlsx")
    assert respuesta.status_code == 200
    assert "spreadsheetml" in respuesta.headers["Content-Type"]


def test_usuario_normal_no_puede_reabrir_una_importacion_cerrada(client, usuario_admin, empresa, db):
    importacion = _crear_importacion(db, empresa, pei="20", estado="cerrado")
    login(client, "admin@test.cl")

    client.post(
        f"/importaciones/resumen/{importacion.id}/estado",
        data={"estado": "pendiente"},
        follow_redirects=True,
    )
    _db.session.refresh(importacion)
    assert importacion.estado == "cerrado"


def test_superadmin_si_puede_reabrir_una_importacion_cerrada(client, empresa, db):
    importacion = _crear_importacion(db, empresa, pei="21", estado="cerrado")
    superadmin = _crear_superadmin(db, empresa)
    login(client, superadmin.email)

    client.post(
        f"/importaciones/resumen/{importacion.id}/estado",
        data={"estado": "pendiente"},
        follow_redirects=True,
    )
    _db.session.refresh(importacion)
    assert importacion.estado == "pendiente"


def test_resumen_muestra_candado_en_importacion_cerrada_para_usuario_normal(client, usuario_admin, empresa, db):
    _crear_importacion(db, empresa, pei="22", estado="cerrado")
    login(client, "admin@test.cl")
    respuesta = client.get("/importaciones/resumen")
    texto = respuesta.get_data(as_text=True)
    assert "🔒 Cerrado" in texto
    assert 'class="select-estado' not in texto
