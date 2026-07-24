from flask import Blueprint

bp = Blueprint("contratos", __name__)

from app.contratos import routes  # noqa: E402,F401
