"""Cuándo se importó cada planilla, visible en todo Inventario.

Mirando una tabla de stock no hay forma de saber si el número viene del archivo
de hoy o del de la semana pasada: se ve igual de convincente en los dos casos.
El mensaje verde de la importación desaparece al cambiar de pantalla.
"""

import io

import pytest
from werkzeug.datastructures import FileStorage

from app.models.importacion_inventario import ImportacionInventario, ultimas_importaciones
from tests.conftest import login

CSV_QMS = (
    "Código Único;Descripción;Stock;Linea Negocio;Categoria;Unidad;Costo Unitario\r\n"
    "COD-001;Tornillo;10;FUSION;INSUMOS;UN;1500\r\n"
    "COD-002;Perno;5;FUSION;INSUMOS;UN;900\r\n"
)

CSV_DEFONTANA = (
    "CodArticulo;Descripción;CodBodega;Nombre Bodega;Saldo Stock\r\n"
    "COD-001;Tornillo;01;Casa Matriz;12\r\n"
)

# Todas las pantallas del módulo: la pregunta es la misma en cada una.
PANTALLAS = [
    "/inventario/", "/inventario/stock", "/inventario/ajuste",
    "/inventario/cruce-datos", "/inventario/regularizacion",
    "/inventario/historial", "/inventario/conteo/importar",
]


def _subir(client, ruta, prefijo, texto, nombre):
    return client.post(
        ruta,
        data={f"{prefijo}-archivo": FileStorage(
            stream=io.BytesIO(texto.encode("utf-8")), filename=nombre)},
        content_type="multipart/form-data", follow_redirects=True,
    )


def _subir_qms(client, nombre="stock-qms-30-09.csv"):
    return _subir(client, "/inventario/conteo/importar/qms", "qms", CSV_QMS, nombre)


def _subir_defontana(client, nombre="informe-defontana.csv"):
    return _subir(client, "/inventario/conteo/importar/defontana", "def", CSV_DEFONTANA, nombre)


# --- Lo que se guarda ---


def test_importar_deja_constancia_de_que_archivo_se_subio(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    _subir_qms(client)

    registro = ImportacionInventario.query.filter_by(sistema="qms").one()
    assert registro.archivo == "stock-qms-30-09.csv"
    assert registro.importado_por_id == usuario_admin.id
    assert registro.importado_en is not None
    # El recuento es el mismo que muestra el mensaje de la importación
    assert registro.total_codigos == 2
    assert registro.creados == 2


def test_cada_sistema_lleva_su_propio_rastro(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    _subir_qms(client)
    _subir_defontana(client)

    ultimas = ultimas_importaciones(empresa.id)
    assert ultimas["qms"].archivo == "stock-qms-30-09.csv"
    assert ultimas["defontana"].archivo == "informe-defontana.csv"


def test_volver_a_subir_reemplaza_en_vez_de_acumular(client, db, empresa, usuario_admin):
    """La pregunta es "¿esto está al día?", no "¿cuántas veces se subió?"."""
    login(client, "admin@test.cl")

    _subir_qms(client, "viejo.csv")
    _subir_qms(client, "nuevo.csv")

    registro = ImportacionInventario.query.filter_by(sistema="qms").one()
    assert registro.archivo == "nuevo.csv"


def test_sin_importar_nada_no_hay_rastro(db, empresa):
    assert ultimas_importaciones(empresa.id) == {"qms": None, "defontana": None}


def test_una_importacion_fallida_no_deja_dicho_que_ocurrio(client, db, empresa, usuario_admin):
    """Si el archivo no sirve, no puede quedar escrito que se importó."""
    login(client, "admin@test.cl")

    _subir(client, "/inventario/conteo/importar/qms", "qms",
           "columna;que;no;corresponde\r\n1;2;3;4\r\n", "malo.csv")

    assert ImportacionInventario.query.count() == 0


# --- Lo que se ve ---


@pytest.mark.parametrize("ruta", PANTALLAS)
def test_la_fecha_se_ve_en_toda_pantalla_del_modulo(client, db, empresa, usuario_admin, ruta):
    login(client, "admin@test.cl")
    _subir_qms(client)

    cuerpo = client.get(ruta).get_data(as_text=True)

    assert "stock-qms-30-09.csv" in cuerpo, f"no aparece en {ruta}"


@pytest.mark.parametrize("ruta", PANTALLAS)
def test_lo_que_nunca_se_importo_tambien_se_dice(client, db, empresa, usuario_admin, ruta):
    """Callarlo se lee como "está al día", que es justo lo contrario."""
    login(client, "admin@test.cl")
    _subir_qms(client)

    cuerpo = client.get(ruta).get_data(as_text=True)

    assert "nunca se ha importado" in cuerpo, f"no lo dice en {ruta}"


def test_se_muestra_quien_lo_subio_y_cuantos_codigos(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")
    _subir_qms(client)

    cuerpo = client.get("/inventario/stock").get_data(as_text=True)

    assert "Admin de Prueba" in cuerpo
    assert "2 códigos" in cuerpo


def test_guardar_un_conteo_no_paga_la_consulta(client, db, empresa, usuario_admin):
    """El rastro se arma sólo al dibujar una plantilla: el endpoint que guarda
    el conteo devuelve JSON y se llama una vez por artículo contado."""
    import json

    from app.models.conteo_inventario import ItemConteoInventario

    login(client, "admin@test.cl")
    item = ItemConteoInventario(empresa_id=empresa.id, codigo="X", nombre="X",
                                cantidad_qms=1, cantidad_defontana=1)
    db.session.add(item)
    db.session.commit()

    from unittest.mock import patch

    with patch("app.inventario.routes.ultimas_importaciones",
               side_effect=AssertionError("no debe consultarse")):
        respuesta = client.post(f"/inventario/stock/{item.id}/contar",
                                data=json.dumps({"cantidad": "1"}),
                                content_type="application/json")

    assert respuesta.status_code == 200
