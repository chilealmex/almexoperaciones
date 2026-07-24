from tests.conftest import login


def test_login_exitoso(client, usuario_admin):
    response = login(client, "admin@test.cl")
    assert response.status_code == 200
    assert b"Bienvenido" in response.data


def test_login_password_incorrecta(client, usuario_admin):
    response = login(client, "admin@test.cl", password="incorrecta")
    assert response.status_code == 200
    assert "Correo o contraseña incorrectos".encode("utf-8") in response.data


def test_password_hash_roundtrip(usuario_admin):
    assert usuario_admin.check_password("password123")
    assert not usuario_admin.check_password("otra-clave")


def test_ruta_protegida_redirige_a_login(client):
    response = client.get("/", follow_redirects=True)
    assert response.status_code == 200
    assert b"Iniciar sesi" in response.data
