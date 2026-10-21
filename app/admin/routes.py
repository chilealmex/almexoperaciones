from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user

from app.admin import bp
from app.admin.forms import UsuarioForm
from app.extensions import db
from app.models.empresa import Empresa
from app.models.usuario import Usuario, Rol
from app.models.permiso import MODULOS, PermisoUsuario
from app.utils.decorators import require_permission
from app.utils.navegacion import MODULOS as NAV_MODULOS


@bp.route("/usuarios")
@require_permission("admin", "ver")
def usuarios():
    """El listado, con la empresa de cada uno a la vista.

    Todo lo que muestra el sistema —inventario, contratos, activos,
    contabilidad— está filtrado por la empresa del usuario. Dos cuentas en
    empresas distintas trabajan sobre datos distintos sin que nada lo diga:
    cada una ve una pantalla que se ve perfectamente normal. Pasó: una importó
    sus planillas y los demás siguieron viendo las de antes, y desde afuera
    parecía que el sistema no se actualizaba.

    Por eso la empresa se ve acá, y por eso se avisa arriba cuando las cuentas
    están repartidas en más de una.
    """
    lista = Usuario.query.order_by(Usuario.nombre_completo)
    # Un admin sólo administra la suya; el superadmin las ve todas, que es lo
    # que le permite darse cuenta del problema y arreglarlo.
    if not current_user.es_superadmin:
        lista = lista.filter(Usuario.empresa_id == current_user.empresa_id)
    lista = lista.all()

    empresas_con_usuarios = sorted(
        {(u.empresa_id, u.empresa.razon_social if u.empresa else "(sin empresa)") for u in lista}
    )
    return render_template(
        "admin/usuarios.html",
        usuarios=lista,
        empresas_con_usuarios=empresas_con_usuarios,
        mi_empresa_id=current_user.empresa_id,
    )


@bp.route("/empresas")
@require_permission("admin", "ver")
def empresas():
    """Qué empresas existen y qué tiene cargado cada una.

    Cuando las cuentas quedaron repartidas hay que decidir cuál es la buena, y
    eso no se puede decidir sin ver dónde están los datos. Acá se ven los dos
    lados: cuántas cuentas y cuánto trabajo cargado tiene cada empresa.
    """
    if not current_user.es_superadmin:
        abort(403)
    return render_template(
        "admin/empresas.html",
        empresas=[_resumen_de_empresa(e) for e in Empresa.query.order_by(Empresa.razon_social).all()],
        mi_empresa_id=current_user.empresa_id,
    )


def _resumen_de_empresa(empresa):
    """Cuántos usuarios y cuánto trabajo cargado tiene una empresa.

    Son los conteos que permiten reconocer cuál es la empresa de verdad: la
    que quedó por error está casi vacía, o tiene lo de hace meses.
    """
    from app.models.activo_fijo import ActivoFijo
    from app.models.contabilidad import ProvisionIngreso
    from app.models.contrato import ContratoCliente
    from app.models.conteo_inventario import ItemConteoInventario
    from app.models.importacion_inventario import ultimas_importaciones

    def cuantos(modelo):
        return db.session.query(db.func.count(modelo.id)).filter(
            modelo.empresa_id == empresa.id
        ).scalar() or 0

    cargas = ultimas_importaciones(empresa.id)
    ultima = max(
        (c.importado_en for c in cargas.values() if c and c.importado_en), default=None
    )
    return {
        "empresa": empresa,
        "usuarios": cuantos(Usuario),
        "articulos": cuantos(ItemConteoInventario),
        "contratos": cuantos(ContratoCliente),
        "activos": cuantos(ActivoFijo),
        "provisiones": cuantos(ProvisionIngreso),
        "ultima_importacion": ultima,
    }


def _cargar_opciones_rol(form):
    query = Rol.query.order_by(Rol.nombre)
    if not current_user.es_superadmin:
        # un admin solo puede crear/editar usuarios normales, nunca otros admins/superadmins
        query = query.filter(Rol.clave == "usuario")
    form.rol_id.choices = [(r.id, r.nombre) for r in query.all()]


