"""Costeo por producto: prorrateo de CIF y gastos internos según la planilla de referencia."""

from app.extensions import db as _db
from app.models.activo_fijo import CategoriaActivo
from app.models.costeo_importacion import CosteoImportacion, CosteoImportacionProducto
from app.models.importacion import Importacion, ProveedorImportacion
from app.utils import costeo_importacion_calculo as calculo
from app.utils import importaciones_calculo as importacion_calculo
from tests.conftest import login
from tests.test_permissions import _crear_superadmin


def _crear_costeo(db, empresa, **kwargs):
    costeo = CosteoImportacion(empresa_id=empresa.id, **kwargs)
    db.session.add(costeo)
    db.session.flush()
    calculo.sembrar_lineas_fijas(costeo)
    db.session.commit()
    return costeo


def _crear_importacion(db, empresa, **kwargs):
    datos = {"empresa_id": empresa.id, "monto": 0}
    datos.update(kwargs)
    importacion = Importacion(**datos)
    db.session.add(importacion)
    db.session.flush()
    importacion_calculo.sembrar_lineas_plantilla(importacion)
    importacion_calculo.recalcular(importacion)
    db.session.commit()
    return importacion


def _cargar_ejemplo_real(costeo, db):
    """Reproduce los datos de la planilla PLANILLA_IMP_1299_ALMEX_CANADA.xlsx."""
    inv1 = costeo.documento_por_rol("inv1")
    inv1.valor_tc = 921.42
    inv1.valor_total_inv = 9134.4

    seguro = costeo.documento_por_rol("seguro")
    seguro.valor_tc = 916.97
    seguro.valor_total_inv = 25

    flete = costeo.documento_por_rol("flete_intl")
    flete.valor_tc = 1
    flete.valor_total_inv = 1071938

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


def test_sembrar_lineas_fijas_crea_9_documentos_y_6_gastos(db, empresa):
    """8 documentos de la planilla más la línea de Ad Valorem."""
    costeo = _crear_costeo(db, empresa)
    assert len(costeo.documentos) == len(calculo.DOCUMENTO_ROLES) == 9
    assert len(costeo.gastos_internos) == len(calculo.GASTO_INTERNO_ROLES) == 6


def test_documento_normal_calcula_valor_clp_como_tc_por_monto(db, empresa):
    costeo = _crear_costeo(db, empresa)
    inv1 = costeo.documento_por_rol("inv1")
    inv1.valor_tc = 900
    inv1.valor_total_inv = 1000
    calculo.recalcular(costeo)
    assert inv1.valor_clp == 900_000


def test_flete_internacional_se_calcula_con_tc_y_monto_total_como_los_demas(db, empresa):
    costeo = _crear_costeo(db, empresa)
    flete = costeo.documento_por_rol("flete_intl")
    flete.valor_tc = 900
    flete.valor_total_inv = 1190.0
    calculo.recalcular(costeo)
    assert flete.valor_clp == 1_071_000


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
    assert len(costeo.documentos) == 9
    assert len(costeo.gastos_internos) == 6

    respuesta = client.get(f"/importaciones/costeo-detallado/{costeo.id}")
    assert respuesta.status_code == 200
    assert "Invoice 1" in respuesta.get_data(as_text=True)


def test_lista_de_costeo_se_puede_filtrar_por_columna_y_por_estado(client, usuario_admin, empresa, db):
    _crear_costeo(db, empresa, n_importacion="10", proveedor="ALMEX CANADA", orden_trabajo="OT-10", estado="cerrado")
    _crear_costeo(db, empresa, n_importacion="11", proveedor="DONGGUAN FANGKUN", orden_trabajo="OT-11", estado="en_proceso")
    login(client, "admin@test.cl")

    respuesta = client.get("/importaciones/costeo-detallado", query_string={"f_proveedor": "DONGGUAN"})
    texto = respuesta.get_data(as_text=True)
    assert "DONGGUAN FANGKUN" in texto
    assert "ALMEX CANADA" not in texto

    respuesta = client.get("/importaciones/costeo-detallado", query_string={"filtro": "cerrado"})
    texto = respuesta.get_data(as_text=True)
    assert "ALMEX CANADA" in texto
    assert "DONGGUAN FANGKUN" not in texto


