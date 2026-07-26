from datetime import date

from app.models.cliente import Cliente
from app.models.contrato_generado import ContratoGenerado
from tests.conftest import login


def _crear_cliente(db, empresa):
    cliente = Cliente(
        empresa_id=empresa.id,
        rut="76086428-5",
        razon_social="Minera Prueba SpA",
        direccion="Av. Falsa 123",
    )
    db.session.add(cliente)
    db.session.commit()
    return cliente


def _datos_formulario(cliente):
    return {
        "cliente_id": cliente.id,
        "fecha_contrato": date.today().isoformat(),
        "correo_arrendador": "contacto@shawalmex.cl",
        "representante_nombre": "Juana Pérez Soto",
        "representante_cedula": "76086428-5",
        "arrendatario_domicilio": "Camino Minero 456, Antofagasta",
        "arrendatario_correo": "gerencia@mineraprueba.cl",
        "fiador_tipo": "natural",
        "fiador_nombre": "Pedro Fiador Rojas",
        "fiador_rut": "76086428-5",
        "fiador_domicilio": "Calle Fiadores 789",
        "fiador_correo": "pedro@fiador.cl",
        "fiador_representante": "",
        "cotizacion_numero": "COT-2026-15",
        "cotizacion_fecha": date.today().isoformat(),
        "planta_ubicacion": "Av. Industrial 1000, Santiago",
        "deducible_uf": 50,
        "csrf_token": "x",
    }


def test_generar_contrato_y_ver_documento(client, db, empresa, usuario_admin):
    cliente = _crear_cliente(db, empresa)
    login(client, "admin@test.cl")

    r = client.post("/contratos/generados/nuevo", data=_datos_formulario(cliente), follow_redirects=True)
    assert r.status_code == 200

    contrato = ContratoGenerado.query.first()
    assert contrato is not None
    assert contrato.cotizacion_numero == "COT-2026-15"

    r = client.get(f"/contratos/generados/{contrato.id}")
    body = r.get_data(as_text=True)
    # los datos variables deben aparecer interpolados en el documento
    assert "Minera Prueba SpA" in body
    assert "76086428-5" in body
    assert "Juana Pérez Soto" in body
    assert "Pedro Fiador Rojas" in body
    assert "COT-2026-15" in body
    assert "Av. Industrial 1000, Santiago" in body
    assert "50 UF" in body
    # y el texto fijo de la plantilla también
    assert "SHAW ALMEX CHILE SpA" in body
    assert "FIANZA Y CODEUDA SOLIDARIA" in body


def test_fiador_empresa_requiere_representante(client, db, empresa, usuario_admin):
    cliente = _crear_cliente(db, empresa)
    login(client, "admin@test.cl")

    datos = _datos_formulario(cliente)
    datos["fiador_tipo"] = "empresa"
    datos["fiador_representante"] = ""
    r = client.post("/contratos/generados/nuevo", data=datos, follow_redirects=True)
    assert "debes indicar su representante legal" in r.get_data(as_text=True)
    assert ContratoGenerado.query.count() == 0


def test_usuario_sin_permiso_no_genera_contratos(client, db, empresa, usuario_bodega):
    login(client, "bodega@test.cl")
    r = client.get("/contratos/generados")
    assert r.status_code == 403
