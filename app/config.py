import os


def _normalizar_uri(uri: str) -> str:
    """Render y otros proveedores entregan 'postgres://', que SQLAlchemy 2 ya no acepta."""
    if uri.startswith("postgres://"):
        return uri.replace("postgres://", "postgresql://", 1)
    return uri


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = _normalizar_uri(
        os.environ.get(
            "DATABASE_URL", "sqlite:///" + os.path.join(os.getcwd(), "instance", "dev.db")
        )
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # pool_pre_ping descarta conexiones muertas antes de usarlas: evita los errores
    # "server closed the connection" cuando la base se duerme o se reinicia.
    # SQLite no usa pool de red, así que se deja sin opciones.
    SQLALCHEMY_ENGINE_OPTIONS = (
        {}
        if SQLALCHEMY_DATABASE_URI.startswith("sqlite")
        else {
            "pool_pre_ping": True,
            "pool_recycle": 280,
            # La base gratuita de Render corta las conexiones inactivas: keepalives
            # las mantienen vivas y un timeout corto evita peticiones colgadas.
            "connect_args": {
                "connect_timeout": 10,
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 3,
            },
        }
    )
    EMPRESA_ID = int(os.environ.get("EMPRESA_ID", "1"))

    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", os.path.join(os.getcwd(), "instance", "uploads")
    )
    R2_BUCKET = os.environ.get("R2_BUCKET")
    R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
    R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
    R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB por archivo subido


class DevConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProdConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = _normalizar_uri(
        os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    )
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SESSION_COOKIE_SECURE = False
    PROPAGAR_ERRORES = True  # en tests interesa ver la excepción real, no la página 500


CONFIG_MAP = {
    "development": DevConfig,
    "production": ProdConfig,
    "testing": TestConfig,
}
