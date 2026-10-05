import csv
import io
import json
from collections import Counter
from datetime import date, datetime, timezone

from flask import render_template, redirect, url_for, flash, request, abort, jsonify, make_response, current_app
from flask_login import current_user
from sqlalchemy import or_, and_
from sqlalchemy.exc import SQLAlchemyError

from app.inventario import bp
from app.inventario.forms import AccionForm, CruceDePruebaForm, ImportarCsvForm
from app.extensions import db
from app.models.conteo_inventario import ItemConteoInventario, TomaInventario, TomaInventarioDetalle
from app.models.equivalencia_codigo import EquivalenciaCodigo, crear_equivalencia
from app.models.codigo_unificado import CodigoUnificado
from app.models.cruce_prueba import borrar_prueba, guardar_prueba, prueba_en_curso
from app.models.importacion_inventario import registrar_importacion, ultimas_importaciones
from app.models.regularizacion import RegularizacionArchivo, RegularizacionHistorial, RegularizacionHistorialArchivo
from app.utils.decorators import require_permission
from app.utils.equivalencias_codigos import proponer
from app.utils.importar_conteo import (
    articulos_fuera_de_ambas_planillas,
    leer_defontana,
    leer_qms,
    clave_sin_ceros,
    codigo_normalizado,
    grupos_duplicados,
    importar_defontana,
    rarezas_del_codigo,
    importar_qms,
    unificar_grupo,
)
from app.utils.cantidades import a_cantidad, format_cantidad, punto_ambiguo
from app.utils.cruce_prueba import comparar, para_guardar
from app.utils.formatting import format_clp, format_fecha_hora
from app.utils.graficos import COLOR, serie, widget_seguro
from app.utils.paneles import panel_inventario
from app.utils.exportar import responder_excel, responder_excel_hojas, responder_plantilla_excel, col, CLP, CANTIDAD, FECHA, PORCENTAJE


def _stats_inventario():
    """Indicadores simples de cuadre QMS/Defontana para las tarjetas superiores del resumen."""
    items_conteo = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id).all()
    total_conteo = len(items_conteo)
    cuadrados = sum(1 for i in items_conteo if i.diferencia_sistemas == 0)
    return {
        "total_conteo": total_conteo,
        "cuadrados": cuadrados,
        "con_dif_stock": total_conteo - cuadrados,
        "conteo_con_diferencia": sum(1 for i in items_conteo if i.tiene_diferencia),
        "conteo_pendientes": sum(1 for i in items_conteo if i.cantidad_fisica is None),
    }


@bp.route("/")
@require_permission("inventario", "ver")
def resumen():
    stats = _stats_inventario()
    panel = widget_seguro(panel_inventario, nombre="resumen de inventario")
    return render_template("inventario/resumen.html", stats=stats, panel=panel)


@bp.context_processor
def _rastro_de_importaciones():
    """Deja a mano en todo Inventario cuándo se importó cada sistema.

    Va por context_processor y no vista por vista porque la pregunta —"¿el
    stock que estoy mirando está al día?"— es la misma en todas las pantallas
    del módulo, y agregarlo a mano en cada una es justo lo que se olvida al
    crear la siguiente.

    Sólo corre cuando se dibuja una plantilla, así que los endpoints que
    devuelven JSON (guardar un conteo, por ejemplo) no pagan la consulta.
    """
    if not current_user.is_authenticated:
        return {}
    return {"ultimas_importaciones": ultimas_importaciones(current_user.empresa_id)}


# --- Stock: cruce QMS / Defontana, conteo físico y diferencias en una sola vista ---

FILTROS_STOCK = ("todos", "diferencias", "sin_contar", "contados")


def filtro_stock(args, por_defecto="todos") -> str:
    """Qué se está mostrando cuando no se eligió nada.

    La pantalla llega con "sin_contar": durante una toma, lo ya contado no
    requiere trabajo y abrirla con los miles de artículos obliga a filtrar a
    mano en cada recarga. La descarga a Excel, en cambio, llega con "todos":
    un archivo descargado se entiende como el registro completo, y entregar
    sólo una parte sin avisar se presta a confusión. Si el usuario eligió un
    filtro, ese manda en los dos casos.
    """
    filtro = (args.get("filtro") or "").strip()
    return filtro if filtro in FILTROS_STOCK else por_defecto


# Qué cuenta como "tiene stock". Además de lo que declaran los dos sistemas,
# entra lo que ya se contó físicamente: un artículo en cero en QMS y Defontana
# del que aparecieron unidades en bodega es justamente un hallazgo, y esconderlo
# sería esconder trabajo hecho.
_TIENE_STOCK = or_(
    ItemConteoInventario.cantidad_qms != 0,
    ItemConteoInventario.cantidad_defontana != 0,
    ItemConteoInventario.cantidad_fisica.isnot(None),
)


def _tiene_stock(item) -> bool:
    """La misma regla que _TIENE_STOCK, para contar sin volver a la base."""
    return bool(item.cantidad_qms or item.cantidad_defontana or item.contado)


def esconder_vacios(args, por_defecto=True) -> bool:
    """Si se dejan fuera los artículos que están en cero en los dos sistemas.

    El maestro trae miles de artículos y la mayoría no tiene existencias en
    ninguno de los dos sistemas: no hay nada que contar en ellos y empujan
    fuera de la pantalla a los que sí importan.

    Es una decisión aparte de los filtros de arriba, no una más de la fila: se
    combina con todos ellos. Durante una toma lo útil es ver lo que falta por
    contar *y* tiene existencias, y eso con un solo filtro no se puede pedir.
    """
    elegido = (args.get("vacios") or "").strip()
    if elegido in ("si", "no"):
        return elegido == "no"
    return por_defecto


COLUMNAS_STOCK = {
    "codigo": ItemConteoInventario.codigo,
    "nombre": ItemConteoInventario.nombre,
    "unidad_qms": ItemConteoInventario.unidad_qms,
    "costo_qms": ItemConteoInventario.costo_unitario_qms,
    "cantidad_qms": ItemConteoInventario.cantidad_qms,
    "cantidad_defontana": ItemConteoInventario.cantidad_defontana,
    "cantidad_fisica": ItemConteoInventario.cantidad_fisica,
    "contado_en": ItemConteoInventario.contado_en,
    "ubicacion": ItemConteoInventario.ubicacion,
    "linea_negocio": ItemConteoInventario.linea_negocio,
}


def _consulta_stock(args, filtro_por_defecto="todos", esconder_vacios_por_defecto=False):
    """Consulta del cruce de stock con búsqueda, filtros por columna y orden aplicados.

    La comparte el listado en pantalla y la exportación a Excel, para que el
    informe descargado sea exactamente lo que el usuario está viendo.
    """
    q = (args.get("q") or "").strip()
    filtro = filtro_stock(args, filtro_por_defecto)
    sin_vacios = esconder_vacios(args, esconder_vacios_por_defecto)

    base = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id)
    if q:
        patron = f"%{q}%"
        base = base.filter(
            or_(ItemConteoInventario.codigo.ilike(patron), ItemConteoInventario.nombre.ilike(patron))
        )
        # Buscar un artículo tiene que encontrarlo aunque esté en cero: si no, la
        # pantalla contestaría "no hay resultados" por un artículo que sí existe,
        # sólo porque venía escondido. Pedirlo a mano con "vacios=no" sí manda.
        if (args.get("vacios") or "").strip() != "no":
            sin_vacios = False

    if sin_vacios:
        base = base.filter(_TIENE_STOCK)

    base, filtros_columna = _filtros_de_columna(base, args)

    if filtro == "sin_contar":
        base = base.filter(ItemConteoInventario.cantidad_fisica.is_(None))
    elif filtro == "contados":
        base = base.filter(ItemConteoInventario.cantidad_fisica.isnot(None))
    elif filtro == "diferencias":
        # descuadre entre sistemas, o el físico contado no coincide con alguno de ellos
        base = base.filter(
            or_(
                ItemConteoInventario.cantidad_qms != ItemConteoInventario.cantidad_defontana,
                and_(
                    ItemConteoInventario.cantidad_fisica.isnot(None),
                    or_(
                        ItemConteoInventario.cantidad_fisica != ItemConteoInventario.cantidad_qms,
                        ItemConteoInventario.cantidad_fisica != ItemConteoInventario.cantidad_defontana,
                    ),
                ),
            )
        )

    base, orden, direccion = _ordenar(base, args, COLUMNAS_STOCK, "codigo")
    return base, q, filtro, filtros_columna, orden, direccion, sin_vacios


@bp.route("/stock")
@require_permission("inventario", "ver")
def stock():
    consulta, q, filtro, filtros_columna, orden, direccion, sin_vacios = _consulta_stock(
        request.args, filtro_por_defecto="sin_contar", esconder_vacios_por_defecto=True
    )
    pagina = request.args.get("pagina", 1, type=int)
    paginacion = consulta.paginate(page=max(1, pagina), per_page=100, error_out=False)

    todos = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id).all()
    resumen = {
        "total": len(todos),
        "con_diferencia": sum(1 for i in todos if i.tiene_diferencia),
        "sin_contar": sum(1 for i in todos if not i.contado),
        "contados": sum(1 for i in todos if i.contado),
        "vacios": sum(1 for i in todos if not _tiene_stock(i)),
    }
    return render_template(
        "inventario/stock.html",
        paginacion=paginacion,
        q=q,
        filtro=filtro,
        etiqueta_filtro=ETIQUETAS_STOCK.get(filtro, filtro),
        resumen=resumen,
        filtros_columna=filtros_columna,
        orden=orden,
        direccion=direccion,
        sin_vacios=sin_vacios,
        puede_cerrar_toma=current_user.es_admin_o_superior,
    )


# --- Toma de inventario: cierre e historial ---
#
# "Cerrar" una toma copia el estado completo del cruce QMS/Defontana/físico a
# una tabla de archivo (TomaInventarioDetalle) y luego limpia el conteo físico
# vivo para que la siguiente toma empiece de cero. Solo puede cerrar quien es
# admin o superadmin; se permite cerrar aunque falten artículos por contar.


