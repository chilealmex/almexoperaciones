from datetime import timezone
from zoneinfo import ZoneInfo

# Las fechas se guardan en UTC y se muestran en hora de Chile continental.
ZONA_LOCAL = ZoneInfo("America/Santiago")


def format_clp(monto) -> str:
    if monto is None:
        return "$0"
    return "${:,.0f}".format(monto).replace(",", ".")


def format_fecha(value) -> str:
    if value is None:
        return ""
    return value.strftime("%d-%m-%Y")


def a_hora_local(value):
    """Pasa un instante guardado en UTC a la hora local de Chile."""
    if value is None:
        return None
    if value.tzinfo is None:  # la base devuelve datetimes sin zona, guardados en UTC
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZONA_LOCAL)


def format_fecha_hora(value) -> str:
    """Fecha y hora local, para saber cuándo se registró un dato."""
    local = a_hora_local(value)
    if local is None:
        return ""
    return local.strftime("%d-%m-%Y %H:%M")


def register_filters(app):
    app.jinja_env.filters["clp"] = format_clp
    app.jinja_env.filters["fecha"] = format_fecha
    app.jinja_env.filters["fecha_hora"] = format_fecha_hora
