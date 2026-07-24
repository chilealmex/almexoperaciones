from functools import wraps

from flask import abort
from flask_login import login_required, current_user


def require_permission(modulo: str, accion: str = "ver"):
    """Exige sesión iniciada y permiso sobre el módulo/acción indicados; si no, 403."""

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.tiene_permiso(modulo, accion):
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator
