from flask import Blueprint

bp = Blueprint("datos_maestros", __name__)

from app.datos_maestros import routes  # noqa: E402,F401
