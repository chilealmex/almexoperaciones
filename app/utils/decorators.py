from functools import wraps

from flask import abort, request
from flask_login import login_required, current_user


def require_permission(modulo: str, accion: str = "ver"):
    """Exige sesión iniciada y permiso sobre el módulo/acción indicados; si no, 403.

    Si el endpoint pertenece a un submódulo con override propio (definido en
    Usuarios > Permisos), también se exige ese permiso puntual; si el usuario
    no tiene un override para ese submódulo, hereda el del módulo completo.
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(*args, **kwargs):
            from app.utils.navegacion import ENDPOINT_A_SUBMODULO

            entrada = ENDPOINT_A_SUBMODULO.get(request.endpoint)
            if entrada is not None and entrada[0] == modulo:
                # tiene_permiso ya cae de vuelta al permiso del módulo si no hay
                # override propio del submódulo, así que esto reemplaza (no suma)
                # el chequeo de módulo cuando el endpoint pertenece a un submódulo.
                permitido = current_user.tiene_permiso(modulo, accion, submodulo=entrada[1])
            else:
                permitido = current_user.tiene_permiso(modulo, accion)

            if not permitido:
                abort(403)

            return view_func(*args, **kwargs)

        return wrapped

    return decorator
