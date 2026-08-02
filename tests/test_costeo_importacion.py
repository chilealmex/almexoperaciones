"""Costeo por producto: prorrateo de CIF y gastos internos según la planilla de referencia."""

from app.extensions import db as _db
from app.models.costeo_importacion import CosteoImportacion, CosteoImportacionProducto
from app.utils import costeo_importacion_calculo as calculo
from tests.conftest import login


def _crear_costeo(db, empresa, **kwargs):
    costeo = CosteoImportacion(empresa_id=empresa.id, **kwargs)
    db.session.add(costeo)
    db.session.flush()
    calculo.sembrar_lineas_fijas(costeo)
    db.session.commit()
    return costeo


def _cargar_ejemplo_real(costeo, db):
    """Reproduce los datos de la planilla PLANILLA_IMP_1299_ALMEX_CANADA.xlsx."""
    inv1 = costeo.documento_por_rol("inv1")
    inv1.valor_tc = 921.42
    inv1.valor_total_inv = 9134.4

    seguro = costeo.documento_por_rol("seguro")
    seguro.valor_tc = 916.97
    seguro.valor_total_inv = 25

    flete = costeo.documento_por_rol("flete_intl")
    flete.valor_clp = 1071938  # entrada directa, sin T/C

    crating_usd = costeo.documento_por_rol("crating_usd")
    crating_usd.valor_tc = 921.42
    crating_usd.valor_total_inv = 184.83

    costeo.gasto_por_rol("almacenaje").valor_clp = 60340
    costeo.gasto_por_rol("desconsolidacion").valor_clp = 145000
    costeo.gasto_por_rol("flete_nacional").valor_clp = 95000
    costeo.gasto_por_rol("gastos_agencia").valor_clp = 120000

    productos_ejemplo = [
        ("CABLE DE ALIMENTACIÓN OT 6235", "46044-022", 534.8, 2),
        ("CABLE DE ALIMENTACIÓN", "46044-022", 534.8, 5),
        ("FILTRO COMPLETO", "24512-001", 33.12, 5),
        ("VALVULA DE RETENCIÓN", "22125-001", 78.8, 5),
        ("MANGUERA DE PRESIÓN", "20022-224-1", 2.88, 300),
        ("SONDA DE TEMPERATURA", "29071-006", 59.36, 25),
        ("MANGUERA ALTA TEMPERATURA", "20022-222-1", 3.2, 600),
        ("TAPA DE PERNO EB - NEGRA", "29348-010", 1.76, 100),
        ("TAPA DE PERNO EB - AMARILLA", "29348-012", 1.76, 100),
        ("QUICK RELEASE PIN", "28228-052", 2.64, 80),
    ]
    for orden, (nombre, codigo, valor_unitario, cantidad) in enumerate(productos_ejemplo):
        db.session.add(
            CosteoImportacionProducto(
                costeo=costeo, orden=orden, producto=nombre, codigo=codigo,
                valor_unitario_tc=valor_unitario, cantidad=cantidad, unidad_tc="USD", activo_fijo="NO",
            )
        )
    db.session.commit()
    calculo.recalcular(costeo)
    db.session.commit()


# --- Lógica de cálculo ---------------------------------------------------


def test_sembrar_lineas_fijas_crea_8_documentos_y_6_gastos(db, empresa):
    costeo = _crear_costeo(db, empresa)
    assert len(costeo.documentos) == len(calculo.DOCUMENTO_ROLES) == 8
    assert len(costeo.gastos_internos) == len(calculo.GASTO_INTERNO_ROLES) == 6


def test_documento_normal_calcula_valor_clp_como_tc_por_monto(db, empresa):
    costeo = _crear_costeo(db, empresa)
    inv1 = costeo.documento_por_rol("inv1")
    inv1.valor_tc = 900
    inv1.valor_total_inv = 1000
    calculo.recalcular(costeo)
    assert inv1.valor_clp == 900_000