def test_lista_de_costeo_se_puede_ordenar_por_encabezado(client, usuario_admin, empresa, db):
    _crear_costeo(db, empresa, n_importacion="20", proveedor="ZETA")
    _crear_costeo(db, empresa, n_importacion="21", proveedor="ALFA")
    login(client, "admin@test.cl")

    respuesta = client.get("/importaciones/costeo-detallado", query_string={"orden": "proveedor", "dir": "asc"})
    texto = respuesta.get_data(as_text=True)
    assert texto.index("ALFA") < texto.index("ZETA")


def test_datos_generales_se_ven_y_editan_sin_salir_de_la_pagina_del_costeo(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="1299", proveedor="ALMEX CANADA")

    respuesta = client.get(f"/importaciones/costeo-detallado/{costeo.id}")
    texto = respuesta.get_data(as_text=True)
    assert "Datos generales" in texto
    assert 'value="1299"' in texto
    assert 'value="ALMEX CANADA"' in texto

    respuesta = client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/editar",
        data={
            "n_importacion": "1299",
            "proveedor": "ALMEX CANADA SPA",
            "orden_trabajo": "6235-STOCK",
            "tasa_ad_valorem": "6",
            "estado": "en_proceso",
            "importacion_id": "0",
            "din_estado": "",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(f"/importaciones/costeo-detallado/{costeo.id}")

    _db.session.refresh(costeo)
    assert costeo.proveedor == "ALMEX CANADA SPA"


def test_las_secciones_del_costeo_son_plegables(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="1299")

    respuesta = client.get(f"/importaciones/costeo-detallado/{costeo.id}")
    texto = respuesta.get_data(as_text=True)
    for objetivo in ("colapsar-datos-generales", "colapsar-documentos", "colapsar-gastos", "colapsar-productos"):
        assert f'data-bs-target="#{objetivo}"' in texto
        assert f'id="{objetivo}"' in texto


def test_selector_de_proveedor_muestra_los_del_catalogo(client, usuario_admin, empresa, db):
    db.session.add(ProveedorImportacion(empresa_id=empresa.id, nombre="ALMEX CANADA"))
    db.session.add(ProveedorImportacion(empresa_id=empresa.id, nombre="DONGGUAN FANGKUN MACHINERY"))
    db.session.commit()
    login(client, "admin@test.cl")

    respuesta = client.get("/importaciones/costeo-detallado/nueva")
    texto = respuesta.get_data(as_text=True)
    assert '<option value="ALMEX CANADA"' in texto
    assert '<option value="DONGGUAN FANGKUN MACHINERY"' in texto
    assert "Crear nuevo proveedor" in texto


def test_al_guardar_costeo_con_proveedor_nuevo_se_agrega_al_catalogo(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/importaciones/costeo-detallado/nueva",
        data={
            "n_importacion": "1310",
            "proveedor": "NUEVO PROVEEDOR SPA",
            "tasa_ad_valorem": "6",
            "estado": "en_proceso",
            "importacion_id": "0",
        },
        follow_redirects=True,
    )
    proveedor = ProveedorImportacion.query.filter_by(empresa_id=empresa.id, nombre="NUEVO PROVEEDOR SPA").first()
    assert proveedor is not None


def test_proveedor_existente_no_se_duplica_en_el_catalogo(client, usuario_admin, empresa, db):
    db.session.add(ProveedorImportacion(empresa_id=empresa.id, nombre="ALMEX CANADA"))
    db.session.commit()
    login(client, "admin@test.cl")

    client.post(
        "/importaciones/costeo-detallado/nueva",
        data={
            "n_importacion": "1311",
            "proveedor": "almex canada",
            "tasa_ad_valorem": "6",
            "estado": "en_proceso",
            "importacion_id": "0",
        },
        follow_redirects=True,
    )
    assert ProveedorImportacion.query.filter_by(empresa_id=empresa.id).count() == 1


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


def test_selector_de_activo_fijo_muestra_las_categorias_del_catalogo(client, usuario_admin, empresa, db):
    db.session.add(CategoriaActivo(empresa_id=empresa.id, nombre="MAQUINARIAS Y EQUIPOS"))
    db.session.add(CategoriaActivo(empresa_id=empresa.id, nombre="VEHICULOS"))
    db.session.commit()
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="56")
    client.post(f"/importaciones/costeo-detallado/{costeo.id}/productos/agregar", follow_redirects=True)

    respuesta = client.get(f"/importaciones/costeo-detallado/{costeo.id}")
    texto = respuesta.get_data(as_text=True)
    assert '<option value="MAQUINARIAS Y EQUIPOS"' in texto
    assert '<option value="VEHICULOS"' in texto


