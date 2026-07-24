from app.models.inventario import Producto
from tests.conftest import login


def _crear_producto(db, empresa, sku="SKU-1", stock_actual=10):
    producto = Producto(empresa_id=empresa.id, sku=sku, nombre="Producto de prueba", stock_actual=stock_actual)
    db.session.add(producto)
    db.session.commit()
    return producto


def test_entrada_aumenta_stock(client, db, empresa, usuario_admin):
    producto = _crear_producto(db, empresa)
    login(client, "admin@test.cl")

    client.post(
        f"/inventario/productos/{producto.id}/movimiento",
        data={"tipo": "entrada", "cantidad": 5, "tipo_documento": "", "csrf_token": "x"},
        follow_redirects=True,
    )

    db.session.refresh(producto)
    assert producto.stock_actual == 15


def test_salida_disminuye_stock(client, db, empresa, usuario_admin):
    producto = _crear_producto(db, empresa)
    login(client, "admin@test.cl")

    client.post(
        f"/inventario/productos/{producto.id}/movimiento",
        data={"tipo": "salida", "cantidad": 4, "tipo_documento": "", "csrf_token": "x"},
        follow_redirects=True,
    )

    db.session.refresh(producto)
    assert producto.stock_actual == 6


def test_salida_no_puede_dejar_stock_negativo(client, db, empresa, usuario_admin):
    producto = _crear_producto(db, empresa, stock_actual=2)
    login(client, "admin@test.cl")

    response = client.post(
        f"/inventario/productos/{producto.id}/movimiento",
        data={"tipo": "salida", "cantidad": 10, "tipo_documento": "", "csrf_token": "x"},
        follow_redirects=True,
    )

    db.session.refresh(producto)
    assert producto.stock_actual == 2
    assert "stock suficiente".encode("utf-8") in response.data


def test_usuario_sin_permiso_editar_no_puede_registrar_movimiento(client, db, empresa, usuario_bodega):
    producto = _crear_producto(db, empresa)
    login(client, "bodega@test.cl")

    response = client.get(f"/inventario/productos/{producto.id}/movimiento")
    assert response.status_code == 403