def test_documento_directo_no_usa_formula(db, empresa):
    costeo = _crear_costeo(db, empresa)
    flete = costeo.documento_por_rol("flete_intl")
    flete.valor_clp = 1_071_938
    calculo.recalcular(costeo)
    assert flete.valor_clp == 1_071_938  # no se pisa con una fórmula


def test_ejemplo_real_reparte_el_exw_correctamente(db, empresa):
    costeo = _crear_costeo(db, empresa)
    _cargar_ejemplo_real(costeo, db)

    # Sin diferencia entre lo declarado en los documentos y lo repartido a productos.
    assert abs(calculo.diferencia_cuadratura(costeo)) < 0.01

    # Los porcentajes de participación de todos los productos deben sumar 1.
    suma_porcentajes = sum(p.porcentaje for p in costeo.productos)
    assert abs(suma_porcentajes - 1) < 0.001

    # El primer producto (2 unidades de USD 534.80) pesa igual que el segundo (5 unidades)
    # en proporción a su EXW: ambos parten del mismo valor unitario.
    primero, segundo = costeo.productos[0], costeo.productos[1]
    assert primero.costo_unitario_final_clp == segundo.costo_unitario_final_clp

    # CIF de cada producto = EXW + crating + flete + seguro (con margen de redondeo por línea:
    # cada componente se redondea a peso entero por separado antes de sumarlos).
    for p in costeo.productos:
        assert abs(p.cif_clp - (p.exw_clp + p.crating_clp + p.flete_clp + p.seguro_clp)) <= 2

    # Costo total = CIF + ad valorem + gastos internos.
    for p in costeo.productos:
        assert abs(p.costo_total_clp - (p.cif_clp + p.ad_valorem_clp + p.gastos_internos_clp)) <= 2

    # Ad Valorem por defecto es 6% del CIF de cada producto.
    tercero = costeo.productos[2]
    assert abs(tercero.ad_valorem_clp - round(tercero.cif_clp * 0.06)) <= 1

    # La suma de los costos totales de todos los productos debe cuadrar con CIF + gastos
    # internos + el ad valorem total (que "totales_documentos" no incluye, porque el ad
    # valorem solo se calcula a nivel de cada producto).
    totales = calculo.totales_documentos(costeo)
    suma_costo_total = sum(p.costo_total_clp for p in costeo.productos)
    suma_ad_valorem = sum(p.ad_valorem_clp for p in costeo.productos)
    esperado = totales["cif_clp"] + totales["gastos_internos_clp"] + suma_ad_valorem
    assert abs(suma_costo_total - esperado) <= len(costeo.productos)


def test_tratado_libre_comercio_exento_no_aplica_ad_valorem(db, empresa):
    costeo = _crear_costeo(db, empresa, tasa_ad_valorem=0)
    _cargar_ejemplo_real(costeo, db)
    assert all(p.ad_valorem_clp == 0 for p in costeo.productos)


def test_producto_marcado_sin_ad_valorem_queda_en_cero_y_no_afecta_a_los_demas(db, empresa):
    costeo = _crear_costeo(db, empresa)
    _cargar_ejemplo_real(costeo, db)

    sin_advalorem = costeo.productos[0]
    otro = costeo.productos[1]
    cif_otro_antes = otro.cif_clp
    ad_valorem_otro_antes = otro.ad_valorem_clp

    sin_advalorem.tiene_ad_valorem = "NO"
    _db.session.commit()
    calculo.recalcular(costeo)
    _db.session.commit()

    assert sin_advalorem.ad_valorem_clp == 0
    # El resto de los productos sigue prorrateando el CIF y su propio ad valorem igual que antes.
    assert otro.cif_clp == cif_otro_antes
    assert otro.ad_valorem_clp == ad_valorem_otro_antes