def test_selector_de_activo_fijo_muestra_el_nombre_y_no_el_codigo_de_cuenta(client, usuario_admin, empresa, db):
    """Si la categoría se llama con el código contable, en la lista se ve la descripción."""
    db.session.add(CategoriaActivo(empresa_id=empresa.id, nombre="1212108001", descripcion="MAQUINARIAS Y EQUIPOS"))
    db.session.add(CategoriaActivo(empresa_id=empresa.id, nombre="1212103001", descripcion="EQUIPOS DE OFICINA"))
    db.session.commit()
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="58")
    client.post(f"/importaciones/costeo-detallado/{costeo.id}/productos/agregar", follow_redirects=True)

    texto = client.get(f"/importaciones/costeo-detallado/{costeo.id}").get_data(as_text=True)
    assert '<option value="1212108001" >MAQUINARIAS Y EQUIPOS</option>' in texto
    # Y quedan ordenadas por ese nombre visible, no por el código.
    assert texto.index(">EQUIPOS DE OFICINA<") < texto.index(">MAQUINARIAS Y EQUIPOS<")


def test_se_puede_marcar_un_producto_con_una_categoria_de_activo_fijo(client, usuario_admin, empresa, db):
    db.session.add(CategoriaActivo(empresa_id=empresa.id, nombre="MUEBLES Y UTILES"))
    db.session.commit()
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="57")
    client.post(f"/importaciones/costeo-detallado/{costeo.id}/productos/agregar", follow_redirects=True)
    _db.session.refresh(costeo)
    producto = costeo.productos[0]

    client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/productos/guardar",
        data={
            f"prod-{producto.id}-producto": "Escritorio",
            f"prod-{producto.id}-valor_unitario_tc": "10",
            f"prod-{producto.id}-cantidad": "2",
            f"prod-{producto.id}-unidad_tc": "USD",
            f"prod-{producto.id}-activo_fijo": "MUEBLES Y UTILES",
        },
        follow_redirects=True,
    )
    _db.session.refresh(producto)
    assert producto.activo_fijo == "MUEBLES Y UTILES"


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


def test_selector_de_moneda_incluye_clp(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="78")
    respuesta = client.get(f"/importaciones/costeo-detallado/{costeo.id}")
    texto = respuesta.get_data(as_text=True)
    assert '<option value="CLP"' in texto


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
        data={"estado": "cerrado"},
        follow_redirects=True,
    )
    _db.session.refresh(costeo)
    assert costeo.estado == "cerrado"


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
    costeo = _crear_costeo(db, empresa, n_importacion="73", estado="en_proceso")
    db.session.commit()
    login(client, "admin@test.cl")

    respuesta = client.get("/importaciones/")
    cuerpo = respuesta.get_data(as_text=True)
    assert "listo" in cuerpo.lower() and "cerrar" in cuerpo.lower()
    assert "1" in cuerpo


def test_costeo_vinculado_a_una_importacion_se_ve_desde_el_detalle_por_pei(client, usuario_admin, empresa, db):
    from app.models.importacion import Importacion
    from app.utils import importaciones_calculo as importaciones_calc

    importacion = Importacion(empresa_id=empresa.id, pei="74", proveedor_nombre="ACME")
    db.session.add(importacion)
    db.session.flush()
    importaciones_calc.sembrar_lineas_plantilla(importacion)
    db.session.commit()

    costeo = _crear_costeo(db, empresa, n_importacion="74", importacion_id=importacion.id, estado="cerrado")
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
        data={"meta-ajuste-cbte": "4582"},
        follow_redirects=True,
    )
    _db.session.refresh(importacion)
    assert importacion.meta_de("ajuste").cbte == "4582"


