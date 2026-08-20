"""La pantalla de estado del sistema.

Existe para responder, cuando algo falla, tres preguntas que hasta ahora había
que adivinar: ¿responde la base?, ¿en qué versión está?, ¿coincide con el
código desplegado? El caso importante es el silencioso: código nuevo con base
vieja, que arranca bien y falla recién al abrir una pantalla nueva.
"""

from app.utils.estado_sistema import (
    cadena_de_migraciones,
    estado_del_sistema,
    revision_del_codigo,
)
from tests.conftest import login


def _migraciones(tmp_path, cadena):
    """Escribe migraciones de mentira con la cadena pedida: {revisión: anterior}."""
    for revision, anterior in cadena.items():
        anterior_txt = f'"{anterior}"' if anterior else "None"
        (tmp_path / f"{revision}_x.py").write_text(
            f'revision = "{revision}"\ndown_revision = {anterior_txt}\n', encoding="utf-8"
        )
    return tmp_path


# --- Leer la cadena de migraciones ---


def test_la_cadena_se_lee_de_los_archivos(tmp_path):
    _migraciones(tmp_path, {"aaa": None, "bbb": "aaa", "ccc": "bbb"})
    assert cadena_de_migraciones(tmp_path) == {"aaa": None, "bbb": "aaa", "ccc": "bbb"}


def test_la_revision_del_codigo_es_la_ultima_de_la_cadena(tmp_path):
    _migraciones(tmp_path, {"aaa": None, "bbb": "aaa", "ccc": "bbb"})
    assert revision_del_codigo(tmp_path) == "ccc"


def test_dos_migraciones_en_paralelo_se_detectan(tmp_path):
    """Es lo que hace fallar el despliegue con 'Multiple head revisions'."""
    _migraciones(tmp_path, {"aaa": None, "bbb": "aaa", "ccc": "aaa"})
    assert sorted(revision_del_codigo(tmp_path)) == ["bbb", "ccc"]


def test_el_proyecto_real_tiene_una_sola_cabeza():
    """Guarda de verdad: si alguien agrega una migración en paralelo, esto falla.

    Sin esto, el descuadre aparece recién en el despliegue, con el sitio a
    medio actualizar.
    """
    cabeza = revision_del_codigo()
    assert isinstance(cabeza, str), f"hay migraciones sin unir: {cabeza}"


# --- El diagnóstico completo ---


def test_una_base_al_dia_se_informa_como_tal(tmp_path):
    _migraciones(tmp_path, {"aaa": None, "bbb": "aaa"})

    estado = estado_del_sistema(_BaseFalsa("bbb"), tmp_path)

    assert estado["base_responde"] is True
    assert estado["revision_base"] == "bbb"
    assert estado["revision_codigo"] == "bbb"
    assert estado["pendientes"] == []
    assert estado["al_dia"] is True


def test_una_base_atrasada_dice_cuantas_migraciones_faltan(tmp_path):
    _migraciones(tmp_path, {"aaa": None, "bbb": "aaa", "ccc": "bbb", "ddd": "ccc"})

    estado = estado_del_sistema(_BaseFalsa("bbb"), tmp_path)

    assert estado["al_dia"] is False
    assert estado["revision_base"] == "bbb"
    assert estado["revision_codigo"] == "ddd"
    # En orden de aplicación, no al revés
    assert estado["pendientes"] == ["ccc", "ddd"]


def test_si_la_base_no_responde_se_informa_sin_reventar(tmp_path):
    _migraciones(tmp_path, {"aaa": None})

    estado = estado_del_sistema(_BaseRota("conexión rechazada"), tmp_path)

    assert estado["base_responde"] is False
    assert "conexión rechazada" in estado["error_base"]
    assert estado["al_dia"] is False
    # La pantalla tiene que poder dibujarse igual: no se propaga la excepción.


def test_las_migraciones_en_paralelo_salen_en_el_estado(tmp_path):
    _migraciones(tmp_path, {"aaa": None, "bbb": "aaa", "ccc": "aaa"})

    estado = estado_del_sistema(_BaseFalsa("aaa"), tmp_path)

    assert sorted(estado["cabezas_multiples"]) == ["bbb", "ccc"]
    assert estado["al_dia"] is False


# --- La pantalla ---


def test_la_pantalla_la_ve_un_admin(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    respuesta = client.get("/estado")

    assert respuesta.status_code == 200
    body = respuesta.get_data(as_text=True)
    assert "Estado del sistema" in body
    assert "Versión que espera el código" in body


def test_la_pantalla_no_la_ve_cualquiera(client, db, empresa, usuario_bodega):
    login(client, "bodega@test.cl")
    assert client.get("/estado").status_code == 403


def test_la_pantalla_pide_sesion(client, db, empresa):
    respuesta = client.get("/estado")
    assert respuesta.status_code in (302, 401)


def test_el_enlace_aparece_en_el_menu_para_un_admin(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    assert "/estado" in client.get("/").get_data(as_text=True)


def test_healthz_sigue_sin_tocar_la_base(client, db, empresa):
    """Si consultara la base, una caída momentánea haría que Render reiniciara
    la instancia en vez de sólo avisar."""
    from unittest.mock import patch

    with patch("app.extensions.db.session.execute", side_effect=AssertionError("no debe consultar")):
        respuesta = client.get("/healthz")

    assert respuesta.status_code == 200
    assert respuesta.get_data(as_text=True) == "ok"


# --- Dobles de prueba ---


class _Dialecto:
    name = "sqlite"


class _Motor:
    dialect = _Dialecto()


class _Sesion:
    def __init__(self, revision):
        self._revision = revision

    def execute(self, *_args, **_kwargs):
        return _Resultado(self._revision)

    def rollback(self):
        pass

    def remove(self):
        pass


class _Resultado:
    def __init__(self, valor):
        self._valor = valor

    def scalar(self):
        return self._valor


class _BaseFalsa:
    """Una base que responde con la revisión que se le indique."""

    def __init__(self, revision):
        self.session = _Sesion(revision)
        self.engine = _Motor()


class _SesionRota(_Sesion):
    def execute(self, *_args, **_kwargs):
        raise RuntimeError(self._revision)


class _BaseRota(_BaseFalsa):
    """Una base que falla al consultarla, como cuando se cae la conexión."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.session = _SesionRota(mensaje)
