from datetime import date, timedelta

from app.models.activo_fijo import ActivoFijo
from app.models.cliente import Cliente
from app.models.arriendo import ArriendoSalida
from tests.conftest import login


def _crear_activo_arrendable(db, empresa):
    activo = ActivoFijo(
        empresa_id=empresa.id,
        codigo_activo="AF-ARR-1",
        nombre="Grúa horquilla",
        fecha_compra=date.today() - timedelta(days=100),
        valor_compra=5_000_000,
        vida_util_meses=60,
        es_arrendable=True,
    )
    db.session.add(activo)
    db.session.commit()
    return activo


def _crear_cliente(db, empresa):
    cliente = Cliente(empresa_id=empresa.id, rut="76086428-5", razon_social="Cliente arrendatario")
    db.session.add(cliente)
    db.session.commit()
    return cliente


def test_no_se_puede_arrendar_dos_veces_el_mismo_activo(client, db, empresa, usuario_admin):
    activo = _crear_activo_arrendable(db, empresa)
    cliente = _crear_cliente(db, empresa)

    primero = ArriendoSalida(
        empresa_id=empresa.id,
        activo_fijo_id=activo.id,
        cliente_id=cliente.id,
        fecha_inicio=date.today(),
        fecha_termino_prevista=date.today() + timedelta(days=30),
        monto_periodo=100_000,
    )
    db.session.add(primero)
    db.session.commit()

    assert activo.arrendado_actualmente is True

    login(client, "admin@test.cl")
    response = client.post(
        "/arriendos/salida/nuevo",
        data={
            "activo_fijo_id": activo.id,
            "cliente_id": cliente.id,
            "fecha_inicio": date.today().isoformat(),
            "fecha_termino_prevista": (date.today() + timedelta(days=30)).isoformat(),
            "monto_periodo": 100_000,
            "periodicidad": "mensual",
            "csrf_token": "x",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "ya está arrendado".encode("utf-8") in response.data
    assert ArriendoSalida.query.count() == 1


def test_devolucion_libera_el_activo_para_nuevo_arriendo(db, empresa):
    activo = _crear_activo_arrendable(db, empresa)
    cliente = _crear_cliente(db, empresa)

    arriendo = ArriendoSalida(
        empresa_id=empresa.id,
        activo_fijo_id=activo.id,
        cliente_id=cliente.id,
        fecha_inicio=date.today() - timedelta(days=30),
        fecha_termino_prevista=date.today(),
        monto_periodo=100_000,
    )
    db.session.add(arriendo)
    db.session.commit()
    assert activo.arrendado_actualmente is True

    arriendo.fecha_devolucion_real = date.today()
    db.session.commit()

    assert activo.arrendado_actualmente is False