@bp.route("/toma/cerrar", methods=["POST"])
@require_permission("inventario", "ver")
def toma_cerrar():
    if not current_user.es_admin_o_superior:
        abort(403)

    items = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id).all()
    if not items:
        flash("No hay artículos cargados para cerrar una toma.", "warning")
        return redirect(url_for("inventario.stock"))

    contados = [i for i in items if i.contado]
    fechas_conteo = [i.contado_en for i in contados if i.contado_en is not None]

    toma = TomaInventario(
        empresa_id=current_user.empresa_id,
        cerrado_por_id=current_user.id,
        fecha_inicio=min(fechas_conteo) if fechas_conteo else None,
        fecha_fin=datetime.now(timezone.utc),
        total_articulos=len(items),
        articulos_contados=len(contados),
        dif_stock=sum(1 for i in items if i.diferencia_sistemas != 0),
        dif_costo=sum(1 for i in items if i.tiene_diferencia_costo),
        dif_unidad=sum(1 for i in items if not i.unidades_coinciden),
        valor_qms_total=sum(i.valor_qms for i in items),
        valor_defontana_total=sum(i.valor_defontana for i in items),
        valor_fisico_total=sum(i.valor_fisico or 0 for i in contados),
    )
    db.session.add(toma)
    db.session.flush()

    detalles = [
        TomaInventarioDetalle(
            toma_id=toma.id,
            codigo=i.codigo,
            nombre=i.nombre,
            categoria=i.categoria,
            linea_negocio=i.linea_negocio,
            ubicacion=i.ubicacion,
            unidad_qms=i.unidad_qms,
            unidad_defontana=i.unidad_defontana,
            costo_unitario_qms=i.costo_unitario_qms,
            costo_unitario_defontana=i.costo_unitario_defontana,
            cantidad_qms=i.cantidad_qms,
            cantidad_defontana=i.cantidad_defontana,
            cantidad_fisica=i.cantidad_fisica,
            contado_por_id=i.contado_por_id,
            contado_en=i.contado_en,
        )
        for i in items
    ]
    db.session.add_all(detalles)

    for i in items:
        i.cantidad_fisica = None
        i.contado_por_id = None
        i.contado_en = None

    db.session.commit()
    flash(
        f"Toma de inventario cerrada: {toma.articulos_contados} de {toma.total_articulos} artículos contados. "
        "El conteo físico quedó en blanco para empezar una toma nueva.",
        "success",
    )
    return redirect(url_for("inventario.historial_detalle", toma_id=toma.id))


@bp.route("/historial/<int:toma_id>/reabrir", methods=["POST"])
@require_permission("inventario", "editar")
def toma_reabrir(toma_id):
    """Devuelve una toma cerrada al cruce vivo para seguir contándola.

    Sirve para cuando una toma se cerró antes de tiempo (por error, o para poder
    refrescar el stock). Restituye el conteo físico y, en los artículos contados,
    también el stock que cada sistema declaraba ese día: sin eso el conteo
    quedaría comparado contra cifras posteriores y aparecerían diferencias falsas.

    En los artículos que estaban sin contar no se toca el stock actual, que es
    justamente el que se quiere tener al día para seguir contando.

    Si un artículo ya se contó de nuevo en el cruce vivo, gana ese conteo por ser
    el más reciente: reabrir nunca pisa trabajo de bodega hecho después.
    """
    if not current_user.es_admin_o_superior:
        abort(403)

    toma = TomaInventario.query.filter_by(id=toma_id, empresa_id=current_user.empresa_id).first_or_404()

    items = {
        codigo_normalizado(i.codigo): i
        for i in ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id).all()
    }

    restaurados = conservados = sin_articulo = 0
    for detalle in toma.detalles:
        if detalle.cantidad_fisica is None:
            continue  # no se contó en esa toma: nada que devolver
        item = items.get(codigo_normalizado(detalle.codigo))
        if item is None:
            sin_articulo += 1  # el artículo se depuró después de cerrar la toma
            continue
        if item.cantidad_fisica is not None:
            conservados += 1  # ya se volvió a contar: el conteo nuevo manda
            continue
        item.cantidad_fisica = detalle.cantidad_fisica
        item.contado_por_id = detalle.contado_por_id
        item.contado_en = detalle.contado_en
        item.cantidad_qms = detalle.cantidad_qms
        item.cantidad_defontana = detalle.cantidad_defontana
        restaurados += 1

    db.session.delete(toma)  # deja de ser historial: vuelve a estar en curso
    db.session.commit()

    aviso = (
        f"Toma retomada: {restaurados} artículos vuelven a aparecer como contados, "
        "con quién los contó y cuándo, así no se cuentan de nuevo."
    )
    if conservados:
        aviso += f" {conservados} se dejaron como estaban porque ya se contaron de nuevo."
    if sin_articulo:
        aviso += f" {sin_articulo} no se pudieron devolver porque el artículo ya no existe."
    flash(aviso, "success")
    return redirect(url_for("inventario.stock"))


@bp.route("/historial")
@require_permission("inventario", "ver")
def historial():
    tomas = (
        TomaInventario.query.filter_by(empresa_id=current_user.empresa_id)
        .order_by(TomaInventario.fecha_fin.desc())
        .all()
    )
    return render_template("inventario/historial.html", tomas=tomas, form=AccionForm())


COLUMNAS_HISTORIAL_DETALLE = {
    "codigo": TomaInventarioDetalle.codigo,
    "nombre": TomaInventarioDetalle.nombre,
    "cantidad_qms": TomaInventarioDetalle.cantidad_qms,
    "cantidad_defontana": TomaInventarioDetalle.cantidad_defontana,
    "cantidad_fisica": TomaInventarioDetalle.cantidad_fisica,
}