def test_control_din_ya_no_aparece_en_la_pagina_del_costeo(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="81")

    respuesta = client.get(f"/importaciones/costeo-detallado/{costeo.id}")
    assert "Control DIN" not in respuesta.get_data(as_text=True)

    respuesta = client.get(f"/importaciones/costeo-detallado/{costeo.id}/editar")
    assert "Control DIN" not in respuesta.get_data(as_text=True)


def test_din_historico_sigue_disponible_aunque_no_este_en_el_menu(client, usuario_admin, empresa, db):
    from app.models.importacion import DinRegistro

    db.session.add(DinRegistro(empresa_id=empresa.id, numero="1289", folio="402360883", total_pagado=109170))
    db.session.commit()
    login(client, "admin@test.cl")
    respuesta = client.get("/importaciones/din")
    assert respuesta.status_code == 200
    assert "402360883" in respuesta.get_data(as_text=True)


# --- Sincronización Costeo -> Cuadratura contable vinculada --------------


def test_al_guardar_el_costeo_la_importacion_vinculada_hereda_proveedor_oc_e_imp(client, usuario_admin, empresa, db):
    importacion = _crear_importacion(db, empresa, pei="50")
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="1288")

    client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/editar",
        data={
            "n_importacion": "1288",
            "proveedor": "DONGGUAN FANGKUN MACHINERY",
            "purchase_order": "14152",
            "tasa_ad_valorem": "6",
            "estado": "en_proceso",
            "importacion_id": str(importacion.id),
        },
        follow_redirects=True,
    )
    _db.session.refresh(importacion)
    assert importacion.proveedor_nombre == "DONGGUAN FANGKUN MACHINERY"
    assert importacion.oc == "14152"
    assert importacion.imp == "1288"


def test_generar_cuadratura_desde_costeo_crea_una_importacion_vinculada(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="1300", proveedor="ALMEX CANADA", purchase_order="14400")

    respuesta = client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/generar-cuadratura",
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    _db.session.refresh(costeo)
    assert costeo.importacion_id is not None
    importacion = Importacion.query.get(costeo.importacion_id)
    assert importacion.proveedor_nombre == "ALMEX CANADA"
    assert importacion.oc == "14400"
    assert importacion.imp == "1300"
    assert importacion.pei is None


def test_generar_cuadratura_no_duplica_si_ya_esta_vinculado(client, usuario_admin, empresa, db):
    importacion = _crear_importacion(db, empresa, pei="51")
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="1301", importacion_id=importacion.id)

    client.post(f"/importaciones/costeo-detallado/{costeo.id}/generar-cuadratura", follow_redirects=True)
    _db.session.refresh(costeo)
    assert costeo.importacion_id == importacion.id
    assert Importacion.query.filter_by(empresa_id=empresa.id).count() == 1


def test_bodega_no_puede_generar_cuadratura_desde_costeo(client, usuario_bodega, empresa, db):
    costeo = _crear_costeo(db, empresa, n_importacion="1302")
    login(client, "bodega@test.cl")

    respuesta = client.post(f"/importaciones/costeo-detallado/{costeo.id}/generar-cuadratura")
    assert respuesta.status_code == 403
    _db.session.refresh(costeo)
    assert costeo.importacion_id is None


# --- Un único botón "Guardar todo" ---------------------------------------


def test_pagina_del_costeo_solo_tiene_un_boton_guardar(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="1400")
    respuesta = client.get(f"/importaciones/costeo-detallado/{costeo.id}")
    texto = respuesta.get_data(as_text=True)
    assert "Guardar todo" in texto
    assert "Guardar datos generales" not in texto
    assert "Guardar documentos" not in texto
    assert "Guardar gastos internos" not in texto
    assert "Guardar productos" not in texto