def test_producto_sin_cantidad_no_revienta_el_calculo(db, empresa):
    costeo = _crear_costeo(db, empresa)
    db.session.add(CosteoImportacionProducto(costeo=costeo, orden=0, producto="Sin cantidad", cantidad=0))
    db.session.commit()
    calculo.recalcular(costeo)
    producto = costeo.productos[0]
    assert producto.costo_unitario_final_clp == 0
    assert producto.impacto_pct == 0


# --- Rutas ---------------------------------------------------------------


def test_bodega_no_puede_ver_costeo_detallado(client, usuario_bodega):
    login(client, "bodega@test.cl")
    assert client.get("/importaciones/costeo-detallado").status_code == 403


def test_admin_crea_y_ve_costeo_detallado(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    respuesta = client.post(
        "/importaciones/costeo-detallado/nueva",
        data={
            "n_importacion": "1299",
            "proveedor": "ALMEX CANADA",
            "orden_trabajo": "6235-6249-STOCK",
            "tasa_ad_valorem": "6",
        },
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    costeo = CosteoImportacion.query.filter_by(empresa_id=empresa.id, n_importacion="1299").first()
    assert costeo is not None
    assert costeo.tasa_ad_valorem == 0.06
    assert len(costeo.documentos) == 8
    assert len(costeo.gastos_internos) == 6

    respuesta = client.get(f"/importaciones/costeo-detallado/{costeo.id}")
    assert respuesta.status_code == 200
    assert "Invoice 1" in respuesta.get_data(as_text=True)


def test_agregar_editar_y_eliminar_producto_por_ruta(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="55")

    client.post(f"/importaciones/costeo-detallado/{costeo.id}/productos/agregar", follow_redirects=True)
    _db.session.refresh(costeo)
    assert len(costeo.productos) == 1
    producto = costeo.productos[0]

    client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/productos/guardar",
        data={
            f"prod-{producto.id}-producto": "Manguera",
            f"prod-{producto.id}-codigo": "COD-1",
            f"prod-{producto.id}-valor_unitario_tc": "10",
            f"prod-{producto.id}-cantidad": "20",
            f"prod-{producto.id}-unidad_tc": "USD",
            f"prod-{producto.id}-activo_fijo": "NO",
        },
        follow_redirects=True,
    )
    _db.session.refresh(producto)
    assert producto.producto == "Manguera"
    assert producto.exw_moneda == 200  # 10 * 20

    client.post(f"/importaciones/costeo-detallado/producto/{producto.id}/eliminar", follow_redirects=True)
    _db.session.refresh(costeo)
    assert len(costeo.productos) == 0


def test_marcar_producto_sin_ad_valorem_por_ruta_lo_deja_en_cero(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="88")
    _cargar_ejemplo_real(costeo, db)
    producto = costeo.productos[0]
    assert producto.ad_valorem_clp > 0  # por defecto viene en "SI"

    client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/productos/guardar",
        data={
            f"prod-{producto.id}-producto": producto.producto,
            f"prod-{producto.id}-codigo": producto.codigo,
            f"prod-{producto.id}-valor_unitario_tc": str(producto.valor_unitario_tc),
            f"prod-{producto.id}-cantidad": str(producto.cantidad),
            f"prod-{producto.id}-unidad_tc": "USD",
            f"prod-{producto.id}-activo_fijo": "NO",
            f"prod-{producto.id}-tiene_ad_valorem": "NO",
        },
        follow_redirects=True,
    )
    _db.session.refresh(producto)
    assert producto.tiene_ad_valorem == "NO"
    assert producto.ad_valorem_clp == 0


def test_guardar_documentos_recalcula_totales(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="77")
    inv1 = costeo.documento_por_rol("inv1")

    client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/documentos/guardar",
        data={
            f"doc-{inv1.id}-moneda": "USD",
            f"doc-{inv1.id}-nro_doc": "101262",
            f"doc-{inv1.id}-valor_tc": "900",
            f"doc-{inv1.id}-valor_total_inv": "1000",
        },
        follow_redirects=True,
    )
    _db.session.refresh(inv1)
    assert inv1.valor_clp == 900_000