@bp.route("/historial/<int:toma_id>")
@require_permission("inventario", "ver")
def historial_detalle(toma_id):
    toma = TomaInventario.query.filter_by(id=toma_id, empresa_id=current_user.empresa_id).first_or_404()

    consulta = TomaInventarioDetalle.query.filter_by(toma_id=toma.id)
    q = (request.args.get("q") or "").strip()
    if q:
        patron = f"%{q}%"
        consulta = consulta.filter(
            or_(TomaInventarioDetalle.codigo.ilike(patron), TomaInventarioDetalle.nombre.ilike(patron))
        )

    filtro = request.args.get("filtro", "todos")
    if filtro not in ("todos", "dif_stock", "dif_costo", "dif_unidad", "sin_contar"):
        filtro = "todos"

    consulta, orden, direccion = _ordenar(consulta, request.args, COLUMNAS_HISTORIAL_DETALLE, "codigo")
    detalles = consulta.all()

    if filtro == "dif_stock":
        detalles = [d for d in detalles if d.diferencia_sistemas != 0]
    elif filtro == "dif_costo":
        detalles = [d for d in detalles if d.tiene_diferencia_costo]
    elif filtro == "dif_unidad":
        detalles = [d for d in detalles if not d.unidades_coinciden]
    elif filtro == "sin_contar":
        detalles = [d for d in detalles if not d.contado]

    conteos = {
        "todos": len(toma.detalles),
        "dif_stock": toma.dif_stock,
        "dif_costo": toma.dif_costo,
        "dif_unidad": toma.dif_unidad,
        "sin_contar": toma.articulos_sin_contar,
    }

    pagina = max(1, request.args.get("pagina", 1, type=int))
    por_pagina = 100
    total_paginas = max(1, (len(detalles) + por_pagina - 1) // por_pagina)
    pagina = min(pagina, total_paginas)
    visibles = detalles[(pagina - 1) * por_pagina : pagina * por_pagina]

    return render_template(
        "inventario/historial_detalle.html",
        toma=toma,
        form=AccionForm(),
        detalles=visibles,
        total_detalles=len(detalles),
        conteos=conteos,
        q=q,
        filtro=filtro,
        orden=orden,
        direccion=direccion,
        pagina=pagina,
        total_paginas=total_paginas,
    )


@bp.route("/historial/<int:toma_id>.xlsx")
@require_permission("inventario", "ver")
def historial_excel(toma_id):
    toma = TomaInventario.query.filter_by(id=toma_id, empresa_id=current_user.empresa_id).first_or_404()

    columnas = [
        col("Código", ancho=20, total="texto"),
        col("Nombre", ancho=44),
        col("Unidad QMS", ancho=12),
        col("Unidad Defontana", ancho=17),
        col("Costo unitario QMS", ancho=18, formato=CLP),
        col("Costo unitario Defontana", ancho=22, formato=CLP),
        col("Stock QMS", ancho=12, formato=CANTIDAD, total="suma"),
        col("Stock Defontana", ancho=16, formato=CANTIDAD, total="suma"),
        col("Stock físico", ancho=13, formato=CANTIDAD, total="suma"),
        col("Contado por", ancho=26),
        col("Fecha y hora del conteo", ancho=22),
        col("Categoría", ancho=24),
        col("Línea de negocio", ancho=24),
        col("Ubicación", ancho=28),
    ]
    filas = [
        [
            d.codigo,
            d.nombre or "",
            d.unidad_qms or "",
            d.unidad_defontana or "",
            d.costo_unitario_qms,
            d.costo_unitario_defontana,
            d.cantidad_qms,
            d.cantidad_defontana,
            d.cantidad_fisica if d.contado else None,
            d.contado_por.nombre_completo if d.contado_por else "",
            format_fecha_hora(d.contado_en),
            d.categoria or "",
            d.linea_negocio or "",
            d.ubicacion or "",
        ]
        for d in toma.detalles
    ]

    return responder_excel(
        f"toma-inventario-{toma.id}",
        f"Toma de inventario cerrada el {format_fecha_hora(toma.fecha_fin)}",
        columnas,
        filas,
        f"Cerrada por {toma.cerrado_por.nombre_completo if toma.cerrado_por else '—'}",
    )


def _descripcion_filtros(q, filtro, filtros_columna, etiquetas, nota=""):
    """Texto legible con los filtros aplicados, para dejarlo escrito en el informe.

    Un informe que dejó fuera parte del maestro tiene que decirlo en su
    encabezado: si no, se lee como el total y cuadra contra nada. Cada pantalla
    recorta con su propia regla, así que el texto lo pone quien llama.
    """
    partes = []
    if filtro and filtro != "todos":
        partes.append(etiquetas.get(filtro, filtro))
    if nota:
        partes.append(nota)
    if q:
        partes.append(f'búsqueda "{q}"')
    for parametro, texto in (filtros_columna or {}).items():
        if texto:
            partes.append(f'{etiquetas.get(parametro, parametro)}: "{texto}"')
    return " · ".join(partes) if partes else "Sin filtros"


ETIQUETAS_STOCK = {
    "diferencias": "Solo con diferencias",
    "sin_contar": "Solo sin contar",
    "contados": "Solo contados",
    "f_codigo": "Código",
    "f_nombre": "Nombre",
    "f_ubicacion": "Ubicación",
    "f_linea": "Línea de negocio",
    "f_unidad": "Unidad",
    "f_categoria": "Categoría",
}


@bp.route("/stock.xlsx")
@require_permission("inventario", "ver")
def stock_excel():
    """Informe en Excel del cruce de stock, con los mismos filtros de la pantalla."""
    # El archivo descargado se entiende como el registro completo, así que no
    # esconde nada por su cuenta: sólo recorta si se lo pidieron a mano.
    consulta, q, filtro, filtros_columna, _orden, _dir, _sin_vacios = _consulta_stock(
        request.args, esconder_vacios_por_defecto=False
    )
    items = consulta.all()

    columnas = [
        col("Código", ancho=20, total="texto"),
        col("Nombre", ancho=48),
        col("Unidad QMS", ancho=12),
        col("Unidad Defontana", ancho=17),
        col("Unidades coinciden", ancho=18),
        col("Costo unitario QMS", ancho=18, formato=CLP),
        col("Costo unitario Defontana", ancho=22, formato=CLP),
        col("Dif. costo unitario", ancho=18, formato=CLP),
        col("Stock QMS", ancho=12, formato=CANTIDAD, total="suma"),
        col("Stock Defontana", ancho=16, formato=CANTIDAD, total="suma"),
        col("Dif. sistemas", ancho=14, formato=CANTIDAD, total="suma"),
        col("Stock físico", ancho=13, formato=CANTIDAD, total="suma"),
        col("Físico vs QMS", ancho=14, formato=CANTIDAD, total="suma"),
        col("Físico vs Defontana", ancho=18, formato=CANTIDAD, total="suma"),
        col("Estado del conteo", ancho=18),
        col("Contado por", ancho=26),
        col("Fecha y hora del conteo", ancho=22),
        col("Ubicación", ancho=28),
        col("Línea de negocio", ancho=24),
    ]
    filas = [
        [
            i.codigo,
            i.nombre or "",
            i.unidad_qms or "",
            i.unidad_defontana or "",
            "Sí" if i.unidades_coinciden else "NO",
            i.costo_unitario_qms,
            i.costo_unitario_defontana,
            i.diferencia_costo_unitario,
            i.cantidad_qms,
            i.cantidad_defontana,
            i.diferencia_sistemas,
            i.cantidad_fisica if i.contado else None,
            i.diferencia_fisica_qms,
            i.diferencia_fisica_defontana,
            "Contado" if i.contado else "Pendiente",
            i.contado_por.nombre_completo if i.contado_por else "",
            format_fecha_hora(i.contado_en),
            i.ubicacion or "",
            i.linea_negocio or "",
        ]
        for i in items
    ]

    return responder_excel(
        "stock-y-conteo",
        "Stock y conteo",
        columnas,
        filas,
        _descripcion_filtros(
            q, filtro, filtros_columna, ETIQUETAS_STOCK,
            "sin los artículos en cero en los dos sistemas" if _sin_vacios else "",
        ),
    )


@bp.route("/stock/<int:item_id>/contar", methods=["POST"])
@require_permission("inventario", "editar")
def stock_contar(item_id):
    """Registra el conteo físico desde la misma fila del listado, sin recargar la página."""
    item = ItemConteoInventario.query.filter_by(
        id=item_id, empresa_id=current_user.empresa_id
    ).first_or_404()

    datos = request.get_json(silent=True) or {}
    valor = str(datos.get("cantidad", "")).strip()

    if valor == "":
        item.cantidad_fisica = None
        item.contado_por_id = None
        item.contado_en = None
    else:
        # Se aceptan decimales: hay artículos que se cuentan en metros, kilos o
        # litros, y ahí "12,5" es la cantidad real. Vale escribirlo con coma o
        # con punto, que es como sale de la calculadora del teléfono.
        #
        # Salvo un punto con tres dígitos detrás, que en Chile es de miles:
        # "3.125" se guardaría como tres mil ciento veinticinco cuando lo
        # contado eran tres metros y ciento veinticinco milímetros. Mil veces
        # la cantidad real, sin aviso. Antes que adivinar, se pregunta.
        if punto_ambiguo(valor):
            entero = valor.strip().replace(".", "")
            return jsonify({
                "ok": False,
                "error": f"¿{valor.strip().replace('.', ',')} o {entero}? Escribe los decimales "
                         f"con coma ({valor.strip().replace('.', ',')}) o sin puntos ({entero}).",
            }), 400
        cantidad = a_cantidad(valor)
        if cantidad is None:
            return jsonify({"ok": False, "error": "Ingresa un número, por ejemplo 12 o 12,5."}), 400
        if cantidad < 0:
            return jsonify({"ok": False, "error": "La cantidad no puede ser negativa."}), 400
        item.cantidad_fisica = cantidad
        item.contado_por_id = current_user.id
        item.contado_en = datetime.now(timezone.utc)

    db.session.commit()
    return jsonify(
        {
            "ok": True,
            "contado": item.contado,
            "dif_qms": item.diferencia_fisica_qms,
            "dif_defontana": item.diferencia_fisica_defontana,
            "tiene_diferencia": item.tiene_diferencia,
            # Para mostrar la trazabilidad del conteo sin recargar la página
            "registrado_por": item.contado_por.nombre_completo if item.contado_por else "",
            "registrado_en": format_fecha_hora(item.contado_en),
        }
    )


# --- Ajuste de inventario: valorización QMS vs Defontana vs conteo físico ---

FILTROS_AJUSTE = ("todos", "dif_stock", "contados")

COLUMNAS_AJUSTE = {
    "codigo": ItemConteoInventario.codigo,
    "nombre": ItemConteoInventario.nombre,
    "unidad_qms": ItemConteoInventario.unidad_qms,
    "unidad_defontana": ItemConteoInventario.unidad_defontana,
    "categoria": ItemConteoInventario.categoria,
    "linea_negocio": ItemConteoInventario.linea_negocio,
    "costo_qms": ItemConteoInventario.costo_unitario_qms,
    "costo_defontana": ItemConteoInventario.costo_unitario_defontana,
    "cantidad_qms": ItemConteoInventario.cantidad_qms,
    "cantidad_defontana": ItemConteoInventario.cantidad_defontana,
    "cantidad_fisica": ItemConteoInventario.cantidad_fisica,
}

# Filtros de texto por columna: parámetro de la URL -> columna de la tabla
FILTROS_COLUMNA = {
    "f_codigo": ItemConteoInventario.codigo,
    "f_nombre": ItemConteoInventario.nombre,
    "f_unidad": ItemConteoInventario.unidad_qms,
    "f_categoria": ItemConteoInventario.categoria,
    "f_linea": ItemConteoInventario.linea_negocio,
    "f_ubicacion": ItemConteoInventario.ubicacion,
}


def _filtros_de_columna(consulta, args):
    """Aplica los filtros escritos bajo cada título de columna. Devuelve (consulta, valores)."""
    valores = {}
    for parametro, columna in FILTROS_COLUMNA.items():
        texto = (args.get(parametro) or "").strip()
        valores[parametro] = texto
        if texto:
            consulta = consulta.filter(columna.ilike(f"%{texto}%"))
    return consulta, valores


def _ordenar(consulta, args, columnas, por_defecto):
    """Ordena por la columna pedida en el encabezado; ignora columnas desconocidas."""
    orden = args.get("orden") or por_defecto
    if orden not in columnas:
        orden = por_defecto
    descendente = args.get("dir") == "desc"
    columna = columnas[orden]
    consulta = consulta.order_by(columna.desc() if descendente else columna.asc())
    return consulta, orden, ("desc" if descendente else "asc")


def _items_ajuste(args):
    """Items del cruce ya filtrados y ordenados según lo pedido en la vista."""
    consulta = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id)

    busqueda = (args.get("q") or "").strip()
    if busqueda:
        patron = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(ItemConteoInventario.codigo.ilike(patron), ItemConteoInventario.nombre.ilike(patron))
        )

    consulta, filtros_columna = _filtros_de_columna(consulta, args)
    consulta, orden, direccion = _ordenar(consulta, args, COLUMNAS_AJUSTE, "codigo")

    items = consulta.all()

    filtro = args.get("filtro", "todos")
    if filtro not in FILTROS_AJUSTE:
        filtro = "todos"
    if filtro == "dif_stock":
        items = [i for i in items if i.diferencia_sistemas != 0]
    elif filtro == "contados":
        items = [i for i in items if i.contado]

    return items, busqueda, filtros_columna, filtro, orden, direccion


def _totales_ajuste(items):
    """Valorización agregada del conjunto filtrado."""
    contados = [i for i in items if i.contado]
    return {
        "articulos": len(items),
        "stock_qms": sum(i.cantidad_qms or 0 for i in items),
        "stock_defontana": sum(i.cantidad_defontana or 0 for i in items),
        "stock_fisico": sum(i.cantidad_fisica or 0 for i in contados),
        "valor_qms": sum(i.valor_qms for i in items),
        "valor_defontana": sum(i.valor_defontana for i in items),
        "valor_fisico": sum(i.valor_fisico or 0 for i in contados),
        "valor_qms_contados": sum(i.valor_qms for i in contados),
        "ajuste_fisico": sum(i.diferencia_valor_fisico or 0 for i in contados),
        "contados": len(contados),
        "dif_stock": sum(1 for i in items if i.diferencia_sistemas != 0),
    }


