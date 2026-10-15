"""Dejar el sistema en el escritorio del celular.

No es una aplicación aparte: es el mismo sitio, declarado de forma que Android
e iOS lo instalen con su ícono y lo abran a pantalla completa, sin la barra del
navegador. Mismo código, mismo login, nada que mantener dos veces.

Lo que Android pide para ofrecer "Instalar aplicación": un manifiesto con
nombre, ícono de 192 y de 512, una dirección de inicio, display "standalone", y
un service worker registrado con un manejador de 'fetch'.
"""

import json

import re

from tests.conftest import login


def _sin_comentarios(codigo: str) -> str:
    """El código del archivo, sin sus comentarios.

    Importa: este archivo explica en palabras por qué no guarda nada, y esas
    palabras nombran justo lo que no debe hacer. Buscándolas en el texto
    completo, la prueba fallaba por el comentario que la respalda.
    """
    sin_bloques = re.sub(r"/\*.*?\*/", "", codigo, flags=re.S)
    return "\n".join(l for l in sin_bloques.splitlines() if not l.strip().startswith("//"))


def test_la_pagina_declara_el_manifiesto(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    html = client.get("/inventario/stock").get_data(as_text=True)

    assert 'rel="manifest"' in html
    assert "manifest.webmanifest" in html


def test_el_manifiesto_se_sirve_con_su_tipo(client):
    """Servido como texto plano, el navegador lo ignora y no ofrece instalar."""
    respuesta = client.get("/static/manifest.webmanifest")

    assert respuesta.status_code == 200
    assert "manifest" in respuesta.headers["Content-Type"]


def test_el_manifiesto_tiene_lo_que_android_exige(client):
    datos = json.loads(client.get("/static/manifest.webmanifest").get_data(as_text=True))

    assert datos["name"] and datos["short_name"]
    assert datos["start_url"] == "/"
    # Sin "standalone" se abre como una pestaña más, con la barra del navegador:
    # se vería igual que tener un acceso directo.
    assert datos["display"] == "standalone"
    # Los normales, y se mira el propósito además del tamaño: el "maskable"
    # también es de 512 y no sirve para lo mismo —Android usa el normal para la
    # pantalla de arranque—, así que contarlo dejaría pasar un manifiesto sin
    # ícono grande de verdad.
    normales = {i["sizes"] for i in datos["icons"] if i.get("purpose", "any") == "any"}
    assert "192x192" in normales and "512x512" in normales


def test_hay_un_icono_para_el_recorte_de_android(client):
    """Android recorta el ícono en círculo o en cuadrado redondeado según el
    teléfono. Sin uno declarado "maskable" le come las puntas al logo."""
    datos = json.loads(client.get("/static/manifest.webmanifest").get_data(as_text=True))

    assert any("maskable" in i.get("purpose", "") for i in datos["icons"])


def test_los_iconos_existen_de_verdad(client):
    """Un manifiesto que apunta a un archivo que no está no instala nada, y el
    navegador no avisa: simplemente no ofrece el botón."""
    datos = json.loads(client.get("/static/manifest.webmanifest").get_data(as_text=True))

    for icono in datos["icons"]:
        respuesta = client.get(icono["src"])
        assert respuesta.status_code == 200, icono["src"]
        assert respuesta.headers["Content-Type"] == "image/png", icono["src"]


def test_ios_tiene_su_propio_icono(client, db, empresa, usuario_admin):
    """iOS no lee el manifiesto para esto: busca el apple-touch-icon, y sin él
    pone una foto de la pantalla como ícono."""
    login(client, "admin@test.cl")

    html = client.get("/inventario/stock").get_data(as_text=True)

    assert 'rel="apple-touch-icon"' in html
    assert client.get("/static/img/apple-touch-icon.png").status_code == 200


def test_el_service_worker_se_sirve_desde_la_raiz(client):
    """Un service worker sólo manda sobre las direcciones que cuelgan de la
    suya: servido en /static/js/ no vería el resto del sitio y Android no
    ofrecería instalar."""
    respuesta = client.get("/sw.js")

    assert respuesta.status_code == 200
    assert "javascript" in respuesta.headers["Content-Type"]


def test_el_service_worker_no_guarda_nada(client):
    """Es la decisión que más importa acá. Un service worker contesta desde su
    copia aunque el servidor diga "no-store", y sigue haciéndolo después de
    cerrar sesión: guardar páginas sería volver al problema recién arreglado, y
    de peor manera."""
    cuerpo = _sin_comentarios(client.get("/sw.js").get_data(as_text=True))

    # Sin respondWith, el service worker no puede contestar: la petición sigue
    # al servidor por fuerza.
    assert "respondWith" not in cuerpo
    assert "cache.put" not in cuerpo and "cache.addAll" not in cuerpo
    # Y limpia lo que haya quedado de una versión anterior.
    assert "caches.delete" in cuerpo


def test_el_service_worker_atiende_fetch(client):
    """Sin un manejador de 'fetch', Android no considera instalable el sitio,
    aunque el manifiesto esté perfecto."""
    cuerpo = client.get("/sw.js").get_data(as_text=True)

    assert "addEventListener('fetch'" in cuerpo


def test_el_service_worker_no_queda_cacheado(client):
    """Si se corrige algo acá, tiene que llegar al celular en la siguiente
    visita y no cuando al navegador le parezca."""
    assert client.get("/sw.js").headers["Cache-Control"] == "no-store"


def test_la_pagina_lo_registra(client, db, empresa, usuario_admin):
    login(client, "admin@test.cl")

    html = client.get("/inventario/stock").get_data(as_text=True)

    assert "serviceWorker" in html
    assert "/sw.js" in html


def test_se_puede_entrar_sin_haber_iniciado_sesion(client):
    """La dirección de inicio del manifiesto es "/". Al abrir la aplicación sin
    sesión tiene que llevar a entrar, no a un error: es lo primero que ve quien
    la acaba de instalar."""
    respuesta = client.get("/", follow_redirects=True)

    assert respuesta.status_code == 200
    assert "contrase" in respuesta.get_data(as_text=True).lower()
