from datetime import date

from flask import render_template, send_from_directory, current_app, abort
from flask_login import login_required, current_user

from app.core import bp
from app.models.contrato import ContratoCliente
from app.models.conteo_inventario import ItemConteoInventario
from app.models.activo_fijo import ActivoFijo
from app.models.arriendo import ArriendoEntrada, ArriendoSalida
from app.models.documento import Documento
from app.models.importacion import Importacion
from app.utils import importaciones_calculo as calculo_importaciones
from app.utils.estado_sistema import estado_del_sistema
from app.utils.graficos import COLOR, COLOR_ESTADO, serie, proximos_meses, widget_seguro


@bp.route("/healthz")
def healthz():
    """Chequeo de salud de Render: no toca la base a propósito.

    Si consultara la base, una caída momentánea de la conexión haría que Render
    diera la instancia por muerta y la reiniciara, empeorando el problema en vez
    de avisarlo. El diagnóstico de la base va en /estado, que es para mirar.
    """
    return "ok", 200


@bp.route("/estado")
@login_required
def estado():
    """Qué versión está corriendo y si la base está al día.

    Existe para no tener que adivinar cuando algo falla: dice si la base
    responde, en qué revisión está y cuántas migraciones le faltan respecto del
    código desplegado. El caso silencioso —código nuevo con base vieja— es el
    que más cuesta descubrir y acá salta de inmediato.
    """
    from app.extensions import db

    if not current_user.es_admin_o_superior:
        abort(403)
    return render_template("core/estado.html", estado=estado_del_sistema(db))


def _panel_inventario():
    """Indicadores y series del módulo de inventario para el tablero: ¿cuadran QMS y Defontana?"""
    items = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id).all()
    contados = [i for i in items if i.contado]
    con_diferencia = [i for i in items if i.tiene_diferencia]

    cuadrados = sum(1 for i in items if i.diferencia_sistemas == 0)
    con_dif_stock = len(items) - cuadrados

    top_diferencias = sorted(
        [i for i in items if i.diferencia_sistemas != 0],
        key=lambda i: abs(i.diferencia_sistemas),
        reverse=True,
    )[:6]

    return {
        "conteo_total": len(items),
        "cuadrados": cuadrados,
        "con_dif_stock": con_dif_stock,
        "grafico_cuadre": [
            serie("Cuadran QMS y Defontana", cuadrados, COLOR["verde"]),
            serie("Con diferencia de stock", con_dif_stock, COLOR["rojo"]),
        ],
        "grafico_conteo": [
            serie("Contados sin diferencia", len([i for i in contados if not i.tiene_diferencia]), COLOR["verde"]),
            serie("Contados con diferencia", len([i for i in contados if i.tiene_diferencia]), COLOR["ambar"]),
            serie("Pendientes de contar", len(items) - len(contados), COLOR["gris"]),
        ],
        "con_diferencia": len(con_diferencia),
        "articulos_con_diferencia": [
            {
                "codigo": i.codigo,
                "nombre": i.nombre,
                "qms": i.cantidad_qms,
                "defontana": i.cantidad_defontana,
                "diferencia": i.diferencia_sistemas,
            }
            for i in top_diferencias
        ],
    }


def _panel_contratos():
    """Estados de contratos, vencimientos por mes y flujo de arriendos."""
    hoy = date.today()
    contratos = ContratoCliente.query.all()
    estados = {"vigente": 0, "por_vencer": 0, "vencido": 0, "terminado": 0}
    for c in contratos:
        estados[c.estado] = estados.get(c.estado, 0) + 1

    por_vencer = sorted(
        [c for c in contratos if c.estado == "por_vencer"], key=lambda c: c.fecha_termino
    )

    # Contratos que terminan en cada uno de los próximos 6 meses
    vencimientos = []
    for anio, mes, etiqueta in proximos_meses(6):
        cantidad = sum(
            1
            for c in contratos
            if not c.terminado_manualmente
            and c.fecha_termino.year == anio
            and c.fecha_termino.month == mes
            and c.fecha_termino >= hoy
        )
        vencimientos.append(serie(etiqueta, cantidad, COLOR["azul"]))

    salidas = ArriendoSalida.query.all()
    entradas = ArriendoEntrada.query.all()
    salidas_activas = [s for s in salidas if s.estado in ("activo", "atrasado")]
    entradas_vigentes = [e for e in entradas if e.estado in ("vigente", "por_vencer")]
    ingreso = sum(s.monto_periodo for s in salidas_activas)
    gasto = sum(e.monto_periodo for e in entradas_vigentes)

    return {
        "total": len(contratos),
        "vigentes": estados.get("vigente", 0),
        "por_vencer": estados.get("por_vencer", 0),
        "vencidos": estados.get("vencido", 0),
        "monto_vigente": sum(c.monto for c in contratos if c.estado == "vigente"),
        "contratos_por_vencer": por_vencer[:6],
        "grafico_estados": [
            serie("Vigentes", estados.get("vigente", 0), COLOR_ESTADO["vigente"]),
            serie("Por vencer", estados.get("por_vencer", 0), COLOR_ESTADO["por_vencer"]),
            serie("Vencidos", estados.get("vencido", 0), COLOR_ESTADO["vencido"]),
            serie("Terminados", estados.get("terminado", 0), COLOR_ESTADO["terminado"]),
        ],
        "grafico_vencimientos": vencimientos,
        "ingreso_arriendos": ingreso,
        "gasto_arriendos": gasto,
        "grafico_flujo": [
            serie("Ingreso por arriendos", ingreso, COLOR["verde"], texto=_clp(ingreso)),
            serie("Gasto por arriendos", gasto, COLOR["rojo"], texto=_clp(gasto)),
        ],
        "arriendos_por_vencer": sorted(
            [e for e in entradas if e.estado == "por_vencer"], key=lambda e: e.fecha_termino
        )[:6],
        "salidas_activas": len(salidas_activas),
    }


