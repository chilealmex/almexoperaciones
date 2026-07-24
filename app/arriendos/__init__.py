from flask import Blueprint

bp = Blueprint("arriendos", __name__)

from app.arriendos import routes  # noqa: E402,F401
