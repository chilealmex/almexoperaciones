from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo


class LoginForm(FlaskForm):
    email = StringField("Correo electrónico", validators=[DataRequired(), Email()])
    password = PasswordField("Contraseña", validators=[DataRequired()])
    recordarme = BooleanField("Recordarme")


class CambiarPasswordForm(FlaskForm):
    password_actual = PasswordField("Contraseña actual", validators=[DataRequired()])
    password_nueva = PasswordField(
        "Contraseña nueva", validators=[DataRequired(), Length(min=8, message="Mínimo 8 caracteres.")]
    )
    password_nueva_confirmar = PasswordField(
        "Confirmar contraseña nueva",
        validators=[DataRequired(), EqualTo("password_nueva", message="Las contraseñas no coinciden.")],
    )