def test_eliminar_costeo_completo(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="99")
    client.post(f"/importaciones/costeo-detallado/{costeo.id}/eliminar", follow_redirects=True)
    assert CosteoImportacion.query.get(costeo.id) is None


# --- Flujo: estado del costeo y enlace con Detalle por PEI ----------------


def test_costeo_nuevo_queda_en_proceso_por_defecto(db, empresa):
    costeo = _crear_costeo(db, empresa, n_importacion="70")
    assert costeo.estado == "en_proceso"


def test_cambiar_estado_del_costeo_por_ruta(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="71")

    client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/estado",
        data={"estado": "listo"},
        follow_redirects=True,
    )
    _db.session.refresh(costeo)
    assert costeo.estado == "listo"


def test_cambiar_a_estado_invalido_no_se_aplica(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="72")

    client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/estado",
        data={"estado": "no_existe"},
        follow_redirects=True,
    )
    _db.session.refresh(costeo)
    assert costeo.estado == "en_proceso"


def test_dashboard_alerta_costeos_listos_para_contabilizar(client, usuario_admin, empresa, db):
    from app.models.importacion import Importacion

    costeo = _crear_costeo(db, empresa, n_importacion="73", estado="listo")
    db.session.commit()
    login(client, "admin@test.cl")

    respuesta = client.get("/importaciones/")
    cuerpo = respuesta.get_data(as_text=True)
    assert "Listo para contabilizar" in cuerpo
    assert "1" in cuerpo


def test_costeo_vinculado_a_una_importacion_se_ve_desde_el_detalle_por_pei(client, usuario_admin, empresa, db):
    from app.models.importacion import Importacion
    from app.utils import importaciones_calculo as importaciones_calc

    importacion = Importacion(empresa_id=empresa.id, pei="74", proveedor_nombre="ACME")
    db.session.add(importacion)
    db.session.flush()
    importaciones_calc.sembrar_lineas_plantilla(importacion)
    db.session.commit()

    costeo = _crear_costeo(db, empresa, n_importacion="74", importacion_id=importacion.id, estado="listo")
    login(client, "admin@test.cl")

    respuesta = client.get(f"/importaciones/detalle/{importacion.id}")
    cuerpo = respuesta.get_data(as_text=True)
    assert "Costeo vinculado" in cuerpo
    assert f"/importaciones/costeo-detallado/{costeo.id}" in cuerpo

    respuesta = client.get(f"/importaciones/costeo-detallado/{costeo.id}")
    cuerpo = respuesta.get_data(as_text=True)
    assert f"/importaciones/detalle/{importacion.id}" in cuerpo


def test_traer_costeo_producto_copia_los_montos_al_asiento_costeo(client, usuario_admin, empresa, db):
    from app.models.importacion import Importacion
    from app.utils import importaciones_calculo as importaciones_calc

    importacion = Importacion(empresa_id=empresa.id, pei="75", proveedor_nombre="ACME", monto=1_000_000)
    db.session.add(importacion)
    db.session.flush()
    importaciones_calc.sembrar_lineas_plantilla(importacion)
    db.session.commit()

    costeo = _crear_costeo(db, empresa, n_importacion="75", importacion_id=importacion.id)
    _cargar_ejemplo_real(costeo, db)  # trae invoice, seguro, flete, crating y gastos internos reales

    login(client, "admin@test.cl")
    client.post(
        f"/importaciones/detalle/{importacion.id}/grupo/costeo/traer-costeo-producto",
        follow_redirects=True,
    )

    _db.session.refresh(importacion)
    linea_invoice = importacion.linea_por_rol("costeo", "costeo_invoice")
    linea_seguro = importacion.linea_por_rol("costeo", "costeo_seguro")
    linea_flete = importacion.linea_por_rol("costeo", "costeo_fleteintl")
    linea_almacenaje = importacion.linea_por_rol("costeo", "costeo_almacenaje")

    totales = calculo.totales_documentos(costeo)
    assert linea_invoice.haber == totales["exw_clp"]
    assert linea_seguro.haber == totales["seguro_clp"]
    assert linea_flete.haber == totales["flete_clp"]
    assert linea_almacenaje.haber == 60340

    # El asiento se recalcula: la diferencia de costeo debe reflejar el nuevo total.
    assert importacion.costeo_suma == sum(
        (importacion.linea_por_rol("costeo", rol).haber or 0)
        for rol in (
            "costeo_invoice", "costeo_seguro", "costeo_fleteintl", "costeo_crating",
            "costeo_advalorem", "costeo_almacenaje", "costeo_desconsolidacion",
            "costeo_habilitacion", "costeo_fletenacional", "costeo_gastosagencia",
            "costeo_cargoterminal",
        )
    )


