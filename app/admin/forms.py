import re

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

from app.utils.rut import validar_rut

_USUARIO_RE = re.compile(r"^[a-z0-9._-]+$")


def validar_nombre_usuario(form, field):
    if field.data and not _USUARIO_RE.match(field.data):
        raise ValidationError("Solo minúsculas, números, puntos, guiones y guion bajo, sin espacios.")


class UsuarioForm(FlaskForm):
    nombre_completo = StringField("Nombre completo", validators=[DataRequired(), Length(max=150)])
    nombre_usuario = StringField(
        "Nombre de usuario", validators=[DataRequired(), Length(min=3, max=50), validar_nombre_usuario]
    )
    email = StringField("Correo electrónico (opcional)", validators=[Optional(), Email()])
    rut = StringField("RUT", validators=[Optional(), validar_rut])
    rol_id = SelectField("Rol", coerce=int, validators=[DataRequired()])
    password = PasswordField(
        "Contraseña",
        validators=[Optional(), Length(min=8, message="Mínimo 8 caracteres.")],
    )
    activo = BooleanField("Activo", default=True)
