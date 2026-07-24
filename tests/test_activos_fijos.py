from datetime import date

from app.models.activo_fijo import ActivoFijo


def _restar_meses(fecha, meses):
    total_meses = fecha.month - 1 - meses
    anio = fecha.year + total_meses // 12
    mes = total_meses % 12 + 1
    return date(anio, mes, min(fecha.day, 28))


def _crear_activo(db, empresa, meses_atras, vida_util_meses=36, valor_compra=1_200_000, valor_residual=0):
    activo = ActivoFijo(
        empresa_id=empresa.id,
        codigo_activo=f"AF-{meses_atras}",
        nombre="Activo de prueba",
        fecha_compra=_restar_meses(date.today(), meses_atras),
        valor_compra=valor_compra,
        valor_residual=valor_residual,
        vida_util_meses=vida_util_meses,
    )
    db.session.add(activo)
    db.session.commit()
    return activo


def test_valor_libro_al_momento_de_la_compra(db, empresa):
    activo = _crear_activo(db, empresa, meses_atras=0)
    assert activo.valor_libro == activo.valor_compra


def test_valor_libro_a_mitad_de_vida_util(db, empresa):
    activo = _crear_activo(db, empresa, meses_atras=18, vida_util_meses=36, valor_compra=1_200_000)
    # A mitad de la vida útil, con valor residual 0, el valor libro debería ser ~600.000
    assert abs(activo.valor_libro - 600_000) <= 1_200_000 / 36  # tolerancia de un mes


def test_valor_libro_no_baja_del_valor_residual(db, empresa):
    activo = _crear_activo(db, empresa, meses_atras=60, vida_util_meses=36, valor_compra=1_200_000, valor_residual=100_000)
    assert activo.valor_libro == 100_000


def test_dar_de_baja_actualiza_estado(db, empresa):
    activo = _crear_activo(db, empresa, meses_atras=5)
    activo.estado = "dado_de_baja"
    activo.motivo_baja = "Equipo obsoleto"
    activo.fecha_baja = date.today()
    db.session.commit()

    db.session.refresh(activo)
    assert activo.estado == "dado_de_baja"
    assert activo.fecha_baja == date.today()


def test_depreciacion_mensual_lineal(db, empresa):
    activo = _crear_activo(db, empresa, meses_atras=5, vida_util_meses=36, valor_compra=1_080_000, valor_residual=0)
    assert activo.depreciacion_mensual == 30_000


def test_depreciacion_mensual_cero_si_ya_termino_vida_util(db, empresa):
    activo = _crear_activo(db, empresa, meses_atras=50, vida_util_meses=36, valor_compra=1_080_000)
    assert activo.depreciacion_mensual == 0


def test_centro_costo_administracion_por_defecto(db, empresa):
    activo = _crear_activo(db, empresa, meses_atras=5)
    assert activo.centro_costo == "Administración"


def test_centro_costo_arriendo_cuando_esta_arrendado(db, empresa):
    from app.models.arriendo import ArriendoSalida
    from app.models.cliente import Cliente
    from datetime import timedelta

    activo = _crear_activo(db, empresa, meses_atras=5)
    cliente = Cliente(empresa_id=empresa.id, rut="76086428-5", razon_social="Cliente Depreciación")
    db.session.add(cliente)
    db.session.commit()

    arriendo = ArriendoSalida(
        empresa_id=empresa.id,
        activo_fijo_id=activo.id,
        cliente_id=cliente.id,
        fecha_inicio=date.today() - timedelta(days=10),
        fecha_termino_prevista=date.today() + timedelta(days=20),
        monto_periodo=100_000,
    )
    db.session.add(arriendo)
    db.session.commit()

    assert activo.centro_costo == "Arriendo"
