"""Los avisos de la aplicación (mensajes flash).

Confirmar o avisar un error no sirve si el mensaje desaparece antes de que la
persona lo lea. Importar una planilla grande tarda cerca de un minuto: durante
esa espera es normal mirar otra cosa, y al volver el aviso ya no estaba.
"""

import io
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
JS = (RAIZ / "app" / "static" / "js" / "main.js").read_text(encoding="utf-8")


def test_los_avisos_no_se_cierran_solos():
    """No debe quedar ningún temporizador que oculte los avisos."""
    assert "classList.remove(\"show\")" not in JS, (
        "hay código que oculta los avisos solo; con una importación larga, "
        "el resultado desaparece antes de que alcancen a leerlo"
    )


def test_el_aviso_se_puede_cerrar_a_mano():
    plantilla = (RAIZ / "app" / "templates" / "partials" / "_flash.html").read_text(encoding="utf-8")
    assert 'data-bs-dismiss="alert"' in plantilla


def test_al_importar_bien_queda_un_aviso_con_el_resultado(client, usuario_admin, empresa, db):
    from tests.conftest import login

    login(client, "admin@test.cl")
    planilla = (
        "﻿Sucursal;Linea Negocio;Categoria;Stock;Descripción;Unidad;Código Único;ubicacion_bodega\n"
        "Casa Matriz;GOMAS;CAT;10;ARTICULO;UN;COD-001;RACK A\n"
    ).encode("utf-8")

    respuesta = client.post(
        "/inventario/conteo/importar/qms",
        data={"qms-archivo": (io.BytesIO(planilla), "qms.csv")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)
    assert "QMS importado" in texto
    assert "1 códigos" in texto or "1 código" in texto


def test_si_la_planilla_no_sirve_el_aviso_lo_dice(client, usuario_admin, empresa, db):
    """Un archivo sin las columnas esperadas tiene que avisar, no quedar en silencio."""
    from tests.conftest import login

    login(client, "admin@test.cl")
    respuesta = client.post(
        "/inventario/conteo/importar/qms",
        data={"qms-archivo": (io.BytesIO(b"columna1;columna2\n1;2\n"), "qms.csv")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)
    assert "alert-danger" in texto
    assert "No se encontraron las columnas" in texto


def test_si_no_se_elige_archivo_tambien_avisa(client, usuario_admin, empresa, db):
    from tests.conftest import login

    login(client, "admin@test.cl")
    respuesta = client.post(
        "/inventario/conteo/importar/qms", data={},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert "alert-danger" in respuesta.get_data(as_text=True)
