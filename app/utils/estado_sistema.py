"""Estado del sistema: qué versión está corriendo y si la base está al día.

Cuando algo va mal, la única señal suele ser que el sitio no carga, y de ahí
hay que ir adivinando: ¿falló el despliegue?, ¿corrió la migración?, ¿la base
responde? Este módulo responde esas tres preguntas en un solo lugar.

El caso que más cuesta detectar es que el código se despliegue pero la
migración no llegue a aplicarse: la aplicación arranca igual, y recién falla
cuando alguien entra a la pantalla que usa la tabla nueva. Comparar la revisión
que espera el código contra la que tiene la base lo deja a la vista antes.
"""

import os
import re
from pathlib import Path

_RE_REVISION = re.compile(r"^revision\s*=\s*[\"'](\w+)[\"']", re.M)
_RE_ANTERIOR = re.compile(r"^down_revision\s*=\s*[\"'](\w+)[\"']", re.M)


def _carpeta_de_migraciones() -> Path:
    return Path(__file__).resolve().parents[2] / "migrations" / "versions"


def cadena_de_migraciones(carpeta=None) -> dict:
    """Lee las migraciones del proyecto: {revisión: revisión anterior}."""
    carpeta = Path(carpeta) if carpeta else _carpeta_de_migraciones()
    cadena = {}
    if not carpeta.is_dir():
        return cadena
    for archivo in carpeta.glob("*.py"):
        texto = archivo.read_text(encoding="utf-8", errors="replace")
        revision = _RE_REVISION.search(texto)
        if not revision:
            continue
        anterior = _RE_ANTERIOR.search(texto)
        cadena[revision.group(1)] = anterior.group(1) if anterior else None
    return cadena


def revision_del_codigo(carpeta=None):
    """Última migración que trae el código: la que nadie declara como anterior.

    Si aparece más de una, es que dos ramas agregaron migraciones en paralelo y
    'flask db upgrade' va a fallar con "Multiple head revisions". Vale la pena
    verlo en la pantalla de estado antes de que reviente el despliegue.
    """
    cadena = cadena_de_migraciones(carpeta)
    anteriores = {anterior for anterior in cadena.values() if anterior}
    cabezas = sorted(revision for revision in cadena if revision not in anteriores)
    if len(cabezas) == 1:
        return cabezas[0]
    return cabezas or None


def _faltantes(cadena, desde, hasta) -> list:
    """Migraciones que hay entre la revisión de la base y la del código."""
    if not hasta or desde == hasta:
        return []
    faltan, actual = [], hasta
    while actual and actual != desde:
        faltan.append(actual)
        actual = cadena.get(actual)
        if actual is None and desde is not None:
            # La revisión de la base no está en la cadena: no se puede comparar.
            return faltan
    return list(reversed(faltan))


def estado_del_sistema(db, carpeta_migraciones=None) -> dict:
    """Diagnóstico completo, sin lanzar excepciones.

    Está pensado para una pantalla que se abre justamente cuando algo falla,
    así que ningún problema de la base puede tumbarla: si la consulta revienta,
    se informa el error en vez de propagarlo.
    """
    from sqlalchemy import text

    revision_codigo = revision_del_codigo(carpeta_migraciones)
    if isinstance(revision_codigo, list):  # varias cabezas
        cabezas = revision_codigo
        revision_codigo = None
    else:
        cabezas = []

    revision_base, error = None, None
    try:
        revision_base = db.session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
    except Exception as fallo:  # la base puede estar caída, sin permisos o vacía
        error = str(fallo).splitlines()[0][:300]
        try:
            db.session.rollback()
        except Exception:
            db.session.remove()

    cadena = cadena_de_migraciones(carpeta_migraciones)
    pendientes = _faltantes(cadena, revision_base, revision_codigo) if not error else []

    return {
        "base_responde": error is None,
        "error_base": error,
        "revision_base": revision_base,
        "revision_codigo": revision_codigo,
        "cabezas_multiples": cabezas,
        "pendientes": pendientes,
        "al_dia": error is None and not pendientes and not cabezas,
        "total_migraciones": len(cadena),
        "commit": (os.environ.get("RENDER_GIT_COMMIT") or "")[:12] or None,
        "entorno": os.environ.get("FLASK_ENV", "development"),
        # El motor real importa: en desarrollo es SQLite y en producción
        # PostgreSQL, y varios errores sólo se ven en uno de los dos.
        "motor": db.engine.dialect.name,
    }
