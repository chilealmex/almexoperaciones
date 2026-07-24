import os

from flask import Flask, render_template

from app.config import CONFIG_MAP
from app.extensions import db, migrate, login_manager, csrf
from app.utils.formatting import register_filters


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(CONFIG_MAP[config_name])

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    register_filters(app)

    from app.models.usuario import Usuario

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(Usuario, int(user_id))

    from app.utils.decorators import require_permission

    @app.context_processor
    def inject_permission_helper():
        from flask_login import current_user

        def puede(modulo, accion="ver"):
            return current_user.is_authenticated and current_user.tiene_permiso(modulo, accion)

        return {"puede": puede}

    from app.auth import bp as auth_bp
    from app.core import bp as core_bp
    from app.admin import bp as admin_bp
    from app.inventario import bp as inventario_bp
    from app.contratos import bp as contratos_bp
    from app.activos_fijos import bp as activos_fijos_bp
    from app.arriendos import bp as arriendos_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(core_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(inventario_bp, url_prefix="/inventario")
    app.register_blueprint(contratos_bp, url_prefix="/contratos")
    app.register_blueprint(activos_fijos_bp, url_prefix="/activos-fijos")
    app.register_blueprint(arriendos_bp, url_prefix="/arriendos")

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(_e):
        return render_template("errors/500.html"), 500

    return app