@bp.route("/ajuste")
@require_permission("inventario", "ver")
def ajuste():
    """Compara costo, unidad de medida y valorización entre QMS, Defontana y el conteo físico."""
    items, busqueda, filtros_columna, filtro, orden, direccion = _items_ajuste(request.args)
    totales = _totales_ajuste(items)

    pagina = max(1, request.args.get("pagina", 1, type=int))
    por_pagina = 100
    total_paginas = max(1, (len(items) + por_pagina - 1) // por_pagina)
    pagina = min(pagina, total_paginas)
    visibles = items[(pagina - 1) * por_pagina : pagina * por_pagina]

    # Artículos donde la diferencia de valorización pesa más
    top_diferencias = sorted(items, key=lambda i: abs(i.diferencia_valor_sistemas or 0), reverse=True)[:8]
    grafico_top = [
        serie(
            (i.nombre or i.codigo)[:38],
            abs(i.diferencia_valor_sistemas),
            COLOR["rojo"] if i.diferencia_valor_sistemas > 0 else COLOR["azul"],
            texto=format_clp(i.diferencia_valor_sistemas),
        )
        for i in top_diferencias
        if i.diferencia_valor_sistemas
    ]

    grafico_valorizacion = [
        serie("Valor QMS", totales["valor_qms"], COLOR["azul"], texto=format_clp(totales["valor_qms"])),
        serie("Valor Defontana", totales["valor_defontana"], COLOR["azul_claro"], texto=format_clp(totales["valor_defontana"])),
        serie("Valor físico contado", totales["valor_fisico"], COLOR["verde"], texto=format_clp(totales["valor_fisico"])),
    ]

    return render_template(
        "inventario/ajuste.html",
        items=visibles,
        totales=totales,
        q=busqueda,
        filtro=filtro,
        filtros_columna=filtros_columna,
        orden=orden,
        direccion=direccion,
        pagina=pagina,
        total_paginas=total_paginas,
        grafico_top=grafico_top,
        grafico_valorizacion=grafico_valorizacion,
    )


@bp.route("/ajuste.csv")
@require_permission("inventario", "ver")
def ajuste_csv():
    """Exporta el ajuste con los mismos filtros aplicados en pantalla."""
    items, _q, _fc, _filtro, _orden, _dir = _items_ajuste(request.args)

    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow([
        "Código", "Descripción",
        "Costo unitario QMS", "Costo unitario Defontana",
        "Stock QMS", "Stock Defontana", "Stock físico",
        "Valor QMS", "Valor Defontana", "Diferencia valorización",
        "Ajuste físico vs QMS", "Categoría", "Línea de negocio", "Ubicación",
    ])
    for i in items:
        escritor.writerow([
            i.codigo, i.nombre or "",
            i.costo_unitario_qms if i.costo_unitario_qms is not None else "",
            i.costo_unitario_defontana if i.costo_unitario_defontana is not None else "",
            i.cantidad_qms, i.cantidad_defontana,
            i.cantidad_fisica if i.contado else "",
            i.valor_qms, i.valor_defontana,
            i.diferencia_valor_sistemas if i.diferencia_valor_sistemas is not None else "",
            i.diferencia_valor_fisico if i.contado else "",
            i.categoria or "", i.linea_negocio or "", i.ubicacion or "",
        ])

    respuesta = make_response(salida.getvalue().encode("utf-8-sig"))
    respuesta.headers["Content-Type"] = "text/csv; charset=utf-8"
    respuesta.headers["Content-Disposition"] = (
        f"attachment; filename=ajuste-inventario-{date.today().isoformat()}.csv"
    )
    return respuesta


ETIQUETAS_AJUSTE = {
    "dif_stock": "Solo con diferencia de stock",
    "contados": "Solo contados",
    "f_codigo": "Código",
    "f_nombre": "Descripción",
    "f_unidad": "Unidad",
    "f_categoria": "Categoría",
    "f_linea": "Línea de negocio",
    "f_ubicacion": "Ubicación",
}


@bp.route("/ajuste.xlsx")
@require_permission("inventario", "ver")
def ajuste_excel():
    """Informe en Excel del ajuste de inventario, con los filtros de la pantalla."""
    items, q, filtros_columna, filtro, _orden, _dir = _items_ajuste(request.args)

    columnas = [
        col("Código", ancho=20, total="texto"),
        col("Descripción", ancho=48),
        col("Costo unitario QMS", ancho=18, formato=CLP),
        col("Costo unitario Defontana", ancho=22, formato=CLP),
        col("Stock QMS", ancho=12, formato=CANTIDAD, total="suma"),
        col("Stock Defontana", ancho=16, formato=CANTIDAD, total="suma"),
        col("Stock físico", ancho=13, formato=CANTIDAD, total="suma"),
        col("Valor QMS", ancho=16, formato=CLP, total="suma"),
        col("Valor Defontana", ancho=17, formato=CLP, total="suma"),
        col("Dif. valorización", ancho=18, formato=CLP, total="suma"),
        col("Ajuste físico vs QMS", ancho=20, formato=CLP, total="suma"),
        col("Categoría", ancho=24),
        col("Línea de negocio", ancho=24),
        col("Ubicación", ancho=28),
    ]
    filas = [
        [
            i.codigo,
            i.nombre or "",
            i.costo_unitario_qms,
            i.costo_unitario_defontana,
            i.cantidad_qms,
            i.cantidad_defontana,
            i.cantidad_fisica if i.contado else None,
            i.valor_qms,
            i.valor_defontana,
            i.diferencia_valor_sistemas,
            i.diferencia_valor_fisico,
            i.categoria or "",
            i.linea_negocio or "",
            i.ubicacion or "",
        ]
        for i in items
    ]

    return responder_excel(
        "ajuste-inventario",
        "Ajuste de inventario",
        columnas,
        filas,
        _descripcion_filtros(q, filtro, filtros_columna, ETIQUETAS_AJUSTE),
    )


# --- Cruce de datos: consistencia de unidad de medida y costo entre QMS y Defontana ---
#
# A diferencia de Ajuste inventario (que valoriza el stock), este submódulo responde
# una pregunta distinta: "¿el maestro de datos está bien parametrizado?" — es decir,
# qué SKUs quedaron con distinta unidad de medida o distinto costo unitario cargado
# en cada sistema, para poder corregirlos en el origen.

FILTROS_CRUCE = ("todos", "dif_costo", "dif_unidad", "ambas", "sin_costo", "costo_sin_stock")

ETIQUETAS_ESTADO_MAESTRO = {
    "ok": "Costo y unidad coinciden",
    "dif_costo": "Diferencia de costo",
    "dif_unidad": "Diferencia de unidad",
    "ambas": "Costo y unidad difieren",
    "sin_costo": "Sin costo cargado",
}

ETIQUETAS_CRUCE = {
    "dif_costo": "Solo con diferencia de costo",
    "dif_unidad": "Solo con distinta unidad de medida",
    "ambas": "Solo con costo y unidad distintos",
    "sin_costo": "Solo sin costo cargado",
    "costo_sin_stock": "Solo con costo cargado y sin stock",
    "f_codigo": "Código",
    "f_nombre": "Descripción",
    "f_unidad": "Unidad",
    "f_categoria": "Categoría",
    "f_linea": "Línea de negocio",
    "f_ubicacion": "Ubicación",
}


def _hay_algo_que_mirar(item) -> bool:
    """Si el artículo aporta algo al cruce de maestro.

    Cruzar tiene sentido cuando hay existencias, y también cuando hay un costo
    cargado sin existencias: eso último es justamente lo que hay que revisar,
    porque un costo sobre cero unidades no valoriza nada. Lo que no tiene ni
    stock ni costo no dice nada y sólo empuja fuera de pantalla a lo que sí.
    """
    return _tiene_stock(item) or item.tiene_costo


def _items_cruce_datos(args, esconder_vacios_por_defecto=False):
    """Items del cruce QMS/Defontana filtrados según consistencia del maestro."""
    consulta = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id)

    busqueda = (args.get("q") or "").strip()
    sin_vacios = esconder_vacios(args, esconder_vacios_por_defecto)
    if busqueda:
        patron = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(ItemConteoInventario.codigo.ilike(patron), ItemConteoInventario.nombre.ilike(patron))
        )
        # Igual que en Stock y conteo: buscar un artículo tiene que encontrarlo
        # aunque esté vacío, que es cuando más falta hace buscarlo.
        if (args.get("vacios") or "").strip() != "no":
            sin_vacios = False

    consulta, filtros_columna = _filtros_de_columna(consulta, args)
    consulta, orden, direccion = _ordenar(consulta, args, COLUMNAS_AJUSTE, "codigo")

    items = consulta.all()
    # Se cuentan siempre, se escondan o no: la pantalla dice cuántos son en los
    # dos casos, y así no hace falta una segunda consulta para averiguarlo.
    vacios = sum(1 for i in items if not _hay_algo_que_mirar(i))
    if sin_vacios:
        items = [i for i in items if _hay_algo_que_mirar(i)]

    filtro = args.get("filtro", "todos")
    if filtro not in FILTROS_CRUCE:
        filtro = "todos"
    if filtro in ETIQUETAS_ESTADO_MAESTRO:
        items = [i for i in items if i.estado_maestro == filtro]
    elif filtro == "costo_sin_stock":
        items = [i for i in items if i.costo_sin_stock]

    return items, busqueda, filtros_columna, filtro, orden, direccion, sin_vacios, vacios


def _totales_cruce(items):
    por_estado = {clave: 0 for clave in ETIQUETAS_ESTADO_MAESTRO}
    for i in items:
        por_estado[i.estado_maestro] += 1
    return {
        "articulos": len(items),
        "con_costo": sum(1 for i in items if i.tiene_costo),
        "costo_sin_stock": sum(1 for i in items if i.costo_sin_stock),
        **por_estado,
    }


