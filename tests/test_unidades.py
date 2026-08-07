"""Equivalencias de unidad de medida entre QMS y Defontana."""

import pytest

from app.models.conteo_inventario import ItemConteoInventario
from app.utils.unidades import son_equivalentes, unidad_normalizada


# Los pares que reportó la usuaria: QMS escribe el primero, Defontana el segundo.
PARES_IGUALES = [("M", "MT"), ("PK", "PACK"), ("L", "LT"), ("FT", "PIE"), ("RL", "ROLLO")]


@pytest.mark.parametrize("qms,defontana", PARES_IGUALES)
def test_los_pares_reportados_son_la_misma_unidad(qms, defontana):
    assert son_equivalentes(qms, defontana)
    assert son_equivalentes(defontana, qms)  # da igual el orden


@pytest.mark.parametrize("qms,defontana", [
    ("M", "KG"),      # metro contra kilo
    ("RL", "UN"),     # rollo contra unidad
    ("CM", "MM"),     # parecidas pero distintas de verdad
    ("PACK", "CAJA"),
])
def test_las_unidades_realmente_distintas_siguen_marcandose(qms, defontana):
    assert not son_equivalentes(qms, defontana)


def test_no_importan_mayusculas_espacios_ni_puntos():
    assert son_equivalentes(" mt. ", "M")
    assert son_equivalentes("Rollo", "rl")
    assert son_equivalentes("UNIDAD", "un")


def test_si_falta_la_unidad_en_un_sistema_no_es_diferencia():
    """Sin dato en uno de los dos no hay nada que contradecir."""
    assert son_equivalentes("MT", None)
    assert son_equivalentes("", "ROLLO")
    assert son_equivalentes(None, None)


def test_una_unidad_desconocida_se_compara_como_antes():
    """Las que no están en la tabla no se dan por equivalentes a la fuerza."""
    assert son_equivalentes("XYZ", "XYZ")
    assert not son_equivalentes("XYZ", "ABC")
    assert unidad_normalizada("XYZ") == "XYZ"


def test_el_articulo_deja_de_aparecer_con_distinta_unidad(db, empresa):
    item = ItemConteoInventario(empresa_id=empresa.id, codigo="COD-1", cantidad_qms=1,
                                cantidad_defontana=1, unidad_qms="M", unidad_defontana="MT",
                                costo_unitario_qms=100, costo_unitario_defontana=100)
    db.session.add(item)
    db.session.commit()

    assert item.unidades_coinciden is True
    assert item.par_de_unidades is None
    assert item.estado_maestro == "ok"


def test_el_articulo_con_unidad_de_verdad_distinta_se_sigue_marcando(db, empresa):
    item = ItemConteoInventario(empresa_id=empresa.id, codigo="COD-2", cantidad_qms=1,
                                cantidad_defontana=1, unidad_qms="M", unidad_defontana="KG",
                                costo_unitario_qms=100, costo_unitario_defontana=100)
    db.session.add(item)
    db.session.commit()

    assert item.unidades_coinciden is False
    assert item.par_de_unidades == "M → KG"
    assert item.estado_maestro == "dif_unidad"


def test_la_pantalla_de_cruce_lista_los_pares_que_siguen_distintos(client, usuario_admin, empresa, db):
    from tests.conftest import login

    db.session.add_all([
        ItemConteoInventario(empresa_id=empresa.id, codigo="A", cantidad_qms=1, cantidad_defontana=1,
                             unidad_qms="M", unidad_defontana="MT",
                             costo_unitario_qms=10, costo_unitario_defontana=10),
        ItemConteoInventario(empresa_id=empresa.id, codigo="B", cantidad_qms=1, cantidad_defontana=1,
                             unidad_qms="BOB", unidad_defontana="TAMBOR",
                             costo_unitario_qms=10, costo_unitario_defontana=10),
    ])
    db.session.commit()

    login(client, "admin@test.cl")
    texto = client.get("/inventario/cruce-datos").get_data(as_text=True)

    # El par equivalente no debe aparecer; el desconocido sí, para poder pedirlo.
    assert "BOB" in texto and "TAMBOR" in texto
    assert "Unidades que aún se cuentan como distintas" in texto


def test_cerrar_la_toma_no_cuenta_las_equivalentes_como_diferencia(client, usuario_admin, empresa, db):
    from tests.conftest import login
    from app.models.conteo_inventario import TomaInventario

    db.session.add_all([
        ItemConteoInventario(empresa_id=empresa.id, codigo="A", cantidad_qms=1, cantidad_defontana=1,
                             unidad_qms="RL", unidad_defontana="ROLLO"),
        ItemConteoInventario(empresa_id=empresa.id, codigo="B", cantidad_qms=1, cantidad_defontana=1,
                             unidad_qms="M", unidad_defontana="KG"),
    ])
    db.session.commit()

    login(client, "admin@test.cl")
    client.post("/inventario/toma/cerrar", follow_redirects=True)

    toma = TomaInventario.query.first()
    assert toma.dif_unidad == 1  # solo el M vs KG, no el RL vs ROLLO
