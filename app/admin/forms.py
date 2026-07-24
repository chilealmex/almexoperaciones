from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField
from wtforms.validators import DataRequired, Email, Length, Optional

from app.utils.rut import validar_rut


class UsuarioForm(FlaskForm):
    nombre_completo = StringField("Nombre completo", validators=[DataRequired(), Length(max=150)])
    email = StringField("Correo electrónico", validators=[DataRequired(), Email()])
    rut = StringField("RUT", validators=[Optional(), validar_rut])
    rol_id = SelectField("Rol", coerce=int, validators=[DataRequired()])
    password = PasswordField(
        "Contraseña",
        validators=[Optional(), Length(min=8, message="Mínimo 8 caracteres.")],
    )
    activo = BooleanField("Activo", default=True)
