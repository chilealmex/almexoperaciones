from flask import Blueprint

bp = Blueprint("importaciones", __name__)

from app.importaciones import routes  # noqa: E402,F401