@bp.route("/cruce-datos")
@require_permission("inventario", "ver")
def cruce_datos():
    """Consistencia de unidad de medida y costo unitario entre QMS y Defontana."""
    items, busqueda, filtros_columna, filtro, orden, direccion, sin_vacios, vacios = (
        _items_cruce_datos(request.args, esconder_vacios_por_defecto=True)
    )
    totales = _totales_cruce(items)

    pagina = max(1, request.args.get("pagina", 1, type=int))
    por_pagina = 100
    total_paginas = max(1, (len(items) + por_pagina - 1) // por_pagina)
    pagina = min(pagina, total_paginas)
    visibles = items[(pagina - 1) * por_pagina : pagina * por_pagina]

    grafico_estado = [
        serie(ETIQUETAS_ESTADO_MAESTRO["ok"], totales["ok"], COLOR["verde"]),
        serie(ETIQUETAS_ESTADO_MAESTRO["dif_costo"], totales["dif_costo"], COLOR["ambar"]),
        serie(ETIQUETAS_ESTADO_MAESTRO["dif_unidad"], totales["dif_unidad"], COLOR["rojo"]),
        serie(ETIQUETAS_ESTADO_MAESTRO["ambas"], totales["ambas"], COLOR["morado"]),
        serie(ETIQUETAS_ESTADO_MAESTRO["sin_costo"], totales["sin_costo"], COLOR["gris"]),
    ]

    # SKUs donde la diferencia de costo pesa más en pesos sobre el stock declarado
    con_impacto = [i for i in items if i.impacto_diferencia_costo]
    top_impacto = sorted(con_impacto, key=lambda i: abs(i.impacto_diferencia_costo), reverse=True)[:8]
    grafico_impacto = [
        serie(
            (i.nombre or i.codigo)[:38],
            abs(i.impacto_diferencia_costo),
            COLOR["rojo"] if i.impacto_diferencia_costo > 0 else COLOR["azul"],
            texto=format_clp(i.impacto_diferencia_costo),
        )
        for i in top_impacto
    ]

    return render_template(
        "inventario/cruce_datos.html",
        items=visibles,
        totales=totales,
        q=busqueda,
        filtro=filtro,
        filtros_columna=filtros_columna,
        orden=orden,
        direccion=direccion,
        pagina=pagina,
        total_paginas=total_paginas,
        grafico_estado=grafico_estado,
        grafico_impacto=grafico_impacto,
        pares_de_unidades=_pares_de_unidades_distintas(items),
        sin_vacios=sin_vacios,
        vacios=vacios,
        form_importar=CruceDePruebaForm(),
        prueba=prueba_en_curso(current_user.empresa_id, current_user.id),
        # Si la subida se rechazó, el panel tiene que volver abierto: cerrado,
        # el aviso de error queda arriba sin nada visible que lo explique.
        abrir_importar=request.args.get("subir") == "1",
    )


def _pares_de_unidades_distintas(items):
    """Los pares de unidades que siguen contando como diferencia, con cuántos artículos.

    Sirve para descubrir equivalencias que falten: en vez de revisar cientos de
    artículos uno por uno, se ven los pocos pares distintos que hay y se agregan
    a la tabla de app/utils/unidades.py los que sean la misma unidad.
    """
    conteo = Counter(
        (i.unidad_qms, i.unidad_defontana) for i in items if not i.unidades_coinciden
    )
    return [
        {"qms": qms, "defontana": defontana, "articulos": cuantos}
        for (qms, defontana), cuantos in conteo.most_common()
    ]


@bp.route("/cruce-datos.xlsx")
@require_permission("inventario", "ver")
def cruce_datos_excel():
    """Informe en Excel de consistencia de unidad y costo, con los filtros de la pantalla."""
    # Como en Stock y conteo: el archivo descargado es el registro completo y
    # no recorta por su cuenta; sólo si se lo piden a mano.
    items, q, filtros_columna, filtro, _orden, _dir, sin_vacios, _vacios = _items_cruce_datos(
        request.args, esconder_vacios_por_defecto=False
    )

    columnas, filas = _excel_del_cruce(items)

    return responder_excel(
        "cruce-datos-inventario",
        "Cruce de unidades y costos",
        columnas,
        filas,
        _descripcion_filtros(
            q, filtro, filtros_columna, ETIQUETAS_CRUCE,
            "sin los artículos sin stock ni costo" if sin_vacios else "",
        ),
    )


def _excel_del_cruce(items):
    """Columnas y filas del informe del cruce.

    Las comparten el cruce del sistema y el de prueba: la misma comparación
    sobre datos distintos tiene que bajarse igual en los dos casos.
    """
    columnas = [
        col("Código", ancho=20, total="texto"),
        col("Descripción", ancho=48),
        col("Unidad QMS", ancho=12),
        col("Unidad Defontana", ancho=17),
        col("Unidades coinciden", ancho=18),
        col("Costo unitario QMS", ancho=18, formato=CLP),
        col("Costo unitario Defontana", ancho=22, formato=CLP),
        col("Dif. costo unitario", ancho=18, formato=CLP),
        col("Desviación costo (%)", ancho=19, formato=PORCENTAJE),
        col("Impacto en stock QMS", ancho=20, formato=CLP, total="suma"),
        col("Falta en", ancho=16),
        col("Estado del maestro", ancho=22),
        col("Costo sin stock", ancho=16),
        col("Categoría", ancho=24),
        col("Línea de negocio", ancho=24),
        col("Ubicación", ancho=28),
    ]
    filas = [
        [
            i.codigo,
            i.nombre or "",
            i.unidad_qms or "",
            i.unidad_defontana or "",
            "Sí" if i.unidades_coinciden else "NO",
            i.costo_unitario_qms,
            i.costo_unitario_defontana,
            i.diferencia_costo_unitario,
            (i.desviacion_costo_pct / 100) if i.desviacion_costo_pct is not None else None,
            i.impacto_diferencia_costo,
            i.falta_en,
            ETIQUETAS_ESTADO_MAESTRO[i.estado_maestro],
            "Sí" if i.costo_sin_stock else "",
            i.categoria or "",
            i.linea_negocio or "",
            i.ubicacion or "",
        ]
        for i in items
    ]
    return columnas, filas


# --- Cruce de datos: paso a paso para dejar QMS igual a Defontana ---
#
# Defontana se toma como la fuente correcta: cada paso dice qué corregir en QMS
# (o qué crear en el sistema donde falta el artículo). El orden importa: primero
# la unidad, porque el costo unitario y el stock se expresan en ella; después el
# costo y el stock; al final los artículos que faltan en uno de los dos sistemas.

PASOS_REGULARIZAR = (
    ("unidad", "Corregir la unidad de medida en QMS",
     "Deja en QMS la misma unidad que tiene Defontana. Va primero: el costo unitario y el stock se miden en esa unidad."),
    ("costo", "Corregir el costo unitario",
     "Deja en QMS el costo unitario de Defontana. Si Defontana no tiene costo, cárgalo primero en Defontana (con la factura)."),
    ("stock", "Ajustar el stock de QMS",
     "Deja en QMS el mismo stock que Defontana. Si crees que Defontana está mal, regularízalo antes en Inventario → Regularización."),
    ("crear_defontana", "Crear en Defontana los artículos que solo están en QMS",
     "Existen en QMS pero no en Defontana. Créalos en Defontana con su unidad y costo, y regístrales el stock."),
    ("crear_qms", "Crear en QMS los artículos que solo están en Defontana",
     "Existen en Defontana pero no en QMS. Créalos en QMS con la unidad, el costo y el stock de Defontana."),
    ("sin_costo", "Cargar costo a los artículos con stock y sin costo",
     "Tienen stock pero ningún sistema tiene costo. Cárgalo en Defontana con la factura y luego en QMS."),
)


def _pasos_regularizar(items):
    """Arma el plan: para cada paso, la lista de (artículo, qué hacer)."""
    pasos = {clave: [] for clave, _titulo, _porque in PASOS_REGULARIZAR}
    for i in items:
        if not _hay_algo_que_mirar(i):
            continue
        if i.en_qms and not i.en_defontana:
            detalle = ", ".join(
                x for x in (
                    f"unidad {i.unidad_qms}" if i.unidad_qms else "",
                    f"costo {format_clp(i.costo_unitario_qms)}" if i.costo_unitario_qms else "",
                    f"stock {format_cantidad(i.cantidad_qms)}" if i.cantidad_qms else "",
                ) if x
            )
            pasos["crear_defontana"].append((i, "Crear en Defontana" + (f" ({detalle}, según QMS)" if detalle else "")))
            continue
        if i.en_defontana and not i.en_qms:
            detalle = ", ".join(
                x for x in (
                    f"unidad {i.unidad_defontana}" if i.unidad_defontana else "",
                    f"costo {format_clp(i.costo_unitario_defontana)}" if i.costo_unitario_defontana else "",
                    f"stock {format_cantidad(i.cantidad_defontana)}" if i.cantidad_defontana else "",
                ) if x
            )
            pasos["crear_qms"].append((i, "Crear en QMS" + (f" ({detalle}, según Defontana)" if detalle else "")))
            continue
        if not i.en_qms and not i.en_defontana:
            continue  # ya no viene en ninguna de las dos planillas
        if not i.unidades_coinciden:
            pasos["unidad"].append((i, f"Cambiar en QMS la unidad {i.unidad_qms} por {i.unidad_defontana}"))
        costo_qms, costo_def = i.costo_unitario_qms, i.costo_unitario_defontana
        if costo_def and costo_qms != costo_def:
            pasos["costo"].append((i, f"Cambiar en QMS el costo de {format_clp(costo_qms or 0)} a {format_clp(costo_def)}"))
        elif not costo_def and costo_qms:
            pasos["costo"].append((i, f"Defontana no tiene costo: cargarlo en Defontana (QMS tiene {format_clp(costo_qms)}; confírmalo con la factura)"))
        elif not costo_def and not costo_qms and _tiene_stock(i):
            pasos["sin_costo"].append((i, "Cargar el costo en Defontana con la factura y luego en QMS"))
        if i.diferencia_sistemas != 0:
            pasos["stock"].append((
                i, f"Ajustar en QMS el stock de {format_cantidad(i.cantidad_qms or 0)} a {format_cantidad(i.cantidad_defontana or 0)}"
            ))
    return pasos


def _items_plan():
    return (
        ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id)
        .order_by(ItemConteoInventario.codigo)
        .all()
    )


@bp.route("/cruce-datos/plan")
@require_permission("inventario", "ver")
def cruce_datos_plan():
    """Paso a paso para regularizar el cruce QMS/Defontana, con Defontana como referencia."""
    pasos = _pasos_regularizar(_items_plan())
    return render_template(
        "inventario/cruce_datos_plan.html",
        pasos=[(n, clave, titulo, porque, pasos[clave]) for n, (clave, titulo, porque) in enumerate(PASOS_REGULARIZAR, start=1)],
        total=sum(len(v) for v in pasos.values()),
        limite=300,
    )


@bp.route("/cruce-datos/plan.xlsx")
@require_permission("inventario", "ver")
def cruce_datos_plan_excel():
    """El plan en Excel: una hoja por paso."""
    pasos = _pasos_regularizar(_items_plan())
    columnas = [
        col("#", ancho=6),
        col("Código", ancho=20, total="texto"),
        col("Descripción", ancho=44),
        col("Línea de negocio", ancho=20),
        col("Unidad QMS", ancho=12),
        col("Unidad Defontana", ancho=17),
        col("Costo QMS", ancho=14, formato=CLP),
        col("Costo Defontana", ancho=16, formato=CLP),
        col("Stock QMS", ancho=12, formato=CANTIDAD),
        col("Stock Defontana", ancho=15, formato=CANTIDAD),
        col("Qué hacer", ancho=60),
        col("Hecho", ancho=8),
    ]
    hojas = []
    for numero, (clave, titulo, porque) in enumerate(PASOS_REGULARIZAR, start=1):
        filas = [
            [
                n, i.codigo, i.nombre or "", i.linea_negocio or "",
                i.unidad_qms or "", i.unidad_defontana or "",
                i.costo_unitario_qms, i.costo_unitario_defontana,
                i.cantidad_qms, i.cantidad_defontana, accion, "",
            ]
            for n, (i, accion) in enumerate(pasos[clave], start=1)
        ]
        hojas.append((f"Paso {numero} - {titulo}", columnas, filas, porque))
    return responder_excel_hojas("regularizar-qms-defontana", hojas)


# --- Regularización: conteo físico contra el Informe de Documentos de Defontana ---


@bp.route("/regularizacion")
@require_permission("inventario", "ver")
def regularizacion():
    """Cruce de un conteo físico con el Informe de Documentos de Defontana.

    Es independiente de la toma de inventario: no lee "Stock y conteo" ni las
    tomas cerradas. Trabaja solo con los archivos que se suben aquí (conteo,
    informes y ajustes), que quedan guardados para no tener que volver a subirlos.
    El cálculo corre en el navegador (static/js/regularizacion.js).
    """
    registros = RegularizacionArchivo.query.filter_by(empresa_id=current_user.empresa_id).all()
    return _pagina_regularizacion(
        registros,
        url_para=lambda clave: url_for("inventario.regularizacion_guardado", clave=clave),
        puede_guardar=_puede_editar_regularizacion(),
        n_historial=RegularizacionHistorial.query.filter_by(empresa_id=current_user.empresa_id).count(),
    )


def _puede_editar_regularizacion():
    return current_user.tiene_permiso("inventario", "editar", submodulo="regularizacion")


def _pagina_regularizacion(registros, url_para, puede_guardar, historial=None, n_historial=0):
    """Pinta Regularización con los archivos indicados: los que están en uso o los de una guardada en el historial."""
    guardados = {
        g.clave: {
            "nombre": g.nombre or "",
            "fecha": format_fecha_hora(g.actualizado_en),
            "por": g.actualizado_por.nombre_completo if g.actualizado_por else "",
            "url": url_para(g.clave),
        }
        for g in registros
    }
    # Lo último que se actualizó (cada subida reemplaza la anterior y queda guardada)
    reciente = max(registros, key=lambda g: g.actualizado_en, default=None)
    ultima = guardados[reciente.clave] if reciente else None
    return render_template(
        "inventario/regularizacion.html",
        guardados=guardados,
        ultima=ultima,
        puede_guardar=puede_guardar,
        url_patron=url_para("__CLAVE__"),
        historial=historial,
        n_historial=n_historial,
    )


@bp.route("/regularizacion/archivar", methods=["POST"])
@require_permission("inventario", "ver")
def regularizacion_archivar():
    """Guarda en el historial la regularización en uso y deja la pantalla vacía para empezar una nueva."""
    if not _puede_editar_regularizacion():
        abort(403)
    registros = RegularizacionArchivo.query.filter_by(empresa_id=current_user.empresa_id).all()
    if not registros:
        flash("No hay nada que guardar: aún no se ha subido ningún archivo.", "warning")
        return redirect(url_for("inventario.regularizacion"))
    ahora = datetime.now(timezone.utc)
    nombre = (request.form.get("nombre") or "").strip()[:150] or f"Regularización del {format_fecha_hora(ahora)}"
    historial = RegularizacionHistorial(empresa_id=current_user.empresa_id, nombre=nombre, creado_en=ahora, creado_por_id=current_user.id)
    for g in registros:
        historial.archivos.append(RegularizacionHistorialArchivo(
            clave=g.clave, nombre=g.nombre, contenido=g.contenido,
            actualizado_en=g.actualizado_en, actualizado_por_id=g.actualizado_por_id,
        ))
        db.session.delete(g)
    db.session.add(historial)
    db.session.commit()
    flash(f"Se guardó \"{nombre}\" en el historial. Ya puedes subir la información nueva.", "success")
    return redirect(url_for("inventario.regularizacion"))