def _panel_activos():
    """Valor libro por categoría y estado de la flota de activos."""
    activos = ActivoFijo.query.all()
    vigentes = [a for a in activos if a.estado == "activo"]

    por_categoria = {}
    for a in vigentes:
        nombre = a.categoria or "Sin categoría"
        por_categoria[nombre] = por_categoria.get(nombre, 0) + a.valor_libro
    top = sorted(por_categoria.items(), key=lambda x: x[1], reverse=True)[:6]
    paleta = [COLOR["ambar"], COLOR["azul"], COLOR["teal"], COLOR["morado"], COLOR["gris"], COLOR["azul_claro"]]

    estados = {}
    for a in activos:
        estados[a.estado] = estados.get(a.estado, 0) + 1
    etiquetas_estado = {
        "activo": ("En uso", COLOR["verde"]),
        "en_mantenimiento": ("En mantención", COLOR["ambar"]),
        "dado_de_baja": ("Dados de baja", COLOR["gris"]),
        "vendido": ("Vendidos", COLOR["morado"]),
    }

    return {
        "total": len(vigentes),
        "valor_libro": sum(a.valor_libro for a in vigentes),
        "depreciacion_mensual": sum(a.depreciacion_mensual for a in vigentes),
        "arrendados": sum(1 for a in vigentes if a.es_arrendable and a.arrendado_actualmente),
        "grafico_categorias": [
            serie(nombre, valor, paleta[idx % len(paleta)], texto=_clp(valor))
            for idx, (nombre, valor) in enumerate(top)
        ],
        "grafico_estados": [
            serie(etiquetas_estado.get(clave, (clave, COLOR["gris"]))[0], cantidad,
                  etiquetas_estado.get(clave, (clave, COLOR["gris"]))[1])
            for clave, cantidad in estados.items()
        ],
    }


def _panel_importaciones():
    """Saldos con agencias y alertas de cuadratura del módulo de importaciones."""
    importaciones = Importacion.query.filter_by(empresa_id=current_user.empresa_id).all()

    favor_total = sum(i.saldo_signado for i in importaciones if i.saldo_signado >= 0)
    contra_total = sum(-i.saldo_signado for i in importaciones if i.saldo_signado < 0)
    con_descuadre = [i for i in importaciones if calculo_importaciones.tiene_descuadre(i)]
    con_notas = [i for i in importaciones if i.notas and i.notas.strip()]

    return {
        "total": len(importaciones),
        "monto_total": sum(i.monto or 0 for i in importaciones),
        "favor_total": favor_total,
        "contra_total": contra_total,
        "alertas": len({i.id for i in con_descuadre} | {i.id for i in con_notas}),
        "grafico_saldo": [
            serie("A favor", favor_total, COLOR["verde"]),
            serie("En contra", contra_total, COLOR["rojo"]),
        ],
    }


def _clp(monto) -> str:
    return "${:,.0f}".format(monto or 0).replace(",", ".")


@bp.route("/")
@login_required
def dashboard():
    """Tablero de indicadores. Cada panel se calcula por separado: si uno falla,
    el resto de la página se sigue mostrando."""
    inventario = None
    contratos = None
    activos = None
    importaciones = None

    if current_user.tiene_permiso("inventario", "ver"):
        inventario = widget_seguro(_panel_inventario, nombre="panel de inventario")
    if current_user.tiene_permiso("contratos", "ver"):
        contratos = widget_seguro(_panel_contratos, nombre="panel de contratos")
    if current_user.tiene_permiso("activos_fijos", "ver"):
        activos = widget_seguro(_panel_activos, nombre="panel de activos fijos")
    if current_user.tiene_permiso("importaciones", "ver"):
        importaciones = widget_seguro(_panel_importaciones, nombre="panel de importaciones")

    return render_template(
        "core/dashboard.html",
        inventario=inventario,
        contratos=contratos,
        activos=activos,
        importaciones=importaciones,
        hoy=date.today(),
    )


@bp.route("/documentos/<int:documento_id>/descargar")
@login_required
def descargar_documento(documento_id):
    documento = Documento.query.get_or_404(documento_id)
    permisos_por_entidad = {
        "movimiento_inventario": "inventario",
        "contrato_cliente": "contratos",
        "activo_fijo": "activos_fijos",
        "arriendo_salida": "arriendos",
        "arriendo_entrada": "arriendos",
    }
    modulo = permisos_por_entidad.get(documento.entidad_tipo)
    if modulo is None or not current_user.tiene_permiso(modulo, "ver"):
        abort(403)

    if current_app.config["STORAGE_BACKEND"] != "local":
        abort(404)

    carpeta_base = current_app.config["UPLOAD_FOLDER"]
    return send_from_directory(
        carpeta_base, documento.ruta_archivo, as_attachment=True, download_name=documento.nombre_archivo
    )
