"""Definición central del menú de la aplicación.

La barra superior muestra los módulos y, justo debajo, una segunda barra con los
submódulos del módulo activo. Cada entrada declara los endpoints que le
pertenecen para poder marcar el elemento activo sin que cada plantilla tenga que
indicarlo a mano.
"""

MODULOS = (
    {
        "clave": "inicio",
        "etiqueta": "Inicio",
        "icono": "🏠",
        "permiso": None,
        "endpoint": "core.dashboard",
        "endpoints": ("core.dashboard",),
        "submodulos": (),
    },
    {
        "clave": "inventario",
        "etiqueta": "Inventario",
        "icono": "📦",
        "permiso": "inventario",
        "endpoint": "inventario.resumen",
        "endpoints": (),
        "submodulos": (
            {
                "clave": "resumen",
                "etiqueta": "Resumen",
                "endpoint": "inventario.resumen",
                "endpoints": ("inventario.resumen",),
            },
            {
                "clave": "stock",
                "etiqueta": "Stock y conteo",
                "endpoint": "inventario.stock",
                "endpoints": ("inventario.stock", "inventario.stock_contar"),
            },
            {
                "clave": "ajuste",
                "etiqueta": "Ajuste inventario",
                "endpoint": "inventario.ajuste",
                "endpoints": ("inventario.ajuste", "inventario.ajuste_csv"),
            },
            {
                "clave": "cruce_datos",
                "etiqueta": "Cruce de datos",
                "endpoint": "inventario.cruce_datos",
                "endpoints": ("inventario.cruce_datos",),
            },
            {
                "clave": "historial_tomas",
                "etiqueta": "Historial de tomas",
                "endpoint": "inventario.historial",
                "endpoints": ("inventario.historial", "inventario.historial_detalle", "inventario.historial_excel"),
            },
            {
                "clave": "importar",
                "etiqueta": "Importar",
                "accion": "editar",
                "endpoint": "inventario.conteo_importar",
                "endpoints": (
                    "inventario.conteo_importar",
                    "inventario.conteo_importar_qms",
                    "inventario.conteo_importar_defontana",
                ),
            },
        ),
    },
    {
        "clave": "contratos",
        "etiqueta": "Contratos",
        "icono": "📄",
        "permiso": "contratos",
        "endpoint": "contratos.resumen",
        "endpoints": (),
        "submodulos": (
            {
                "clave": "resumen",
                "etiqueta": "Resumen",
                "endpoint": "contratos.resumen",
                "endpoints": ("contratos.resumen",),
            },
            {
                "clave": "contratos",
                "etiqueta": "Contratos",
                "endpoint": "contratos.contratos",
                "endpoints": (
                    "contratos.contratos",
                    "contratos.nuevo_contrato",
                    "contratos.ver_contrato",
                    "contratos.editar_contrato",
                    "contratos.renovar_contrato",
                    "contratos.terminar_contrato",
                    "contratos.subir_documento",
                ),
            },
            {
                "clave": "arriendos",
                "etiqueta": "Arriendos",
                "endpoint": "arriendos.index",
                "endpoints": (
                    "arriendos.index",
                    "arriendos.nuevo_arriendo_salida",
                    "arriendos.ver_arriendo_salida",
                    "arriendos.subir_documento_salida",
                    "arriendos.firmar_arriendo_salida",
                    "arriendos.ver_firma_salida",
                    "arriendos.devolver_arriendo_salida",
                    "arriendos.nueva_facturacion_salida",
                    "arriendos.marcar_facturacion_pagada",
                    "arriendos.nuevo_arriendo_entrada",
                    "arriendos.ver_arriendo_entrada",
                    "arriendos.terminar_arriendo_entrada",
                    "arriendos.nuevo_pago_entrada",
                    "arriendos.marcar_pago_realizado",
                ),
            },
            {
                "clave": "generados",
                "etiqueta": "Generar contrato",
                "endpoint": "contratos.generados",
                "endpoints": (
                    "contratos.generados",
                    "contratos.nuevo_generado",
                    "contratos.editar_generado",
                    "contratos.ver_generado",
                ),
            },
        ),
    },
    {
        "clave": "activos_fijos",
        "etiqueta": "Activos fijos",
        "icono": "🏷️",
        "permiso": "activos_fijos",
        "endpoint": "activos_fijos.resumen",
        "endpoints": (),
        "submodulos": (
            {
                "clave": "resumen",
                "etiqueta": "Resumen",
                "endpoint": "activos_fijos.resumen",
                "endpoints": ("activos_fijos.resumen",),
            },
            {
                "clave": "activos",
                "etiqueta": "Activos",
                "endpoint": "activos_fijos.activos",
                "endpoints": (
                    "activos_fijos.activos",
                    "activos_fijos.nuevo_activo",
                    "activos_fijos.ver_activo",
                    "activos_fijos.editar_activo",
                    "activos_fijos.dar_de_baja",
                    "activos_fijos.subir_documento",
                ),
            },
            {
                "clave": "depreciacion",
                "etiqueta": "Depreciación",
                "endpoint": "activos_fijos.depreciacion",
                "endpoints": ("activos_fijos.depreciacion",),
            },
            {
                "clave": "categorias",
                "etiqueta": "Categorías",
                "endpoint": "activos_fijos.categorias",
                "endpoints": (
                    "activos_fijos.categorias",
                    "activos_fijos.nueva_categoria",
                    "activos_fijos.eliminar_categoria",
                ),
            },
        ),
    },
    {
        "clave": "datos_maestros",
        "etiqueta": "Datos maestros",
        "icono": "🗂️",
        "permiso": "datos_maestros",
        "endpoint": "datos_maestros.resumen",
        "endpoints": (),
        "submodulos": (
            {
                "clave": "resumen",
                "etiqueta": "Resumen",
                "endpoint": "datos_maestros.resumen",
                "endpoints": ("datos_maestros.resumen",),
            },
            {
                "clave": "clientes",
                "etiqueta": "Clientes",
                "endpoint": "datos_maestros.clientes",
                "endpoints": (
                    "datos_maestros.clientes",
                    "datos_maestros.nuevo_cliente",
                    "datos_maestros.editar_cliente",
                ),
            },
            {
                "clave": "proveedores",
                "etiqueta": "Proveedores",
                "endpoint": "datos_maestros.proveedores",
                "endpoints": (
                    "datos_maestros.proveedores",
                    "datos_maestros.nuevo_proveedor",
                    "datos_maestros.editar_proveedor",
                ),
            },
            {
                "clave": "importar",
                "etiqueta": "Importar",
                "accion": "editar",
                "endpoint": "datos_maestros.importar",
                "endpoints": ("datos_maestros.importar",),
            },
        ),
    },
    {
        "clave": "importaciones",
        "etiqueta": "Importaciones",
        "icono": "🚢",
        "permiso": "importaciones",
        "endpoint": "importaciones.dashboard",
        "endpoints": ("importaciones.dashboard",),
        "submodulos": (
            {
                "clave": "resumen",
                "etiqueta": "Resumen",
                "endpoint": "importaciones.resumen",
                "endpoints": (
                    "importaciones.resumen",
                    "importaciones.nueva_importacion",
                    "importaciones.editar_importacion",
                    "importaciones.cambiar_estado",
                    "importaciones.eliminar_importacion",
                ),
            },
            {
                "clave": "detalle",
                "etiqueta": "Cuadratura contable",
                "endpoint": "importaciones.detalle_index",
                "endpoints": (
                    "importaciones.detalle_index",
                    "importaciones.detalle",
                    "importaciones.guardar_grupo",
                    "importaciones.agregar_linea",
                    "importaciones.completar_plantilla",
                    "importaciones.traer_costeo_producto",
                    "importaciones.eliminar_linea",
                ),
            },
            {
                "clave": "costeo_detallado",
                "etiqueta": "Costeo",
                "endpoint": "importaciones.costeo_detallado_lista",
                "endpoints": (
                    "importaciones.costeo_detallado_lista",
                    "importaciones.nuevo_costeo_detallado",
                    "importaciones.editar_costeo_detallado",
                    "importaciones.eliminar_costeo_detallado",
                    "importaciones.ver_costeo_detallado",
                    "importaciones.cambiar_estado_costeo",
                    "importaciones.guardar_documentos_costeo",
                    "importaciones.guardar_gastos_costeo",
                    "importaciones.guardar_productos_costeo",
                    "importaciones.agregar_producto_costeo",
                    "importaciones.eliminar_producto_costeo",
                ),
            },
            {
                "clave": "agencias",
                "etiqueta": "Agencias",
                "endpoint": "importaciones.agencias",
                "endpoints": ("importaciones.agencias",),
            },
            {
                "clave": "proveedores",
                "etiqueta": "Proveedores",
                "endpoint": "importaciones.proveedores",
                "endpoints": (
                    "importaciones.proveedores",
                    "importaciones.nuevo_proveedor",
                    "importaciones.editar_proveedor",
                    "importaciones.eliminar_proveedor",
                ),
            },
        ),
    },
    {
        "clave": "contabilidad",
        "etiqueta": "Contabilidad",
        "icono": "📒",
        "permiso": "contabilidad",
        "endpoint": "contabilidad.provision_ingresos",
        "endpoints": ("contabilidad.index",),
        "submodulos": (
            {
                "clave": "provision_ingresos",
                "etiqueta": "Provisión de Ingresos",
                "endpoint": "contabilidad.provision_ingresos",
                "endpoints": (
                    "contabilidad.provision_ingresos",
                    "contabilidad.importar_provision_ingresos",
                    "contabilidad.guardar_provision_ingresos",
                    "contabilidad.eliminar_provision_ingreso",
                    "contabilidad.exportar_provision_ingresos",
                ),
            },
            {
                "clave": "dif_tc",
                "etiqueta": "Dif TC PR/CL",
                "endpoint": "contabilidad.dif_tc",
                "endpoints": (
                    "contabilidad.dif_tc",
                    "contabilidad.nuevo_periodo_dif_tc",
                    "contabilidad.ver_periodo_dif_tc",
                    "contabilidad.importar_mayor_dif_tc",
                    "contabilidad.guardar_periodo_dif_tc",
                    "contabilidad.cambiar_estado_dif_tc",
                    "contabilidad.eliminar_periodo_dif_tc",
                    "contabilidad.exportar_periodo_dif_tc",
                ),
            },
        ),
    },
    {
        "clave": "admin",
        "etiqueta": "Usuarios",
        "icono": "👥",
        "permiso": "admin",
        "endpoint": "admin.usuarios",
        "endpoints": (
            "admin.usuarios",
            "admin.nuevo_usuario",
            "admin.editar_usuario",
            "admin.permisos_usuario",
        ),
        "submodulos": (),
    },
)


