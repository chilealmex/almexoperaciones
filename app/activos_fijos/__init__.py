from flask import Blueprint

bp = Blueprint("activos_fijos", __name__)

from app.activos_fijos import routes  # noqa: E402,F401
