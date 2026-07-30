from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, StringField
from wtforms.validators import DataRequired, Email, Length, Optional

from app.utils.rut import validar_rut


class ClienteForm(FlaskForm):
    rut = StringField("RUT", validators=[DataRequired(), validar_rut])
    razon_social = StringField("Razón social", validators=[DataRequired(), Length(max=150)])
    giro = StringField("Giro", validators=[Optional(), Length(max=150)])
    direccion = StringField("Dirección", validators=[Optional(), Length(max=200)])
    comuna = StringField("Comuna", validators=[Optional(), Length(max=80)])
    ciudad = StringField("Ciudad", validators=[Optional(), Length(max=80)])
    telefono = StringField("Teléfono", validators=[Optional(), Length(max=30)])
    email = StringField("Correo electrónico", validators=[Optional(), Email()])
    contacto_nombre = StringField("Nombre de contacto", validators=[Optional(), Length(max=120)])
    activo = BooleanField("Activo", default=True)


class ProveedorForm(FlaskForm):
    rut = StringField("RUT", validators=[DataRequired(), validar_rut])
    razon_social = StringField("Razón social", validators=[DataRequired(), Length(max=150)])
    giro = StringField("Giro", validators=[Optional(), Length(max=150)])
    direccion = StringField("Dirección", validators=[Optional(), Length(max=200)])
    telefono = StringField("Teléfono", validators=[Optional(), Length(max=30)])
    email = StringField("Correo electrónico", validators=[Optional(), Email()])
    contacto_nombre = StringField("Nombre de contacto", validators=[Optional(), Length(max=120)])
    activo = BooleanField("Activo", default=True)


class ImportarExcelForm(FlaskForm):
    archivo = FileField(
        "Archivo Excel", validators=[DataRequired(), FileAllowed(["xlsx"], "Debe ser un archivo .xlsx")]
    )
