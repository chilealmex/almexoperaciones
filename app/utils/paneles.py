"""Cálculo de los paneles (indicadores + series de gráficos) de cada módulo.

Vive fuera de las vistas para que el tablero general y el resumen de cada módulo
muestren exactamente los mismos números.
"""

from datetime import date

from flask_login import current_user

from app.models.inventario import Producto
from app.models.contrato import ContratoCliente
from app.models.conteo_inventario import ItemConteoInventario
from app.models.activo_fijo import ActivoFijo
from app.models.arriendo import ArriendoEntrada, ArriendoSalida
from app.utils.formatting import format_clp as _clp
from app.utils.graficos import COLOR, COLOR_ESTADO, serie, proximos_meses


def panel_inventario():
    """Indicadores y series del módulo de inventario para el tablero."""
    productos = Producto.query.filter_by(activo=True).all()
    bajo_stock = [p for p in productos if p.bajo_stock_minimo]

    items = ItemConteoInventario.query.filter_by(empresa_id=current_user.empresa_id).all()
    contados = [i for i in items if i.contado]
    con_diferencia = [i for i in items if i.tiene_diferencia]

    # Valor de inventario por categoría (top 5)
    por_categoria = {}
    for p in productos:
        nombre = p.categoria.nombre if p.categoria else "Sin categoría"
        por_categoria[nombre] = por_categoria.get(nombre, 0) + p.stock_actual * p.precio_costo
    top_categorias = sorted(por_categoria.items(), key=lambda x: x[1], reverse=True)[:5]

    paleta = [COLOR["azul"], COLOR["azul_claro"], COLOR["teal"], COLOR["morado"], COLOR["gris"]]
    return {
        "productos": len(productos),
        "bajo_stock": len(bajo_stock),
        "valor_costo": sum(p.stock_actual * p.precio_costo for p in productos),
        "productos_bajo_stock": sorted(bajo_stock, key=lambda p: p.stock_actual - p.stock_minimo)[:6],
        "grafico_salud": [
            serie("Stock suficiente", len(productos) - len(bajo_stock), COLOR["verde"]),
            serie("Bajo el mínimo", len(bajo_stock), COLOR["rojo"]),
        ],
        "conteo_total": len(items),
        "grafico_conteo": [
            serie("Contados sin diferencia", len([i for i in contados if not i.tiene_diferencia]), COLOR["verde"]),
            serie("Contados con diferencia", len([i for i in contados if i.tiene_diferencia]), COLOR["ambar"]),
            serie("Pendientes de contar", len(items) - len(contados), COLOR["gris"]),
        ],
        "con_diferencia": len(con_diferencia),
        "grafico_categorias": [
            serie(nombre, valor, paleta[idx % len(paleta)], texto=_clp(valor))
            for idx, (nombre, valor) in enumerate(top_categorias)
        ],
    }


def panel_contratos():
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


def panel_activos():
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