def test_traer_costeo_producto_sin_vinculo_avisa_y_no_falla(client, usuario_admin, empresa, db):
    from app.models.importacion import Importacion
    from app.utils import importaciones_calculo as importaciones_calc

    importacion = Importacion(empresa_id=empresa.id, pei="76")
    db.session.add(importacion)
    db.session.flush()
    importaciones_calc.sembrar_lineas_plantilla(importacion)
    db.session.commit()

    login(client, "admin@test.cl")
    respuesta = client.post(
        f"/importaciones/detalle/{importacion.id}/grupo/costeo/traer-costeo-producto",
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "no tiene un Costeo vinculado" in respuesta.get_data(as_text=True)


# --- Costeo (asientos) eliminado, y control DIN unificado en Costeo -------


def test_submodulo_costeo_asientos_ya_no_existe(client, usuario_admin):
    login(client, "admin@test.cl")
    assert client.get("/importaciones/costeo").status_code == 404
    assert client.get("/importaciones/costeo/matriz.xlsx").status_code == 404


def test_se_puede_editar_el_cbte_del_ajuste_desde_cuadratura_contable(client, usuario_admin, empresa, db):
    from app.models.importacion import Importacion
    from app.utils import importaciones_calculo as importaciones_calc

    importacion = Importacion(empresa_id=empresa.id, pei="80")
    db.session.add(importacion)
    db.session.flush()
    importaciones_calc.sembrar_lineas_plantilla(importacion)
    db.session.commit()

    login(client, "admin@test.cl")
    client.post(
        f"/importaciones/detalle/{importacion.id}/grupo/ajuste/guardar",
        data={"meta-cbte": "4582"},
        follow_redirects=True,
    )
    _db.session.refresh(importacion)
    assert importacion.meta_de("ajuste").cbte == "4582"


def test_campos_din_se_guardan_dentro_del_costeo(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/importaciones/costeo-detallado/nueva",
        data={
            "n_importacion": "81",
            "din_agencia": "UPS",
            "din_folio": "402360883",
            "din_estado": "pagado",
            "din_total_pagado": "109170",
        },
        follow_redirects=True,
    )
    costeo = CosteoImportacion.query.filter_by(empresa_id=empresa.id, n_importacion="81").first()
    assert costeo is not None
    assert costeo.din_agencia == "UPS"
    assert costeo.din_folio == "402360883"
    assert costeo.din_estado == "pagado"
    assert costeo.din_total_pagado == 109170

    respuesta = client.get(f"/importaciones/costeo-detallado/{costeo.id}")
    cuerpo = respuesta.get_data(as_text=True)
    assert "Control DIN" in cuerpo
    assert "402360883" in cuerpo


def test_din_historico_sigue_disponible_aunque_no_este_en_el_menu(client, usuario_admin, empresa, db):
    from app.models.importacion import DinRegistro

    db.session.add(DinRegistro(empresa_id=empresa.id, numero="1289", folio="402360883", total_pagado=109170))
    db.session.commit()
    login(client, "admin@test.cl")
    respuesta = client.get("/importaciones/din")
    assert respuesta.status_code == 200
    assert "402360883" in respuesta.get_data(as_text=True)