def test_guardar_todo_actualiza_datos_generales_documentos_gastos_y_productos(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="1401")
    inv1 = costeo.documento_por_rol("inv1")
    gasto = costeo.gastos_internos[0]
    db.session.add(CosteoImportacionProducto(costeo=costeo, orden=0, unidad_tc="USD", activo_fijo="NO", tiene_ad_valorem="SI"))
    db.session.commit()
    producto = costeo.productos[0]

    respuesta = client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/guardar",
        data={
            "n_importacion": "1401",
            "proveedor": "ALMEX CANADA",
            "tasa_ad_valorem": "6",
            "estado": "en_proceso",
            "importacion_id": "0",
            f"doc-{inv1.id}-moneda": "USD",
            f"doc-{inv1.id}-valor_tc": "900",
            f"doc-{inv1.id}-valor_total_inv": "1000",
            f"gasto-{gasto.id}-valor_clp": "$61.199",
            f"prod-{producto.id}-producto": "Producto A",
            f"prod-{producto.id}-valor_unitario_tc": "100",
            f"prod-{producto.id}-cantidad": "2",
        },
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    _db.session.refresh(costeo)
    assert costeo.proveedor == "ALMEX CANADA"
    _db.session.refresh(inv1)
    assert inv1.valor_clp == 900_000
    _db.session.refresh(gasto)
    assert gasto.valor_clp == 61199
    _db.session.refresh(producto)
    assert producto.producto == "Producto A"


# --- Bloqueo del estado Cerrado -------------------------------------------


def test_usuario_normal_no_puede_reabrir_un_costeo_cerrado(client, usuario_admin, empresa, db):
    costeo = _crear_costeo(db, empresa, n_importacion="1410", estado="cerrado")
    login(client, "admin@test.cl")

    client.post(f"/importaciones/costeo-detallado/{costeo.id}/estado", data={"estado": "en_proceso"}, follow_redirects=True)
    _db.session.refresh(costeo)
    assert costeo.estado == "cerrado"


def test_superadmin_si_puede_reabrir_un_costeo_cerrado(client, empresa, db):
    costeo = _crear_costeo(db, empresa, n_importacion="1411", estado="cerrado")
    superadmin = _crear_superadmin(db, empresa)
    login(client, superadmin.email)

    client.post(f"/importaciones/costeo-detallado/{costeo.id}/estado", data={"estado": "en_proceso"}, follow_redirects=True)
    _db.session.refresh(costeo)
    assert costeo.estado == "en_proceso"


def test_usuario_normal_no_puede_modificar_un_costeo_cerrado(client, usuario_admin, empresa, db):
    costeo = _crear_costeo(db, empresa, n_importacion="1412", estado="cerrado", proveedor="ALMEX CANADA")
    login(client, "admin@test.cl")

    client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/guardar",
        data={
            "n_importacion": "1412",
            "proveedor": "OTRO PROVEEDOR",
            "tasa_ad_valorem": "6",
            "estado": "cerrado",
            "importacion_id": "0",
        },
        follow_redirects=True,
    )
    _db.session.refresh(costeo)
    assert costeo.proveedor == "ALMEX CANADA"


def test_costeo_cerrado_muestra_candado_y_campos_deshabilitados(client, usuario_admin, empresa, db):
    costeo = _crear_costeo(db, empresa, n_importacion="1413", estado="cerrado")
    login(client, "admin@test.cl")

    respuesta = client.get(f"/importaciones/costeo-detallado/{costeo.id}")
    texto = respuesta.get_data(as_text=True)
    assert "🔒 Cerrado" in texto
    assert "Guardar todo" not in texto


def test_lista_de_costeo_muestra_boton_reabrir_solo_a_superadmin(client, empresa, db):
    _crear_costeo(db, empresa, n_importacion="1414", estado="cerrado")
    superadmin = _crear_superadmin(db, empresa)
    login(client, superadmin.email)

    respuesta = client.get("/importaciones/costeo-detallado")
    assert "Reabrir" in respuesta.get_data(as_text=True)


