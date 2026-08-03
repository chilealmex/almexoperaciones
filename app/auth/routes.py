import time
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.auth import bp
from app.auth.forms import LoginForm, CambiarPasswordForm
from app.extensions import db
from app.models.usuario import Usuario

_INTENTOS_LOGIN = defaultdict(list)
_MAX_INTENTOS = 10
_VENTANA_SEGUNDOS = 5 * 60


def _next_seguro(destino: str | None) -> str | None:
    """Evita el open redirect: solo se sigue un 'next' que sea una ruta relativa propia."""
    if not destino:
        return None
    partes = urlparse(destino)
    if partes.netloc or partes.scheme:
        return None
    if not destino.startswith("/"):
        return None
    return destino


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

        identificador = form.identificador.data.strip().lower()
        usuario = Usuario.query.filter(
            db.or_(Usuario.nombre_usuario == identificador, Usuario.email == identificador)
        ).first()
        if usuario is None or not usuario.check_password(form.password.data) or not usuario.activo:
            _registrar_intento(ip)
            flash("Usuario/correo o contraseña incorrectos.", "danger")
            return render_template("auth/login.html", form=form)

        login_user(usuario, remember=form.recordarme.data)
        usuario.ultimo_login = datetime.now(timezone.utc)
        db.session.commit()
        siguiente = _next_seguro(request.args.get("next"))
        return redirect(siguiente or url_for("core.dashboard"))

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    form = CambiarPasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.password_actual.data):
            flash("La contraseña actual no es correcta.", "danger")
            return render_template("auth/perfil.html", form=form)

        current_user.set_password(form.password_nueva.data)
        db.session.commit()
        flash("Contraseña actualizada correctamente.", "success")
        return redirect(url_for("core.dashboard"))

    return render_template("auth/perfil.html", form=form)