def _cargar_opciones_empresa(form):
    """El desplegable de empresa, sólo para el superadmin.

    Cambiar la empresa de una cuenta cambia todos los datos que esa persona
    ve, así que no es una edición más y no la hace cualquier administrador.
    Sin opciones cargadas, WTForms rechaza cualquier valor que llegue en el
    POST: el campo no se puede forzar desde fuera.
    """
    if not current_user.es_superadmin:
        form.empresa_id.choices = []
        return
    form.empresa_id.choices = [
        (e.id, f"{e.razon_social} ({e.rut})")
        for e in Empresa.query.order_by(Empresa.razon_social).all()
    ]


def _empresa_elegida(form, por_defecto):
    """La empresa que pidió el formulario, o la de quien está administrando."""
    if current_user.es_superadmin and form.empresa_id.data:
        return form.empresa_id.data
    return por_defecto


def _rol_permitido_para_actor(rol_id: int) -> bool:
    if current_user.es_superadmin:
        return True
    rol = db.session.get(Rol, rol_id)
    return rol is not None and rol.clave == "usuario"


@bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@require_permission("admin", "editar")
def nuevo_usuario():
    form = UsuarioForm()
    _cargar_opciones_rol(form)
    _cargar_opciones_empresa(form)
    if form.validate_on_submit():
        if not _rol_permitido_para_actor(form.rol_id.data):
            abort(403)
        if not form.password.data:
            flash("La contraseña es obligatoria para un usuario nuevo.", "danger")
            return render_template("admin/usuario_form.html", form=form, usuario=None)

        nombre_usuario = form.nombre_usuario.data.strip().lower()
        if Usuario.query.filter_by(nombre_usuario=nombre_usuario).first():
            flash("Ya existe un usuario con ese nombre de usuario.", "danger")
            return render_template("admin/usuario_form.html", form=form, usuario=None)

        email_normalizado = form.email.data.lower().strip() if form.email.data else None
        if email_normalizado and Usuario.query.filter_by(email=email_normalizado).first():
            flash("Ya existe un usuario con ese correo.", "danger")
            return render_template("admin/usuario_form.html", form=form, usuario=None)

        usuario = Usuario(
            empresa_id=_empresa_elegida(form, current_user.empresa_id),
            nombre_completo=form.nombre_completo.data.strip(),
            nombre_usuario=nombre_usuario,
            email=email_normalizado,
            rut=form.rut.data,
            rol_id=form.rol_id.data,
            activo=form.activo.data,
        )
        usuario.set_password(form.password.data)
        db.session.add(usuario)
        db.session.commit()
        flash("Usuario creado correctamente.", "success")
        return redirect(url_for("admin.usuarios"))

    return render_template("admin/usuario_form.html", form=form, usuario=None)


@bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@require_permission("admin", "editar")
def editar_usuario(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    if not current_user.puede_gestionar_a(usuario):
        abort(403)

    form = UsuarioForm(obj=usuario)
    _cargar_opciones_rol(form)
    _cargar_opciones_empresa(form)

    if form.validate_on_submit():
        if not _rol_permitido_para_actor(form.rol_id.data):
            abort(403)

        nombre_usuario = form.nombre_usuario.data.strip().lower()
        duplicado_usuario = Usuario.query.filter(
            Usuario.nombre_usuario == nombre_usuario, Usuario.id != usuario.id
        ).first()
        if duplicado_usuario:
            flash("Ya existe otro usuario con ese nombre de usuario.", "danger")
            return render_template("admin/usuario_form.html", form=form, usuario=usuario)

        email_normalizado = form.email.data.lower().strip() if form.email.data else None
        if email_normalizado:
            duplicado_email = Usuario.query.filter(
                Usuario.email == email_normalizado, Usuario.id != usuario.id
            ).first()
            if duplicado_email:
                flash("Ya existe otro usuario con ese correo.", "danger")
                return render_template("admin/usuario_form.html", form=form, usuario=usuario)

        usuario.nombre_completo = form.nombre_completo.data.strip()
        usuario.nombre_usuario = nombre_usuario
        usuario.email = email_normalizado
        usuario.rut = form.rut.data
        usuario.rol_id = form.rol_id.data
        usuario.activo = form.activo.data
        if form.password.data:
            usuario.set_password(form.password.data)

        # El cambio de empresa se avisa aparte: no es un dato más de la ficha,
        # es con qué datos va a trabajar esa persona de ahora en adelante.
        empresa_nueva = _empresa_elegida(form, usuario.empresa_id)
        cambio_de_empresa = empresa_nueva != usuario.empresa_id
        if cambio_de_empresa:
            antes = usuario.empresa.razon_social if usuario.empresa else "(sin empresa)"
            usuario.empresa_id = empresa_nueva
        db.session.commit()
        flash("Usuario actualizado correctamente.", "success")
        if cambio_de_empresa:
            flash(
                f"{usuario.nombre_completo} pasó de {antes} a "
                f"{usuario.empresa.razon_social}: desde ahora ve el inventario, los "
                "contratos y la contabilidad de esa empresa, y deja de ver los de la "
                "anterior. Nada se borró ni se movió de lugar.",
                "warning",
            )
        return redirect(url_for("admin.usuarios"))

    return render_template("admin/usuario_form.html", form=form, usuario=usuario)


def _submodulos_por_modulo():
    """Submódulos declarados en la navegación, indexados por módulo (mismo orden que se ve en pantalla)."""
    return {m["clave"]: m["submodulos"] for m in NAV_MODULOS if m["permiso"]}


def _campo(sufijo, modulo, submodulo_clave=""):
    prefijo = f"{modulo}__{submodulo_clave}" if submodulo_clave else modulo
    return f"{sufijo}_{prefijo}"


def _guardar_override(usuario, modulo, submodulo_clave, form):
    puede_ver = form.get(_campo("ver", modulo, submodulo_clave)) == "on"
    puede_editar = form.get(_campo("editar", modulo, submodulo_clave)) == "on"
    usar_por_defecto = form.get(_campo("heredar", modulo, submodulo_clave)) == "on"

    override = PermisoUsuario.query.filter_by(
        usuario_id=usuario.id, modulo=modulo, submodulo=submodulo_clave
    ).first()

    if usar_por_defecto:
        if override:
            db.session.delete(override)
        return

    if override is None:
        override = PermisoUsuario(usuario_id=usuario.id, modulo=modulo, submodulo=submodulo_clave)
        db.session.add(override)
    override.puede_ver = puede_ver
    override.puede_editar = puede_editar


@bp.route("/usuarios/<int:usuario_id>/permisos", methods=["GET", "POST"])
@require_permission("admin", "editar")
def permisos_usuario(usuario_id):
    # Solo el superadmin define qué módulos y submódulos puede ver/editar cada
    # usuario: un admin normal ya no puede tocar esta pantalla, ni siquiera por URL directa.
    if not current_user.es_superadmin:
        abort(403)

    usuario = Usuario.query.get_or_404(usuario_id)
    if not current_user.puede_gestionar_a(usuario):
        abort(403)

    submodulos_por_modulo = _submodulos_por_modulo()

    if request.method == "POST":
        for modulo in MODULOS:
            _guardar_override(usuario, modulo, "", request.form)
            for submodulo in submodulos_por_modulo.get(modulo, ()):
                _guardar_override(usuario, modulo, submodulo["clave"], request.form)

        db.session.commit()
        flash("Permisos actualizados correctamente.", "success")
        return redirect(url_for("admin.permisos_usuario", usuario_id=usuario.id))

    overrides = {(p.modulo, p.submodulo): p for p in usuario.permisos_custom}
    return render_template(
        "admin/permisos.html",
        usuario=usuario,
        modulos=MODULOS,
        submodulos_por_modulo=submodulos_por_modulo,
        overrides=overrides,
    )