def test_tabla_de_productos_sigue_el_orden_de_columnas_de_la_planilla(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="1415")
    client.post(f"/importaciones/costeo-detallado/{costeo.id}/productos/agregar", follow_redirects=True)

    texto = client.get(f"/importaciones/costeo-detallado/{costeo.id}").get_data(as_text=True)
    inicio = texto.index('id="productos"')
    cabecera = texto[inicio : texto.index("</thead>", inicio)]
    encabezados = [
        "Producto", "Cód. único", "Valor unit. T/C", "Cantidad", "Unidad T/C", "Activo fijo",
        "EXW", "%", "EXW CLP", "Crating", "Flete", "Seguro", "CIF",
        "¿Ad Valorem?", "Ad Valorem", "% s/ CIF", "TT. Gasto inter.", "Costo total",
        "Costo unit. inicial", "Costo unit. final", "Impacto %",
    ]
    posiciones = [cabecera.index(">" + e) for e in encabezados]
    assert posiciones == sorted(posiciones)


def test_documentos_y_gastos_traen_los_enganches_para_sumar_en_vivo(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="1416")

    texto = client.get(f"/importaciones/costeo-detallado/{costeo.id}").get_data(as_text=True)
    documento = costeo.documentos[0]
    assert f'id="doc-clp-{documento.id}"' in texto
    assert f'data-doc-id="{documento.id}"' in texto
    assert 'id="total-cif"' in texto
    assert 'id="total-gastos-internos"' in texto
    assert "gasto-valor-clp" in texto
    assert 'id="kpi-costo-total"' in texto


def test_ad_valorem_manual_manda_por_sobre_el_calculo_automatico(db, empresa):
    costeo = _crear_costeo(db, empresa)
    _cargar_ejemplo_real(costeo, db)

    producto = costeo.productos[0]
    producto.ad_valorem_manual_clp = 175_020
    _db.session.commit()
    calculo.recalcular(costeo)
    _db.session.commit()

    assert producto.ad_valorem_clp == 175_020
    # Y el costo total lo toma en cuenta.
    assert producto.costo_total_clp == (
        producto.cif_clp + 175_020 + producto.gastos_internos_clp
    )


def test_ad_valorem_manual_vacio_vuelve_al_calculo_automatico(db, empresa):
    costeo = _crear_costeo(db, empresa)
    _cargar_ejemplo_real(costeo, db)

    producto = costeo.productos[0]
    producto.ad_valorem_manual_clp = 999_999
    _db.session.commit()
    calculo.recalcular(costeo)
    _db.session.commit()
    assert producto.ad_valorem_clp == 999_999

    producto.ad_valorem_manual_clp = None
    _db.session.commit()
    calculo.recalcular(costeo)
    _db.session.commit()
    assert abs(producto.ad_valorem_clp - round(producto.cif_clp * 0.06)) <= 1


def test_producto_sin_ad_valorem_ignora_el_monto_manual(db, empresa):
    costeo = _crear_costeo(db, empresa)
    _cargar_ejemplo_real(costeo, db)

    producto = costeo.productos[0]
    producto.tiene_ad_valorem = "NO"
    producto.ad_valorem_manual_clp = 500_000
    _db.session.commit()
    calculo.recalcular(costeo)
    _db.session.commit()
    assert producto.ad_valorem_clp == 0


def test_se_puede_escribir_el_ad_valorem_a_mano_desde_la_pantalla(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="59")
    client.post(f"/importaciones/costeo-detallado/{costeo.id}/productos/agregar", follow_redirects=True)
    _db.session.refresh(costeo)
    producto = costeo.productos[0]

    datos = {
        f"prod-{producto.id}-producto": "ENCHUFE",
        f"prod-{producto.id}-valor_unitario_tc": "100",
        f"prod-{producto.id}-cantidad": "1",
        f"prod-{producto.id}-unidad_tc": "USD",
        f"prod-{producto.id}-activo_fijo": "NO",
        f"prod-{producto.id}-tiene_ad_valorem": "SI",
        f"prod-{producto.id}-ad_valorem_manual_clp": "$175.020",
    }
    client.post(f"/importaciones/costeo-detallado/{costeo.id}/productos/guardar", data=datos, follow_redirects=True)
    _db.session.refresh(producto)
    assert producto.ad_valorem_manual_clp == 175_020
    assert producto.ad_valorem_clp == 175_020

    # Al borrarlo vuelve a calcularse solo.
    datos[f"prod-{producto.id}-ad_valorem_manual_clp"] = ""
    client.post(f"/importaciones/costeo-detallado/{costeo.id}/productos/guardar", data=datos, follow_redirects=True)
    _db.session.refresh(producto)
    assert producto.ad_valorem_manual_clp is None


