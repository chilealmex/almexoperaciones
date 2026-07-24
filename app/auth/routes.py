import time
from collections import defaultdict
from datetime import datetime, timezone

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.auth import bp
from app.auth.forms import LoginForm
from app.extensions import db
from app.models.usuario import Usuario

_INTENTOS_LOGIN = defaultdict(list)
_MAX_INTENTOS = 10
_VENTANA_SEGUNDOS = 5 * 60


def _rate_limit_ok(ip: str) -> bool:
    ahora = time.time()
    intentos = _INTENTOS_LOGIN[ip]
    intentos[:] = [t for t in intentos if ahora - t < _VENTANA_SEGUNDOS]
    return len(intentos) < _MAX_INTENTOS


def _registrar_intento(ip: str) -> None:
    _INTENTOS_LOGIN[ip].append(time.time())


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("core.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        ip = request.remote_addr or "desconocida"
        if not _rate_limit_ok(ip):
            flash("Demasiados intentos. Intenta nuevamente en unos minutos.", "danger")
            return render_template("auth/login.html", form=form)

        usuario = Usuario.query.filter_by(email=form.email.data.lower().strip()).first()
        if usuario is None or not usuario.check_password(form.password.data) or not usuario.activo:
            _registrar_intento(ip)
            flash("Correo o contraseña incorrectos.", "danger")
            return render_template("auth/login.html", form=form)

        login_user(usuario, remember=form.recordarme.data)
        usuario.ultimo_login = datetime.now(timezone.utc)
        db.session.commit()
        siguiente = request.args.get("next")
        return redirect(siguiente or url_for("core.dashboard"))

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.login"))
