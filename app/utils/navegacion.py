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
                "clave": "productos",
                "etiqueta": "Productos",
                "endpoint": "inventario.productos",
                "endpoints": (
                    "inventario.productos",
                    "inventario.nuevo_producto",
                    "inventario.editar_producto",
                    "inventario.ver_producto",
                    "inventario.nuevo_movimiento",
                ),
            },
            {
                "clave": "movimientos",
                "etiqueta": "Movimientos",
                "endpoint": "inventario.movimientos",
                "endpoints": ("inventario.movimientos",),
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
                "clave": "clientes",
                "etiqueta": "Clientes",
                "endpoint": "contratos.clientes",
                "endpoints": (
                    "contratos.clientes",
                    "contratos.nuevo_cliente",
                    "contratos.editar_cliente",
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
                "clave": "proveedores",
                "etiqueta": "Proveedores",
                "endpoint": "arriendos.proveedores",
                "endpoints": ("arriendos.proveedores", "arriendos.nuevo_proveedor"),
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
    return puede(permiso, accion)


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
            }
        )

        if not activo:
            continue

        modulo_activo = modulos[-1]
        for submodulo in modulo["submodulos"]:
            if not _es_visible(modulo, submodulo, puede):
                continue
            sub_activo = endpoint in submodulo["endpoints"]
            submodulos.append(
                {
                    "clave": submodulo["clave"],
                    "etiqueta": submodulo["etiqueta"],
                    "endpoint": submodulo["endpoint"],
                    "activo": sub_activo,
                }
            )

    return {
        "modulos": modulos,
        "modulo_activo": modulo_activo,
        "submodulos": submodulos,
    }
