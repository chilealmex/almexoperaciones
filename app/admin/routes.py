from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user

from app.admin import bp
from app.admin.forms import UsuarioForm
from app.extensions import db
from app.models.usuario import Usuario, Rol
from app.models.permiso import MODULOS, PermisoUsuario
from app.utils.decorators import require_permission


@bp.route("/usuarios")
@require_permission("admin", "ver")
def usuarios():
    lista = Usuario.query.order_by(Usuario.nombre_completo).all()
    return render_template("admin/usuarios.html", usuarios=lista)


def _cargar_opciones_rol(form):
    query = Rol.query.order_by(Rol.nombre)
    if not current_user.es_superadmin:
        # un admin solo puede crear/editar usuarios normales, nunca otros admins/superadmins
        query = query.filter(Rol.clave == "usuario")
    form.rol_id.choices = [(r.id, r.nombre) for r in query.all()]


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
    if form.validate_on_submit():
        if not _rol_permitido_para_actor(form.rol_id.data):
            abort(403)
        if not form.password.data:
            flash("La contraseña es obligatoria para un usuario nuevo.", "danger")
            return render_template("admin/usuario_form.html", form=form, usuario=None)
        if Usuario.query.filter_by(email=form.email.data.lower().strip()).first():
            flash("Ya existe un usuario con ese correo.", "danger")
            return render_template("admin/usuario_form.html", form=form, usuario=None)

        usuario = Usuario(
            empresa_id=current_user.empresa_id,
            nombre_completo=form.nombre_completo.data.strip(),
            email=form.email.data.lower().strip(),
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

    if form.validate_on_submit():
        if not _rol_permitido_para_actor(form.rol_id.data):
            abort(403)

        email_normalizado = form.email.data.lower().strip()
        duplicado = Usuario.query.filter(
            Usuario.email == email_normalizado, Usuario.id != usuario.id
        ).first()
        if duplicado:
            flash("Ya existe otro usuario con ese correo.", "danger")
            return render_template("admin/usuario_form.html", form=form, usuario=usuario)

        usuario.nombre_completo = form.nombre_completo.data.strip()
        usuario.email = email_normalizado
        usuario.rut = form.rut.data
        usuario.rol_id = form.rol_id.data
        usuario.activo = form.activo.data
        if form.password.data:
            usuario.set_password(form.password.data)
        db.session.commit()
        flash("Usuario actualizado correctamente.", "success")
        return redirect(url_for("admin.usuarios"))

    return render_template("admin/usuario_form.html", form=form, usuario=usuario)


@bp.route("/usuarios/<int:usuario_id>/permisos", methods=["GET", "POST"])
@require_permission("admin", "editar")
def permisos_usuario(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    if not current_user.puede_gestionar_a(usuario):
        abort(403)

    if request.method == "POST":
        for modulo in MODULOS:
            puede_ver = request.form.get(f"ver_{modulo}") == "on"
            puede_editar = request.form.get(f"editar_{modulo}") == "on"
            override = PermisoUsuario.query.filter_by(
                usuario_id=usuario.id, modulo=modulo
            ).first()

            usar_rol_por_defecto = request.form.get(f"heredar_{modulo}") == "on"
            if usar_rol_por_defecto:
                if override:
                    db.session.delete(override)
                continue

            if override is None:
                override = PermisoUsuario(usuario_id=usuario.id, modulo=modulo)
                db.session.add(override)
            override.puede_ver = puede_ver
            override.puede_editar = puede_editar

        db.session.commit()
        flash("Permisos actualizados correctamente.", "success")
        return redirect(url_for("admin.permisos_usuario", usuario_id=usuario.id))

    overrides = {p.modulo: p for p in usuario.permisos_custom}
    return render_template(
        "admin/permisos.html", usuario=usuario, modulos=MODULOS, overrides=overrides
    )
