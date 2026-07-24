from datetime import date, timedelta

from flask import render_template, send_from_directory, current_app, abort
from flask_login import login_required, current_user

from app.core import bp
from app.models.inventario import Producto
from app.models.contrato import ContratoCliente
from app.models.arriendo import ArriendoEntrada
from app.models.documento import Documento


@bp.route("/healthz")
def healthz():
    return "ok", 200


@bp.route("/")
@login_required
def dashboard():
    hoy = date.today()

    productos_bajo_stock = []
    contratos_por_vencer = []
    arriendos_entrada_por_vencer = []

    if current_user.tiene_permiso("inventario", "ver"):
        productos_bajo_stock = [
            p for p in Producto.query.filter_by(activo=True).all() if p.bajo_stock_minimo
        ]

    if current_user.tiene_permiso("contratos", "ver"):
        contratos_por_vencer = [
            c
            for c in ContratoCliente.query.filter(
                ContratoCliente.fecha_termino >= hoy,
                ContratoCliente.terminado_manualmente.is_(False),
            ).all()
            if c.estado == "por_vencer"
        ]

    if current_user.tiene_permiso("arriendos", "ver"):
        arriendos_entrada_por_vencer = [
            a
            for a in ArriendoEntrada.query.filter(
                ArriendoEntrada.fecha_termino >= hoy,
                ArriendoEntrada.terminado_manualmente.is_(False),
            ).all()
            if a.estado == "por_vencer"
        ]

    return render_template(
        "core/dashboard.html",
        productos_bajo_stock=productos_bajo_stock,
        contratos_por_vencer=contratos_por_vencer,
        arriendos_entrada_por_vencer=arriendos_entrada_por_vencer,
    )


@bp.route("/documentos/<int:documento_id>/descargar")
@login_required
def descargar_documento(documento_id):
    documento = Documento.query.get_or_404(documento_id)
    permisos_por_entidad = {
        "movimiento_inventario": "inventario",
        "contrato_cliente": "contratos",
        "activo_fijo": "activos_fijos",
        "arriendo_salida": "arriendos",
        "arriendo_entrada": "arriendos",
    }
    modulo = permisos_por_entidad.get(documento.entidad_tipo)
    if modulo is None or not current_user.tiene_permiso(modulo, "ver"):
        abort(403)

    if current_app.config["STORAGE_BACKEND"] != "local":
        abort(404)

    carpeta_base = current_app.config["UPLOAD_FOLDER"]
    return send_from_directory(
        carpeta_base, documento.ruta_archivo, as_attachment=True, download_name=documento.nombre_archivo
    )
