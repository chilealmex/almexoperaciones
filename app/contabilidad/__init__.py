from flask import Blueprint

bp = Blueprint("contabilidad", __name__)

from app.contabilidad import routes  # noqa: E402,F401