def test_un_monto_absurdamente_largo_no_rompe_el_guardado(client, usuario_admin, empresa, db):
    """Un número gigante (pegado por error) se acota en vez de tirar un error 500."""
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="60")
    gasto = costeo.gastos_internos[0]

    respuesta = client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/gastos/guardar",
        data={f"gasto-{gasto.id}-valor_clp": "150638150638150624150638"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    _db.session.refresh(gasto)
    assert gasto.valor_clp == 10 ** 15


def test_ad_valorem_es_una_linea_mas_de_documentos_y_queda_fuera_del_cif(db, empresa):
    costeo = _crear_costeo(db, empresa)
    _cargar_ejemplo_real(costeo, db)
    cif_antes = calculo.totales_documentos(costeo)["cif_clp"]

    doc = costeo.documento_por_rol("ad_valorem")
    assert doc is not None, "la línea de Ad Valorem se siembra junto con las demás"
    doc.valor_tc = 894.79
    doc.valor_total_inv = 195.6
    calculo.recalcular(costeo)

    totales = calculo.totales_documentos(costeo)
    assert totales["ad_valorem_clp"] == round(894.79 * 195.6)
    assert totales["cif_clp"] == cif_antes  # el Ad Valorem no infla el CIF
    assert totales["costo_total_clp"] == totales["cif_clp"] + totales["ad_valorem_clp"] + totales["gastos_internos_clp"]


def test_el_ad_valorem_cargado_como_documento_se_reparte_entre_los_productos(db, empresa):
    costeo = _crear_costeo(db, empresa)
    _cargar_ejemplo_real(costeo, db)

    doc = costeo.documento_por_rol("ad_valorem")
    doc.valor_tc = 1
    doc.valor_total_inv = 200000
    calculo.recalcular(costeo)
    _db.session.commit()

    repartido = sum(p.ad_valorem_clp for p in costeo.productos)
    assert abs(repartido - 200000) <= len(costeo.productos)
    # Se reparte proporcional al peso de cada producto, igual que el flete.
    primero = costeo.productos[0]
    assert abs(primero.ad_valorem_clp - 200000 * primero.porcentaje) <= 2


def test_los_productos_exentos_no_reciben_ad_valorem_y_el_resto_absorbe_el_total(db, empresa):
    costeo = _crear_costeo(db, empresa)
    _cargar_ejemplo_real(costeo, db)

    costeo.productos[0].tiene_ad_valorem = "NO"
    doc = costeo.documento_por_rol("ad_valorem")
    doc.valor_tc = 1
    doc.valor_total_inv = 200000
    calculo.recalcular(costeo)
    _db.session.commit()

    assert costeo.productos[0].ad_valorem_clp == 0
    repartido = sum(p.ad_valorem_clp for p in costeo.productos)
    assert abs(repartido - 200000) <= len(costeo.productos)


def test_sin_documento_de_ad_valorem_se_sigue_calculando_con_la_tasa(db, empresa):
    costeo = _crear_costeo(db, empresa)
    _cargar_ejemplo_real(costeo, db)  # deja la línea de Ad Valorem en cero
    producto = costeo.productos[2]
    assert abs(producto.ad_valorem_clp - round(producto.cif_clp * 0.06)) <= 1


def test_agregar_un_producto_conserva_lo_escrito_y_recalcula(client, usuario_admin, empresa, db):
    """El botón '+ Agregar producto' vive dentro del formulario grande: no debe perder lo tipeado."""
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="62")
    client.post(f"/importaciones/costeo-detallado/{costeo.id}/productos/agregar", follow_redirects=True)
    _db.session.refresh(costeo)
    producto = costeo.productos[0]
    inv1 = costeo.documento_por_rol("inv1")
    gasto = costeo.gastos_internos[0]

    # Se escribe en pantalla y, sin guardar, se agrega otra línea.
    client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/productos/agregar",
        data={
            f"doc-{inv1.id}-valor_tc": "900",
            f"doc-{inv1.id}-valor_total_inv": "1000",
            f"gasto-{gasto.id}-valor_clp": "$50.000",
            f"prod-{producto.id}-producto": "ENCHUFE",
            f"prod-{producto.id}-valor_unitario_tc": "100",
            f"prod-{producto.id}-cantidad": "2",
            f"prod-{producto.id}-unidad_tc": "USD",
            f"prod-{producto.id}-activo_fijo": "NO",
            f"prod-{producto.id}-tiene_ad_valorem": "SI",
        },
        follow_redirects=True,
    )
    _db.session.refresh(costeo)
    _db.session.refresh(producto)
    _db.session.refresh(inv1)
    _db.session.refresh(gasto)

    assert len(costeo.productos) == 2
    assert producto.producto == "ENCHUFE"       # no se perdió lo escrito
    assert inv1.valor_clp == 900_000
    assert gasto.valor_clp == 50_000
    assert producto.exw_clp == 900_000          # y quedó recalculado


