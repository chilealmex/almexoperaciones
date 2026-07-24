from datetime import date, timedelta

from app.models.cliente import Cliente
from app.models.contrato import ContratoCliente
from app.utils.rut import es_rut_valido, calcular_dv


def test_rut_valido_conocido():
    # 76.086.428-5 es un RUT de ejemplo con dígito verificador correcto (módulo 11).
    assert calcular_dv("76086428") == "5"
    assert es_rut_valido("76086428-5")
    assert es_rut_valido("76.086.428-5")


def test_rut_invalido():
    assert not es_rut_valido("76086428-9")
    assert not es_rut_valido("abc")


def _crear_cliente(db, empresa):
    cliente = Cliente(empresa_id=empresa.id, rut="76086428-5", razon_social="Cliente de prueba")
    db.session.add(cliente)
    db.session.commit()
    return cliente


def test_estado_vigente(db, empresa):
    cliente = _crear_cliente(db, empresa)
    contrato = ContratoCliente(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        numero_contrato="C-1",
        objeto="Servicio",
        fecha_inicio=date.today() - timedelta(days=10),
        fecha_termino=date.today() + timedelta(days=100),
        monto=100000,
        dias_alerta_vencimiento=30,
    )
    assert contrato.estado == "vigente"


def test_estado_por_vencer_dentro_de_la_ventana_de_alerta(db, empresa):
    cliente = _crear_cliente(db, empresa)
    contrato = ContratoCliente(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        numero_contrato="C-2",
        objeto="Servicio",
        fecha_inicio=date.today() - timedelta(days=300),
        fecha_termino=date.today() + timedelta(days=10),
        monto=100000,
        dias_alerta_vencimiento=30,
    )
    assert contrato.estado == "por_vencer"


def test_estado_vencido(db, empresa):
    cliente = _crear_cliente(db, empresa)
    contrato = ContratoCliente(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        numero_contrato="C-3",
        objeto="Servicio",
        fecha_inicio=date.today() - timedelta(days=400),
        fecha_termino=date.today() - timedelta(days=5),
        monto=100000,
        dias_alerta_vencimiento=30,
    )
    assert contrato.estado == "vencido"


def test_estado_terminado_manualmente_ignora_fechas(db, empresa):
    cliente = _crear_cliente(db, empresa)
    contrato = ContratoCliente(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        numero_contrato="C-4",
        objeto="Servicio",
        fecha_inicio=date.today() - timedelta(days=10),
        fecha_termino=date.today() + timedelta(days=100),
        monto=100000,
        terminado_manualmente=True,
    )
    assert contrato.estado == "terminado"
