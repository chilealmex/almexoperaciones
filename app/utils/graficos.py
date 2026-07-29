"""Paleta y utilidades para los gráficos de los tableros.

Los colores viven en Python (y no sólo en el CSS) porque las series se arman en
las vistas: así el mismo concepto usa siempre el mismo color en toda la app.
"""

from datetime import date

from flask import current_app

COLOR = {
    "azul": "#1c5f8f",
    "azul_claro": "#2a7cb0",
    "verde": "#1a7f5a",
    "teal": "#2a9d8f",
    "ambar": "#d9a13b",
    "rojo": "#b03a30",
    "morado": "#4a5578",
    "gris": "#9aa8b8",
}

# Colores por estado, consistentes en todos los módulos
COLOR_ESTADO = {
    "vigente": COLOR["verde"],
    "activo": COLOR["verde"],
    "por_vencer": COLOR["ambar"],
    "vencido": COLOR["rojo"],
    "atrasado": COLOR["rojo"],
    "terminado": COLOR["gris"],
    "finalizado": COLOR["gris"],
}

MESES_CORTOS = (
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
)


def serie(etiqueta, valor, color, texto=None):
    """Punto de una serie para los macros de gráficos."""
    return {"etiqueta": etiqueta, "valor": valor or 0, "color": color, "texto": texto}


def etiqueta_mes(anio: int, mes: int) -> str:
    return f"{MESES_CORTOS[mes - 1]} {str(anio)[2:]}"


def proximos_meses(cantidad: int = 6, desde: date | None = None):
    """[(año, mes, 'ene 26'), ...] a partir del mes actual."""
    inicio = desde or date.today()
    resultado = []
    anio, mes = inicio.year, inicio.month
    for _ in range(cantidad):
        resultado.append((anio, mes, etiqueta_mes(anio, mes)))
        mes += 1
        if mes > 12:
            mes = 1
            anio += 1
    return resultado


def widget_seguro(calcular, por_defecto=None, nombre="widget"):
    """Ejecuta el cálculo de un panel y, si falla, devuelve un valor por defecto.

    Un tablero está hecho de muchos indicadores independientes: que uno falle no
    debe dejar al usuario sin la página completa.
    """
    try:
        return calcular()
    except Exception:
        current_app.logger.exception("No se pudo calcular %s", nombre)
        return por_defecto