@bp.route("/regularizacion/historial")
@require_permission("inventario", "ver")
def regularizacion_historial():
    """Regularizaciones guardadas, de la más reciente a la más antigua."""
    lista = (RegularizacionHistorial.query.filter_by(empresa_id=current_user.empresa_id)
             .order_by(RegularizacionHistorial.creado_en.desc(), RegularizacionHistorial.id.desc()).all())
    return render_template(
        "inventario/regularizacion_historial.html",
        lista=lista,
        puede_borrar=_puede_editar_regularizacion(),
    )


def _historial_de_la_empresa(historial_id):
    historial = db.session.get(RegularizacionHistorial, historial_id)
    if historial is None or historial.empresa_id != current_user.empresa_id:
        abort(404)
    return historial


@bp.route("/regularizacion/historial/<int:historial_id>")
@require_permission("inventario", "ver")
def regularizacion_historial_ver(historial_id):
    """Abre una regularización guardada tal como quedó (solo lectura: no cambia lo guardado)."""
    historial = _historial_de_la_empresa(historial_id)
    return _pagina_regularizacion(
        historial.archivos,
        url_para=lambda clave: url_for("inventario.regularizacion_historial_archivo", historial_id=historial.id, clave=clave),
        puede_guardar=False,
        historial=historial,
    )


@bp.route("/regularizacion/historial/<int:historial_id>/archivo/<clave>")
@require_permission("inventario", "ver")
def regularizacion_historial_archivo(historial_id, clave):
    historial = _historial_de_la_empresa(historial_id)
    archivo = next((a for a in historial.archivos if a.clave == clave), None)
    if archivo is None:
        abort(404)
    respuesta = make_response(archivo.contenido)
    respuesta.headers["Content-Type"] = "application/json" if clave == "estado" else "application/octet-stream"
    if clave != "estado" and request.args.get("descargar"):
        respuesta.headers["Content-Disposition"] = f'attachment; filename="{(archivo.nombre or clave + ".xlsx").replace(chr(34), "")}"'
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@bp.route("/regularizacion/historial/<int:historial_id>/borrar", methods=["POST"])
@require_permission("inventario", "ver")
def regularizacion_historial_borrar(historial_id):
    if not _puede_editar_regularizacion():
        abort(403)
    historial = _historial_de_la_empresa(historial_id)
    nombre = historial.nombre
    db.session.delete(historial)
    db.session.commit()
    flash(f"Se borró \"{nombre}\" del historial.", "success")
    return redirect(url_for("inventario.regularizacion_historial"))


@bp.route("/regularizacion/guardado/<clave>", methods=["GET", "POST"])
@require_permission("inventario", "ver")
def regularizacion_guardado(clave):
    """Lee (GET) o guarda (POST) un informe o el estado del submódulo Regularización.

    Guardar reemplaza lo anterior y exige permiso de edición: lo guardado lo ven
    todos los que entran al submódulo.
    """
    if clave not in RegularizacionArchivo.CLAVES:
        abort(404)
    registro = RegularizacionArchivo.query.filter_by(empresa_id=current_user.empresa_id, clave=clave).first()

    if request.method == "GET":
        if registro is None:
            abort(404)
        respuesta = make_response(registro.contenido)
        respuesta.headers["Content-Type"] = "application/json" if clave == "estado" else "application/octet-stream"
        respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    if not _puede_editar_regularizacion():
        abort(403)
    if request.form.get("borrar"):
        if registro is not None:
            db.session.delete(registro)
            db.session.commit()
        return jsonify(ok=True)

    if clave == "estado":
        contenido, nombre = request.get_data(), None
        try:
            json.loads(contenido or b"{}")
        except ValueError:
            abort(400)
    else:
        archivo = request.files.get("archivo")
        if archivo is None or not archivo.filename:
            abort(400)
        contenido, nombre = archivo.read(), archivo.filename[:255]
    if not contenido:
        abort(400)

    if registro is None:
        registro = RegularizacionArchivo(empresa_id=current_user.empresa_id, clave=clave)
        db.session.add(registro)
    registro.contenido = contenido
    registro.nombre = nombre
    registro.actualizado_en = datetime.now(timezone.utc)
    registro.actualizado_por_id = current_user.id
    db.session.commit()
    return jsonify(ok=True, nombre=registro.nombre or "", fecha=format_fecha_hora(registro.actualizado_en), por=current_user.nombre_completo)


@bp.route("/conteo/importar", methods=["GET", "POST"])
@require_permission("inventario", "editar")
def conteo_importar():
    form_qms = ImportarCsvForm(prefix="qms")
    form_defontana = ImportarCsvForm(prefix="def")
    total_items = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id).count()
    return render_template(
        "inventario/conteo_importar.html", form_qms=form_qms, form_defontana=form_defontana, total_items=total_items
    )


@bp.route("/conteo/duplicados")
@require_permission("inventario", "editar")
def conteo_duplicados():
    """Artículos que ya no vienen en ninguna de las dos planillas.

    Los códigos repetidos se unen en "Unificar códigos": es la misma pregunta
    —estos dos son el mismo artículo— y tenerla en dos pantallas obligaba a
    saber de antemano en cuál de las dos estaba el caso que se tiene al frente.
    """
    fuera = articulos_fuera_de_ambas_planillas(current_user.empresa_id)
    return render_template(
        "inventario/conteo_duplicados.html",
        fuera=fuera,
        fuera_contados=[i for i in fuera if i.cantidad_fisica is not None],
        form=AccionForm(),
    )


@bp.route("/conteo/duplicados/unificar", methods=["POST"])
@require_permission("inventario", "editar")
def conteo_unificar_duplicados():
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)

    clave = (request.form.get("clave") or "").strip()
    grupos = grupos_duplicados(current_user.empresa_id)
    if clave:  # unificar solo el grupo pedido
        # La misma llave con que se arman los grupos: si acá se usara otra, el
        # botón de una fila no encontraría su grupo y no unificaría nada.
        grupos = [g for g in grupos if clave_sin_ceros(g[0].codigo) == clave]

    unificados = 0
    eliminados = 0
    for grupo in grupos:
        eliminados += len(grupo) - 1
        unificar_grupo(grupo, current_user.id)
        unificados += 1
    db.session.commit()

    if unificados:
        flash(
            f"Se unificaron {unificados} código(s); se juntaron {eliminados} línea(s) repetida(s). "
            "Queda guardado: las próximas importaciones no los van a volver a separar.",
            "success",
        )
    else:
        flash("No quedaban códigos repetidos por unificar.", "info")
    return redirect(url_for("inventario.equivalencias_codigos"))


@bp.route("/conteo/duplicados/eliminar-ausentes", methods=["POST"])
@require_permission("inventario", "editar")
def conteo_eliminar_ausentes():
    """Borra los artículos que ya no vienen ni en QMS ni en Defontana."""
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)

    ausentes = articulos_fuera_de_ambas_planillas(current_user.empresa_id)
    contados = sum(1 for i in ausentes if i.cantidad_fisica is not None)
    for item in ausentes:
        db.session.delete(item)
    db.session.commit()

    if ausentes:
        mensaje = f"Se eliminaron {len(ausentes)} artículo(s) que ya no aparecen en ninguna de las dos planillas."
        if contados:
            mensaje += f" De esos, {contados} tenía(n) conteo físico registrado."
        flash(mensaje, "success")
    else:
        flash("Todos los artículos aparecen en al menos una de las dos planillas.", "info")
    return redirect(url_for("inventario.conteo_duplicados"))


@bp.route("/conteo/importar/plantilla-qms")
@require_permission("inventario", "editar")
def conteo_plantilla_qms():
    return responder_plantilla_excel(
        "plantilla-qms",
        "QMS",
        [
            "Código único", "Descripción", "Stock", "Linea Negocio", "Sucursal",
            "Unidad", "Categoría", "Valor Unitario", "Valor Total",
        ],
        fila_ejemplo=["ROP-BCAN-M", "Roldana cable acero", 12, "Repuestos", "Bodega Central", "UN", "Componentes", 15000, 180000],
    )


@bp.route("/conteo/importar/plantilla-defontana")
@require_permission("inventario", "editar")
def conteo_plantilla_defontana():
    return responder_plantilla_excel(
        "plantilla-defontana",
        "Defontana",
        ["CodArticulo", "Descripción", "Saldo Stock", "Nombre Bodega", "Unidad", "Costo Unitario", "Valor Total"],
        fila_ejemplo=["ROP-BCAN-M", "Roldana cable acero", 12, "Bodega Central", "UN", 15000, 180000],
    )


def _avisar_fallo_de_importacion(error, sistema: str) -> None:
    """Deja un mensaje entendible en vez de una página de error.

    Si la importación revienta, la persona ve un "Internal Server Error" sin
    ninguna pista: no sabe si el archivo se cargó a medias, si tiene que
    reintentar, ni qué corregir. Se deshace lo escrito y se explica qué pasó.
    """
    db.session.rollback()
    detalle = str(getattr(error, "orig", error))
    if "out of range" in detalle or "too large" in detalle:
        mensaje = (
            f"No se pudo importar {sistema}: hay una cantidad o un costo demasiado grande "
            "en la planilla. Suele ser una celda con un número mal pegado, o la columna "
            "de valor total leída como costo unitario. Revisa el archivo y vuelve a subirlo."
        )
    elif "value too long" in detalle:
        mensaje = (
            f"No se pudo importar {sistema}: algún texto de la planilla es más largo de lo "
            "que admite el sistema. Revisa códigos y descripciones muy extensos."
        )
    else:
        mensaje = (
            f"No se pudo importar {sistema}. No se guardó nada, así que puedes corregir el "
            "archivo y volver a intentarlo. Detalle técnico: " + detalle[:200]
        )
    current_app.logger.exception("Falló la importación de %s", sistema)
    flash(mensaje, "danger")


def _resumen_importacion(resultado: dict) -> str:
    """Texto del aviso tras importar, mencionando los congelados sólo si los hubo."""
    detalle = [f"{resultado['creados']} nuevos", f"{resultado['actualizados']} actualizados"]
    if resultado.get("congelados"):
        detalle.append(f"{resultado['congelados']} sin tocar por estar ya contados")
    return f"{resultado['total_codigos']} códigos ({', '.join(detalle)})."


_NOMBRE_DEL_SISTEMA = {"qms": "QMS", "defontana": "Defontana"}


def _importar_un_sistema(sistema: str, archivo, solo_no_contados: bool) -> bool:
    """Carga una planilla y avisa cómo fue. Devuelve si quedó guardada.

    Lo usan por igual la pantalla de Importar y la de Cruce de datos: si cada
    una tuviera su copia, un arreglo en una se olvidaría en la otra.
    """
    nombre = _NOMBRE_DEL_SISTEMA[sistema]
    # El importador se elige acá y no en una tabla armada al cargar el módulo:
    # esa tabla se queda con la función de ese instante y deja de reflejar
    # cualquier cambio posterior sobre el nombre.
    importador = importar_qms if sistema == "qms" else importar_defontana
    try:
        resultado = importador(archivo, current_user.empresa_id, solo_no_contados)
        # Se deja el rastro dentro del mismo commit que el stock: si la
        # importación falla, tampoco queda dicho que ocurrió.
        registrar_importacion(
            current_user.empresa_id, sistema, archivo.filename,
            current_user.id, resultado,
        )
        db.session.commit()
        flash(f"{nombre} importado: {_resumen_importacion(resultado)}", "success")
        return True
    except ValueError as e:
        flash(str(e), "danger")
    except SQLAlchemyError as e:
        _avisar_fallo_de_importacion(e, nombre)
    return False


