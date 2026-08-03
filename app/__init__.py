import logging
import os
import sys

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

from app.config import CONFIG_MAP
from app.extensions import db, migrate, login_manager, csrf
from app.utils.formatting import register_filters
from app.utils.navegacion import construir_navegacion, ENDPOINT_A_SUBMODULO

_SIN_ESPECIFICAR = object()


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(CONFIG_MAP[config_name])

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    app.config["VERSION_ESTATICA"] = _version_estatica(app)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    register_filters(app)

    from app.models.usuario import Usuario

    @login_manager.user_loader
    def load_user(user_id):
        """Carga al usuario de la sesión.

        Si la base de datos falla (la conexión de Render se cae al estar inactiva),
        se descarta la transacción rota y se devuelve None: la petición se trata
        como anónima en vez de arrastrar el error a la página de error, que
        también necesita al usuario para dibujar el menú.
        """
        try:
            return db.session.get(Usuario, int(user_id))
        except (ValueError, TypeError):
            return None
        except Exception:
            app.logger.exception("No se pudo cargar el usuario %s", user_id)
            try:
                db.session.rollback()
            except Exception:
                db.session.remove()
            return None

    from app.utils.decorators import require_permission

    @app.context_processor
    def inject_permission_helper():
        from flask_login import current_user

        def puede(modulo, accion="ver", submodulo=_SIN_ESPECIFICAR):
            if not current_user.is_authenticated:
                return False
            # Si la plantilla no indica el submódulo, se infiere del endpoint actual
            # (así "puede('inventario', 'editar')" dentro de stock.html respeta un
            # override puntual del submódulo "stock" sin que cada plantilla lo declare).
            if submodulo is _SIN_ESPECIFICAR:
                entrada = ENDPOINT_A_SUBMODULO.get(request.endpoint)
                submodulo = entrada[1] if entrada and entrada[0] == modulo else None
            return current_user.tiene_permiso(modulo, accion, submodulo=submodulo)

        nav = {"modulos": [], "modulo_activo": None, "submodulos": []}
        if current_user.is_authenticated:
            nav = construir_navegacion(request.endpoint, puede)

        def url_con(**cambios):
            """URL de la vista actual conservando los parámetros y cambiando sólo algunos.

            Sirve para ordenar, filtrar y paginar sin perder el resto de la consulta.
            Un valor None o vacío quita el parámetro.
            """
            if not request.endpoint:
                return "#"
            args = request.args.to_dict()
            args.update(request.view_args or {})
            for clave, valor in cambios.items():
                if valor in (None, ""):
                    args.pop(clave, None)
                else:
                    args[clave] = valor
            return url_for(request.endpoint, **args)

        return {
            "puede": puede,
            "nav": nav,
            "url_con": url_con,
            "version_estatica": app.config["VERSION_ESTATICA"],
        }

    from app.auth import bp as auth_bp
    from app.core import bp as core_bp
    from app.admin import bp as admin_bp
    from app.inventario import bp as inventario_bp
    from app.contratos import bp as contratos_bp
    from app.activos_fijos import bp as activos_fijos_bp
    from app.arriendos import bp as arriendos_bp
    from app.datos_maestros import bp as datos_maestros_bp
    from app.importaciones import bp as importaciones_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(core_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(inventario_bp, url_prefix="/inventario")
    app.register_blueprint(contratos_bp, url_prefix="/contratos")
    app.register_blueprint(activos_fijos_bp, url_prefix="/activos-fijos")
    app.register_blueprint(arriendos_bp, url_prefix="/arriendos")
    app.register_blueprint(datos_maestros_bp, url_prefix="/datos-maestros")
    app.register_blueprint(importaciones_bp, url_prefix="/importaciones")

    _configurar_logging(app)
    _registrar_manejo_de_errores(app)
    _registrar_cabeceras_de_seguridad(app)

    return app


def _version_estatica(app) -> str:
    """Marca de versión para los archivos estáticos, basada en la fecha del CSS."""
    try:
        css = os.path.join(app.static_folder, "css", "custom.css")
        return str(int(os.path.getmtime(css)))
    except OSError:
        return "1"


def _configurar_logging(app):
    """Deja el log en stdout para que el proveedor (Render) lo capture."""
    if app.logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s en %(module)s: %(message)s")
    )
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)


