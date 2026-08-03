from tests.conftest import login


def test_login_exitoso(client, usuario_admin):
    response = login(client, "admin@test.cl")
    assert response.status_code == 200
    assert b"Bienvenido" in response.data


def test_login_password_incorrecta(client, usuario_admin):
    response = login(client, "admin@test.cl", password="incorrecta")
    assert response.status_code == 200
    assert "Usuario/correo o contraseña incorrectos".encode("utf-8") in response.data


def test_login_con_nombre_usuario_en_vez_de_correo(client, usuario_admin):
    response = login(client, "admin_prueba")
    assert response.status_code == 200
    assert b"Bienvenido" in response.data


def test_password_hash_roundtrip(usuario_admin):
    assert usuario_admin.check_password("password123")
    assert not usuario_admin.check_password("otra-clave")


def test_ruta_protegida_redirige_a_login(client):
    response = client.get("/", follow_redirects=True)
    assert response.status_code == 200
    assert b"Iniciar sesi" in response.data


def test_login_con_next_externo_no_redirige_fuera_del_sitio(client, usuario_admin):
    """El parámetro ?next= no debe permitir un open redirect a otro dominio."""
    response = client.post(
        "/login?next=https://evil.example.com/phishing",
        data={"identificador": "admin@test.cl", "password": "password123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_login_con_next_relativo_si_se_respeta(client, usuario_admin):
    response = client.post(
        "/login?next=/inventario",
        data={"identificador": "admin@test.cl", "password": "password123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/inventario"


def test_cabeceras_de_seguridad_presentes(client):
    response = client.get("/login")
    assert "Content-Security-Policy" in response.headers
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_remember_cookie_tiene_httponly_configurado(app):
    assert app.config["REMEMBER_COOKIE_HTTPONLY"] is True