@bp.route("/conteo/importar/qms", methods=["POST"])
@require_permission("inventario", "editar")
def conteo_importar_qms():
    form = ImportarCsvForm(prefix="qms")
    if form.validate_on_submit():
        _importar_un_sistema("qms", form.archivo.data, form.solo_no_contados.data)
    else:
        flash("Selecciona un archivo .csv o .xlsx válido.", "danger")
    return redirect(url_for("inventario.conteo_importar"))


@bp.route("/conteo/importar/defontana", methods=["POST"])
@require_permission("inventario", "editar")
def conteo_importar_defontana():
    form = ImportarCsvForm(prefix="def")
    if form.validate_on_submit():
        _importar_un_sistema("defontana", form.archivo.data, form.solo_no_contados.data)
    else:
        flash("Selecciona un archivo .csv o .xlsx válido.", "danger")
    return redirect(url_for("inventario.conteo_importar"))


# --- Cruce de prueba: comparar dos planillas sin cargarlas al sistema ---
#
# El maestro de artículos es uno solo y lo miran todos los submódulos de
# Inventario. Para ver cómo quedaría un cruce no hace falta escribirlo: las dos
# planillas se leen, se comparan en memoria y lo único que se guarda es esa
# lectura, aparte, para que los filtros de la pantalla no obliguen a releer los
# archivos en cada clic. El maestro no se toca.
#
# Cargar de verdad sigue estando en Importar, que es donde dice que carga.


@bp.route("/cruce-datos/prueba", methods=["POST"])
@require_permission("inventario", "editar")
def cruce_prueba_subir():
    form = CruceDePruebaForm()
    if not form.validate_on_submit():
        for errores in form.errors.values():
            for error in errores:
                flash(error, "danger")
        return redirect(url_for("inventario.cruce_datos", subir="1"))

    try:
        lectura = {
            "qms": para_guardar(leer_qms(form.archivo_qms.data)),
            "defontana": para_guardar(leer_defontana(form.archivo_defontana.data)),
        }
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("inventario.cruce_datos", subir="1"))

    guardar_prueba(
        current_user.empresa_id, current_user.id, lectura,
        form.archivo_qms.data.filename, form.archivo_defontana.data.filename,
    )
    db.session.commit()
    return redirect(url_for("inventario.cruce_prueba"))


