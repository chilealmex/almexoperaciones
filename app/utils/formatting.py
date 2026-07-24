def format_clp(monto) -> str:
    if monto is None:
        return "$0"
    return "${:,.0f}".format(monto).replace(",", ".")


def format_fecha(value) -> str:
    if value is None:
        return ""
    return value.strftime("%d-%m-%Y")


def register_filters(app):
    app.jinja_env.filters["clp"] = format_clp
    app.jinja_env.filters["fecha"] = format_fecha