def _construir_endpoint_a_submodulo():
    """Índice endpoint -> (módulo, submódulo) para exigir permiso a nivel de submódulo."""
    indice = {}
    for modulo in MODULOS:
        for submodulo in modulo["submodulos"]:
            for endpoint in submodulo["endpoints"]:
                indice[endpoint] = (modulo["clave"], submodulo["clave"])
    return indice


# Se calcula una sola vez al importar: los endpoints de cada submódulo no cambian en caliente.
ENDPOINT_A_SUBMODULO = _construir_endpoint_a_submodulo()


def _endpoints_del_modulo(modulo):
    endpoints = set(modulo["endpoints"])
    for submodulo in modulo["submodulos"]:
        endpoints.update(submodulo["endpoints"])
    return endpoints


def _es_visible(modulo, submodulo, puede):
    """Un módulo sin permiso declarado es público; el submódulo hereda el del módulo."""
    permiso = modulo["permiso"]
    if permiso is None:
        return True
    accion = (submodulo or modulo).get("accion", "ver")
    clave_submodulo = submodulo["clave"] if submodulo else None
    return puede(permiso, accion, submodulo=clave_submodulo)


def construir_navegacion(endpoint, puede):
    """Arma el menú visible para el usuario actual y marca el módulo/submódulo activo."""
    modulos = []
    modulo_activo = None
    submodulos = []

    for modulo in MODULOS:
        if not _es_visible(modulo, None, puede):
            continue

        activo = endpoint in _endpoints_del_modulo(modulo)
        modulos.append(
            {
                "clave": modulo["clave"],
                "etiqueta": modulo["etiqueta"],
                "icono": modulo["icono"],
                "endpoint": modulo["endpoint"],
                "activo": activo,
                # Cada módulo lleva sus propios submódulos, para poder mostrarlos
                # todos en el menú del celular: ahí no hay un módulo "abierto" al
                # costado, así que si solo se listaran los del módulo activo no
                # habría forma de llegar a los demás.
                "submodulos": [
                    {
                        "clave": sub["clave"],
                        "etiqueta": sub["etiqueta"],
                        "endpoint": sub["endpoint"],
                        "activo": endpoint in sub["endpoints"],
                    }
                    for sub in modulo["submodulos"]
                    if _es_visible(modulo, sub, puede)
                ],
            }
        )

        if not activo:
            continue

        modulo_activo = modulos[-1]
        submodulos.extend(modulos[-1]["submodulos"])

    return {
        "modulos": modulos,
        "modulo_activo": modulo_activo,
        "submodulos": submodulos,
    }