@bp.route("/cruce-datos/prueba")
@require_permission("inventario", "editar")
def cruce_prueba():
    """El cruce de las dos planillas subidas, sin que nada de esto se guarde."""
    prueba = prueba_en_curso(current_user.empresa_id, current_user.id)
    if prueba is None:
        flash("Sube las dos planillas para compararlas.", "info")
        return redirect(url_for("inventario.cruce_datos", subir="1"))

    items, busqueda, filtros_columna, filtro, orden, direccion, sin_vacios, vacios = (
        _items_de_la_prueba(prueba, request.args)
    )
    pagina = max(1, request.args.get("pagina", 1, type=int))
    por_pagina = 100
    total_paginas = max(1, (len(items) + por_pagina - 1) // por_pagina)
    pagina = min(pagina, total_paginas)

    return render_template(
        "inventario/cruce_prueba.html",
        prueba=prueba,
        items=items[(pagina - 1) * por_pagina : pagina * por_pagina],
        totales=_totales_cruce(items),
        q=busqueda,
        filtro=filtro,
        filtros_columna=filtros_columna,
        orden=orden,
        direccion=direccion,
        pagina=pagina,
        total_paginas=total_paginas,
        sin_vacios=sin_vacios,
        vacios=vacios,
        pares_de_unidades=_pares_de_unidades_distintas(items),
        form=AccionForm(),
    )


@bp.route("/cruce-datos/prueba.xlsx")
@require_permission("inventario", "editar")
def cruce_prueba_excel():
    """El cruce de prueba en Excel, con los mismos filtros de la pantalla."""
    prueba = prueba_en_curso(current_user.empresa_id, current_user.id)
    if prueba is None:
        abort(404)
    items, q, filtros_columna, filtro, _orden, _dir, sin_vacios, _vacios = _items_de_la_prueba(
        prueba, request.args
    )
    columnas, filas = _excel_del_cruce(items)
    return responder_excel(
        "cruce-de-prueba",
        "Cruce de prueba (no cargado al sistema)",
        columnas,
        filas,
        _descripcion_filtros(
            q, filtro, filtros_columna, ETIQUETAS_CRUCE,
            "sin los artículos sin stock ni costo" if sin_vacios else "",
        ),
    )


@bp.route("/cruce-datos/prueba/terminar", methods=["POST"])
@require_permission("inventario", "editar")
def cruce_prueba_terminar():
    form = AccionForm()
    if not form.validate_on_submit():
        abort(400)
    if borrar_prueba(current_user.empresa_id, current_user.id):
        db.session.commit()
        flash("Se descartó la comparación. En el sistema no había quedado nada.", "success")
    return redirect(url_for("inventario.cruce_datos"))


def _equivalencias_vigentes():
    """Las uniones que alguien ya confirmó, para no volver a preguntar por ellas.

    Se leen, no se cambian: sin esto la prueba mostraría como "Falta en QMS"
    pares que ya se resolvieron en Unificar códigos.
    """
    from app.utils.importar_conteo import _encadenar, _redirecciones_de_unificaciones, _traducciones_confirmadas

    return _encadenar(
        _traducciones_confirmadas(current_user.empresa_id),
        _redirecciones_de_unificaciones(current_user.empresa_id),
    )


def _items_de_la_prueba(prueba, args):
    """El mismo filtrado y orden del cruce, pero sobre la lista en memoria."""
    guardado = prueba.contenido
    items = comparar(guardado["qms"], guardado["defontana"], _equivalencias_vigentes())

    busqueda = (args.get("q") or "").strip()
    sin_vacios = esconder_vacios(args, True)
    if busqueda:
        patron = busqueda.lower()
        items = [
            i for i in items
            if patron in (i.codigo or "").lower() or patron in (i.nombre or "").lower()
        ]
        # Igual que en el cruce: buscar un artículo tiene que encontrarlo
        # aunque esté vacío, que es cuando más falta hace buscarlo.
        if (args.get("vacios") or "").strip() != "no":
            sin_vacios = False

    filtros_columna = {}
    for parametro, atributo in FILTROS_COLUMNA_PRUEBA.items():
        texto = (args.get(parametro) or "").strip()
        filtros_columna[parametro] = texto
        if texto:
            items = [i for i in items if texto.lower() in (getattr(i, atributo) or "").lower()]

    vacios = sum(1 for i in items if not _hay_algo_que_mirar(i))
    if sin_vacios:
        items = [i for i in items if _hay_algo_que_mirar(i)]

    filtro = args.get("filtro", "todos")
    if filtro not in FILTROS_CRUCE:
        filtro = "todos"
    if filtro in ETIQUETAS_ESTADO_MAESTRO:
        items = [i for i in items if i.estado_maestro == filtro]
    elif filtro == "costo_sin_stock":
        items = [i for i in items if i.costo_sin_stock]

    orden = args.get("orden") if args.get("orden") in ORDEN_PRUEBA else "codigo"
    direccion = "desc" if args.get("direccion") == "desc" else "asc"
    items = sorted(items, key=ORDEN_PRUEBA[orden], reverse=(direccion == "desc"))

    return items, busqueda, filtros_columna, filtro, orden, direccion, sin_vacios, vacios


FILTROS_COLUMNA_PRUEBA = {
    "f_codigo": "codigo",
    "f_nombre": "nombre",
    "f_unidad": "unidad_qms",
    "f_categoria": "categoria",
    "f_linea": "linea_negocio",
    "f_ubicacion": "ubicacion",
}


def _por_numero(nombre):
    """Ordena dejando los vacíos al final, que es donde no estorban."""
    return lambda i: (getattr(i, nombre) is None, getattr(i, nombre) or 0)


ORDEN_PRUEBA = {
    "codigo": lambda i: i.codigo or "",
    "nombre": lambda i: (i.nombre or "").lower(),
    "categoria": lambda i: (i.categoria or "").lower(),
    "cantidad_qms": _por_numero("cantidad_qms"),
    "cantidad_defontana": _por_numero("cantidad_defontana"),
    "costo_unitario_qms": _por_numero("costo_unitario_qms"),
    "costo_unitario_defontana": _por_numero("costo_unitario_defontana"),
}



# --- Equivalencias de códigos: el mismo artículo con otro código en cada sistema ---
#
# El mismo artículo debería existir en QMS y en Defontana: en eso consiste el
# cruce. Cuando el código se creó distinto en cada uno, el cruce por código no
# los encuentra y quedan dos filas sueltas, una "Falta en Defontana" y otra
# "Falta en QMS".
#
# Nada se une solo. Se proponen parejas y alguien confirma una por una: unir
# dos artículos distintos suma sus existencias y falsea el inventario.


def _sueltos(empresa_id):
    """Los que quedaron en un solo sistema, que son los candidatos a unir."""
    base = ItemConteoInventario.query.filter_by(empresa_id=empresa_id)
    solo_qms = base.filter(
        ItemConteoInventario.en_qms.is_(True), ItemConteoInventario.en_defontana.is_(False)
    ).order_by(ItemConteoInventario.codigo).all()
    solo_defo = base.filter(
        ItemConteoInventario.en_defontana.is_(True), ItemConteoInventario.en_qms.is_(False)
    ).order_by(ItemConteoInventario.codigo).all()
    return solo_qms, solo_defo


def _codigo_que_no_esta(codigo, sueltos, sistema) -> str:
    """Mensaje de error si el código no está entre los sueltos de ese sistema."""
    if not codigo:
        return f"Falta el código de {sistema}."
    clave = codigo_normalizado(codigo)
    if any(codigo_normalizado(i.codigo) == clave for i in sueltos):
        return ""
    return (
        f'No hay ningún artículo suelto en {sistema} con el código "{codigo}". '
        "Revisa cómo está escrito, o puede que ya cruce con el otro sistema."
    )


def estado_de_equivalencias(empresa_id) -> dict:
    """Todo lo que hace falta saber, para la pantalla y para el Excel.

    Van juntas a propósito: si el archivo se armara por su cuenta, podría
    proponer otras parejas que la pantalla, y se estaría trabajando sobre dos
    listas que no son la misma.
    """
    solo_qms, solo_defo = _sueltos(empresa_id)
    confirmadas = EquivalenciaCodigo.query.filter_by(
        empresa_id=empresa_id
    ).order_by(EquivalenciaCodigo.creado_en.desc()).all()
    unificados = CodigoUnificado.query.filter_by(
        empresa_id=empresa_id
    ).order_by(CodigoUnificado.creado_en.desc()).all()
    ya_unidos = {e.clave_qms for e in confirmadas}
    claves_unidas = {e.clave_defontana for e in confirmadas}

    # Lo ya confirmado sale de la lista de candidatos: se resolvió.
    pendientes_qms = [i for i in solo_qms if codigo_normalizado(i.codigo) not in ya_unidos]
    pendientes_defo = [i for i in solo_defo if codigo_normalizado(i.codigo) not in claves_unidas]
    propuestas = proponer(pendientes_qms, pendientes_defo)

    # Los que no alcanzaron ni una propuesta: son los que hay que revisar a
    # mano, y sin ellos el archivo no serviría para repartirse el trabajo.
    con_propuesta_qms = {p["qms"].id for p in propuestas}
    con_propuesta_defo = {p["defontana"].id for p in propuestas}
    return {
        "propuestas": propuestas,
        "confirmadas": confirmadas,
        "unificados": unificados,
        "pendientes_qms": pendientes_qms,
        "pendientes_defontana": pendientes_defo,
        "sin_pareja_qms": [i for i in pendientes_qms if i.id not in con_propuesta_qms],
        "sin_pareja_defontana": [i for i in pendientes_defo if i.id not in con_propuesta_defo],
    }


@bp.route("/equivalencias")
@require_permission("inventario", "editar")
def equivalencias_codigos():
    """Todo lo que es "el mismo artículo con dos códigos", en una sola pantalla.

    Son dos casos distintos por dentro y uno solo para quien mira: o el código
    quedó escrito de dos maneras en el maestro —"011-CON-OTH-01" y
    "11-CON-OTH-01"— y hay que dejar una sola línea, o cada sistema lo creó con
    su propio código y hay que enseñarle al cruce que son el mismo. Separarlos
    en dos pantallas obligaba a saber de antemano en cuál de los dos casos
    estaba el artículo que se tiene al frente.
    """
    datos = estado_de_equivalencias(current_user.empresa_id)
    return render_template(
        "inventario/equivalencias.html",
        propuestas=datos["propuestas"],
        solo_qms=datos["pendientes_qms"],
        solo_defontana=datos["pendientes_defontana"],
        confirmadas=datos["confirmadas"],
        unificados=datos["unificados"],
        grupos=grupos_duplicados(current_user.empresa_id),
        clave_sin_ceros=clave_sin_ceros,
        rarezas_del_codigo=rarezas_del_codigo,
        form=AccionForm(),
    )


def _absorber_fila_de_defontana(codigo_qms, codigo_defo, solo_qms, solo_defo) -> None:
    """Junta las dos filas en la de QMS y borra la de Defontana.

    Sin esto, la fila de Defontana queda de zombi: la próxima importación
    manda su stock a la fila de QMS —para eso es la equivalencia— y la vieja
    se queda con el saldo de antes y sin actualizarse nunca, apareciendo como
    un artículo que ya no está en ningún sistema.

    Lo que declara Defontana se copia tal cual; lo de QMS no se toca.
    """
    clave_qms = codigo_normalizado(codigo_qms)
    clave_defo = codigo_normalizado(codigo_defo)
    destino = next((i for i in solo_qms if codigo_normalizado(i.codigo) == clave_qms), None)
    origen = next((i for i in solo_defo if codigo_normalizado(i.codigo) == clave_defo), None)
    if destino is None or origen is None or destino.id == origen.id:
        return

    destino.cantidad_defontana = origen.cantidad_defontana
    destino.unidad_defontana = origen.unidad_defontana
    destino.costo_unitario_defontana = origen.costo_unitario_defontana
    destino.en_defontana = True
    # Los datos de texto sólo se completan si al destino le faltaban.
    for campo in ("nombre", "ubicacion", "categoria", "linea_negocio"):
        if not getattr(destino, campo):
            setattr(destino, campo, getattr(origen, campo))
    # El conteo físico es trabajo de bodega: si sólo lo tiene el que se va, se
    # conserva; si el destino ya tenía uno, ese manda.
    if destino.cantidad_fisica is None and origen.cantidad_fisica is not None:
        destino.cantidad_fisica = origen.cantidad_fisica
        destino.contado_por_id = origen.contado_por_id
        destino.contado_en = origen.contado_en

    db.session.delete(origen)


@bp.route("/equivalencias/unir", methods=["POST"])
@require_permission("inventario", "editar")
def equivalencias_unir():
    """Confirma una pareja. Queda guardada y el importador la respeta siempre."""
    if not AccionForm().validate_on_submit():
        abort(400)

    codigo_qms = (request.form.get("codigo_qms") or "").strip()
    codigo_defo = (request.form.get("codigo_defontana") or "").strip()

    # Los códigos se escriben a mano, así que un dedazo no puede terminar en
    # una equivalencia hacia un artículo que no existe: eso no daría error
    # nunca y quedaría ahí, sin unir nada, sin que se note.
    solo_qms, solo_defo = _sueltos(current_user.empresa_id)
    faltante = _codigo_que_no_esta(codigo_qms, solo_qms, "QMS") or _codigo_que_no_esta(
        codigo_defo, solo_defo, "Defontana"
    )
    if faltante:
        flash(faltante, "warning")
        return redirect(url_for("inventario.equivalencias_codigos"))

    _equivalencia, error = crear_equivalencia(
        current_user.empresa_id, codigo_qms, codigo_defo, current_user.id,
        puntaje=request.form.get("puntaje", type=float),
        motivo=request.form.get("motivo"),
    )
    if error:
        flash(error, "warning")
        return redirect(url_for("inventario.equivalencias_codigos"))

    _absorber_fila_de_defontana(codigo_qms, codigo_defo, solo_qms, solo_defo)
    db.session.commit()
    flash(
        f"{codigo_defo} (Defontana) y {codigo_qms} (QMS) quedaron unidos. "
        "Se van a cruzar en todas las importaciones, desde la próxima.",
        "success",
    )
    return redirect(url_for("inventario.equivalencias_codigos"))


@bp.route("/equivalencias/<int:equivalencia_id>/deshacer", methods=["POST"])
@require_permission("inventario", "editar")
def equivalencias_deshacer(equivalencia_id):
    """Separa dos códigos que se habían unido por error."""
    if not AccionForm().validate_on_submit():
        abort(400)

    equivalencia = EquivalenciaCodigo.query.filter_by(
        id=equivalencia_id, empresa_id=current_user.empresa_id
    ).first_or_404()
    codigos = f"{equivalencia.codigo_defontana} y {equivalencia.codigo_qms}"
    db.session.delete(equivalencia)
    db.session.commit()
    flash(
        f"{codigos} vuelven a ser artículos separados. "
        "El stock ya cruzado se reordena en la próxima importación.",
        "success",
    )
    return redirect(url_for("inventario.equivalencias_codigos"))


@bp.route("/equivalencias/unificado/<int:unificacion_id>/separar", methods=["POST"])
@require_permission("inventario", "editar")
def unificacion_separar(unificacion_id):
    """Libera un código que se había retirado al unificar por error.

    No devuelve la línea borrada: eso lo hace la próxima importación, que es
    la que sabe el stock de hoy. Lo que hace es dejar de redirigir el código,
    que es lo que impedía que volviera.
    """
    if not AccionForm().validate_on_submit():
        abort(400)

    unificacion = CodigoUnificado.query.filter_by(
        id=unificacion_id, empresa_id=current_user.empresa_id
    ).first_or_404()
    retirado, vigente = unificacion.codigo_retirado, unificacion.codigo_vigente
    db.session.delete(unificacion)
    db.session.commit()
    flash(
        f"{retirado} deja de apuntar a {vigente}. "
        "Vuelve a tener línea propia en la próxima importación que lo traiga.",
        "success",
    )
    return redirect(url_for("inventario.equivalencias_codigos"))


@bp.route("/equivalencias.xlsx")
@require_permission("inventario", "editar")
def equivalencias_excel():
    """El trabajo de unificar códigos, en un archivo para revisar fuera de la pantalla.

    Cuatro hojas, que son las cuatro situaciones distintas: lo que falta
    confirmar, lo que ya se unió, y los que quedaron sueltos en cada sistema
    sin ninguna pareja propuesta. Esos últimos son los que hay que buscar a
    mano, así que son los que más se agradece poder repartir.
    """
    datos = estado_de_equivalencias(current_user.empresa_id)

    propuestas = [
        col("Código QMS", ancho=22, total="texto"),
        col("Descripción QMS", ancho=46),
        col("Stock QMS", ancho=12, formato=CANTIDAD),
        col("Código Defontana", ancho=22),
        col("Descripción Defontana", ancho=46),
        col("Stock Defontana", ancho=15, formato=CANTIDAD),
        col("Qué tan seguro", ancho=14, formato=PORCENTAJE),
        col("Por qué", ancho=52),
    ]
    filas_propuestas = [
        [p["qms"].codigo, p["qms"].nombre or "", p["qms"].cantidad_qms,
         p["defontana"].codigo, p["defontana"].nombre or "",
         p["defontana"].cantidad_defontana, p["puntaje"], p["motivo"]]
        for p in datos["propuestas"]
    ]

    unidos = [
        col("Código Defontana", ancho=22, total="texto"),
        col("Código QMS", ancho=22),
        col("Por qué se unieron", ancho=46),
        col("Qué tan seguro", ancho=14, formato=PORCENTAJE),
        col("Quién", ancho=26),
        col("Cuándo", ancho=18, formato=FECHA),
    ]
    filas_unidos = [
        [e.codigo_defontana, e.codigo_qms, e.motivo or "",
         (e.puntaje / 100) if e.puntaje else None,
         e.creado_por.nombre_completo if e.creado_por else "", e.creado_en]
        for e in datos["confirmadas"]
    ]

    def sueltos(items, campo_stock):
        columnas = [
            col("Código", ancho=22, total="texto"),
            col("Descripción", ancho=52),
            col("Stock", ancho=12, formato=CANTIDAD, total="suma"),
            col("Unidad", ancho=10),
            col("Ubicación", ancho=26),
            col("Categoría", ancho=24),
        ]
        filas = [
            [i.codigo, i.nombre or "", getattr(i, campo_stock),
             (i.unidad_qms or i.unidad_defontana or ""), i.ubicacion or "", i.categoria or ""]
            for i in items
        ]
        return columnas, filas

    col_solo_qms, filas_solo_qms = sueltos(datos["sin_pareja_qms"], "cantidad_qms")
    col_solo_defo, filas_solo_defo = sueltos(datos["sin_pareja_defontana"], "cantidad_defontana")

    hojas = [
        ("Por unir", propuestas, filas_propuestas,
         "Parejas propuestas: confirma una por una en la pantalla. Unir dos "
         "artículos distintos suma sus existencias."),
        ("Ya unidos", unidos, filas_unidos,
         "Equivalencias confirmadas: el importador las respeta en cada carga."),
        ("Sin pareja — QMS", col_solo_qms, filas_solo_qms,
         "Están solo en QMS y no se les encontró pareja: hay que buscarla a mano."),
        ("Sin pareja — Defontana", col_solo_defo, filas_solo_defo,
         "Están solo en Defontana y no se les encontró pareja: hay que buscarla a mano."),
    ]
    return responder_excel_hojas("unificar-codigos", hojas)
