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
from app.inventario.forms import AccionForm, ImportarCsvForm
from app.extensions import db
from app.models.conteo_inventario import ItemConteoInventario, TomaInventario, TomaInventarioDetalle
from app.models.equivalencia_codigo import EquivalenciaCodigo, crear_equivalencia
from app.models.importacion_inventario import registrar_importacion, ultimas_importaciones
from app.models.regularizacion import RegularizacionArchivo
from app.utils.decorators import require_permission
from app.utils.equivalencias_codigos import proponer
from app.utils.importar_conteo import (
    articulos_fuera_de_ambas_planillas,
    codigo_normalizado,
    grupos_duplicados,
    importar_defontana,
    rarezas_del_codigo,
    importar_qms,
    unificar_grupo,
)
from app.utils.cantidades import a_cantidad, punto_ambiguo
from app.utils.formatting import format_clp, format_fecha_hora
from app.utils.graficos import COLOR, serie, widget_seguro
from app.utils.paneles import panel_inventario
from app.utils.exportar import responder_excel, responder_plantilla_excel, col, CLP, CANTIDAD, FECHA, PORCENTAJE


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
    guardados = {
        g.clave: {
            "nombre": g.nombre or "",
            "fecha": format_fecha_hora(g.actualizado_en),
            "por": g.actualizado_por.nombre_completo if g.actualizado_por else "",
            "url": url_for("inventario.regularizacion_guardado", clave=g.clave),
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
        puede_guardar=current_user.tiene_permiso("inventario", "editar", submodulo="regularizacion"),
    )


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

    if not current_user.tiene_permiso("inventario", "editar", submodulo="regularizacion"):
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
    """Artículos repetidos: el mismo código escrito con o sin espacios/acentos."""
    fuera = articulos_fuera_de_ambas_planillas(current_user.empresa_id)
    return render_template(
        "inventario/conteo_duplicados.html",
        grupos=grupos_duplicados(current_user.empresa_id),
        fuera=fuera,
        fuera_contados=[i for i in fuera if i.cantidad_fisica is not None],
        form=AccionForm(),
        codigo_normalizado=codigo_normalizado,
        rarezas_del_codigo=rarezas_del_codigo,
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
        grupos = [g for g in grupos if codigo_normalizado(g[0].codigo) == clave]

    unificados = 0
    eliminados = 0
    for grupo in grupos:
        eliminados += len(grupo) - 1
        unificar_grupo(grupo)
        unificados += 1
    db.session.commit()

    if unificados:
        flash(f"Se unificaron {unificados} código(s); se juntaron {eliminados} línea(s) repetida(s).", "success")
    else:
        flash("No quedaban códigos repetidos por unificar.", "info")
    return redirect(url_for("inventario.conteo_duplicados"))


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


@bp.route("/conteo/importar/qms", methods=["POST"])
@require_permission("inventario", "editar")
def conteo_importar_qms():
    form = ImportarCsvForm(prefix="qms")
    if form.validate_on_submit():
        try:
            resultado = importar_qms(
                form.archivo.data, current_user.empresa_id, form.solo_no_contados.data
            )
            # Se deja el rastro dentro del mismo commit que el stock: si la
            # importación falla, tampoco queda dicho que ocurrió.
            registrar_importacion(
                current_user.empresa_id, "qms", form.archivo.data.filename,
                current_user.id, resultado,
            )
            db.session.commit()
            flash(f"QMS importado: {_resumen_importacion(resultado)}", "success")
        except ValueError as e:
            flash(str(e), "danger")
        except SQLAlchemyError as e:
            _avisar_fallo_de_importacion(e, "QMS")
    else:
        flash("Selecciona un archivo .csv o .xlsx válido.", "danger")
    return redirect(url_for("inventario.conteo_importar"))


@bp.route("/conteo/importar/defontana", methods=["POST"])
@require_permission("inventario", "editar")
def conteo_importar_defontana():
    form = ImportarCsvForm(prefix="def")
    if form.validate_on_submit():
        try:
            resultado = importar_defontana(
                form.archivo.data, current_user.empresa_id, form.solo_no_contados.data
            )
            # Se deja el rastro dentro del mismo commit que el stock: si la
            # importación falla, tampoco queda dicho que ocurrió.
            registrar_importacion(
                current_user.empresa_id, "defontana", form.archivo.data.filename,
                current_user.id, resultado,
            )
            db.session.commit()
            flash(f"Defontana importado: {_resumen_importacion(resultado)}", "success")
        except ValueError as e:
            flash(str(e), "danger")
        except SQLAlchemyError as e:
            _avisar_fallo_de_importacion(e, "Defontana")
    else:
        flash("Selecciona un archivo .csv o .xlsx válido.", "danger")
    return redirect(url_for("inventario.conteo_importar"))


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


@bp.route("/equivalencias")
@require_permission("inventario", "editar")
def equivalencias_codigos():
    """Propone qué artículo de QMS es el mismo que cuál de Defontana."""
    solo_qms, solo_defo = _sueltos(current_user.empresa_id)
    confirmadas = EquivalenciaCodigo.query.filter_by(
        empresa_id=current_user.empresa_id
    ).order_by(EquivalenciaCodigo.creado_en.desc()).all()
    ya_unidos = {e.clave_qms for e in confirmadas}
    claves_unidas = {e.clave_defontana for e in confirmadas}

    # Lo ya confirmado sale de la lista de candidatos: se resolvió.
    pendientes_qms = [i for i in solo_qms if codigo_normalizado(i.codigo) not in ya_unidos]
    pendientes_defo = [i for i in solo_defo if codigo_normalizado(i.codigo) not in claves_unidas]

    return render_template(
        "inventario/equivalencias.html",
        propuestas=proponer(pendientes_qms, pendientes_defo),
        solo_qms=pendientes_qms,
        solo_defontana=pendientes_defo,
        confirmadas=confirmadas,
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