def _quiere_json() -> bool:
    """True si la petición espera JSON (fetch de la app) en vez de una página HTML."""
    if request.is_json or request.path.endswith(".json"):
        return True
    return request.accept_mimetypes.best == "application/json"


def _registrar_manejo_de_errores(app):
    """Ninguna excepción debe dejar al usuario frente a una pantalla en blanco."""

    def _pagina(plantilla, codigo, mensaje):
        # La página de error consulta la base (menú, usuario). Si la transacción
        # quedó rota, hay que descartarla antes de dibujarla o el error se repite.
        try:
            db.session.rollback()
        except Exception:
            db.session.remove()

        if _quiere_json():
            return jsonify({"ok": False, "error": mensaje}), codigo
        try:
            return render_template(plantilla, mensaje=mensaje), codigo
        except Exception:  # la propia página de error falló: respuesta mínima
            app.logger.exception("No se pudo renderizar %s", plantilla)
            return (
                "<!doctype html><meta charset='utf-8'>"
                f"<title>Error {codigo}</title>"
                f"<h1>{codigo}</h1><p>{mensaje}</p><p><a href='/'>Volver al inicio</a></p>",
                codigo,
            )

    @app.errorhandler(403)
    def forbidden(_e):
        return _pagina("errors/403.html", 403, "No tienes permiso para acceder a esta sección.")

    @app.errorhandler(404)
    def not_found(_e):
        return _pagina("errors/404.html", 404, "La página que buscas no existe.")

    @app.errorhandler(413)
    def archivo_muy_grande(_e):
        flash("El archivo supera el tamaño máximo permitido (16 MB).", "danger")
        destino = request.referrer or url_for("core.dashboard")
        return redirect(destino)

    @app.errorhandler(CSRFError)
    def csrf_expirado(_e):
        """Un formulario abierto demasiado tiempo no debe terminar en un error 400 crudo."""
        flash("Tu sesión expiró por seguridad. Vuelve a enviar el formulario.", "warning")
        return redirect(request.referrer or url_for("auth.login"))

    @app.errorhandler(HTTPException)
    def error_http(e):
        """Cualquier otro error HTTP (400, 405, 500...) con la misma cara que el resto."""
        return _pagina("errors/500.html", e.code or 500, e.description or "Solicitud inválida.")

    @app.errorhandler(Exception)
    def error_no_controlado(e):
        """Última red de seguridad: se registra el error, se descarta la transacción
        a medias y se responde con la página 500 en vez de caerse."""
        app.logger.exception("Error no controlado en %s %s", request.method, request.path)
        try:
            db.session.rollback()
        except Exception:
            app.logger.exception("No se pudo revertir la transacción")
        if app.config.get("PROPAGAR_ERRORES"):
            raise e
        return _pagina("errors/500.html", 500, "Ocurrió un error inesperado. Intenta nuevamente.")

    @app.teardown_request
    def cerrar_sesion_bd(exc):
        if exc is not None:
            try:
                db.session.rollback()
            except Exception:
                app.logger.exception("No se pudo revertir la transacción al cerrar la petición")


def _registrar_cabeceras_de_seguridad(app):
    """Cabeceras de seguridad en toda respuesta.

    Sin dominios externos que permitir: todo el CSS/JS de la app está servido
    desde /static (ver base.html), así que default-src 'self' no rompe nada.
    'unsafe-inline' queda en script-src/style-src porque varias plantillas usan
    onclick/onchange en línea (confirmaciones, auto-submit) y algún <script> con
    datos de Jinja incrustados; sacarlo del todo requeriría moverlos a JS externo.
    """
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )

    @app.after_request
    def _cabeceras(response):
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # HSTS solo tiene sentido si el sitio se sirve por HTTPS (así está configurado en
        # Render); en Dev/Test no se envía para no romper el http:// local.
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