def test_eliminar_un_producto_conserva_lo_escrito_en_los_demas(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="63")
    for _ in range(2):
        client.post(f"/importaciones/costeo-detallado/{costeo.id}/productos/agregar", follow_redirects=True)
    _db.session.refresh(costeo)
    queda, se_borra = costeo.productos[0], costeo.productos[1]
    inv1 = costeo.documento_por_rol("inv1")

    client.post(
        f"/importaciones/costeo-detallado/producto/{se_borra.id}/eliminar",
        data={
            f"doc-{inv1.id}-valor_tc": "900",
            f"doc-{inv1.id}-valor_total_inv": "1000",
            f"prod-{queda.id}-producto": "SE QUEDA",
            f"prod-{queda.id}-valor_unitario_tc": "50",
            f"prod-{queda.id}-cantidad": "4",
            f"prod-{queda.id}-unidad_tc": "USD",
            f"prod-{queda.id}-activo_fijo": "NO",
            f"prod-{queda.id}-tiene_ad_valorem": "SI",
        },
        follow_redirects=True,
    )
    _db.session.refresh(costeo)
    _db.session.refresh(queda)

    assert len(costeo.productos) == 1
    assert queda.producto == "SE QUEDA"
    assert queda.exw_clp == 900_000  # el que queda absorbe todo el EXW


def test_la_pantalla_muestra_el_porcentaje_real_de_ad_valorem_sobre_el_cif(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="64")
    _cargar_ejemplo_real(costeo, db)
    producto = costeo.productos[0]
    producto.ad_valorem_manual_clp = round(producto.cif_clp * 0.059)
    _db.session.commit()
    calculo.recalcular(costeo)
    _db.session.commit()

    texto = client.get(f"/importaciones/costeo-detallado/{costeo.id}").get_data(as_text=True)
    assert "% s/ CIF" in texto
    assert "5.9%" in texto


def test_responsable_costeo_se_elige_de_una_lista_con_los_ya_usados(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _crear_costeo(db, empresa, n_importacion="65", responsable_costeo="WILRAYLI JIMENEZ")
    costeo = _crear_costeo(db, empresa, n_importacion="66")

    texto = client.get(f"/importaciones/costeo-detallado/{costeo.id}").get_data(as_text=True)
    assert '<option value="WILRAYLI JIMENEZ"' in texto
    assert "Crear nueva persona" in texto


def test_se_puede_escribir_un_responsable_nuevo_y_queda_en_la_lista(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    costeo = _crear_costeo(db, empresa, n_importacion="67")

    client.post(
        f"/importaciones/costeo-detallado/{costeo.id}/guardar",
        data={"n_importacion": "67", "responsable_costeo": "PERSONA NUEVA", "tasa_ad_valorem": "6", "importacion_id": "0"},
        follow_redirects=True,
    )
    _db.session.refresh(costeo)
    assert costeo.responsable_costeo == "PERSONA NUEVA"

    otro = _crear_costeo(db, empresa, n_importacion="68")
    texto = client.get(f"/importaciones/costeo-detallado/{otro.id}").get_data(as_text=True)
    assert '<option value="PERSONA NUEVA"' in texto
