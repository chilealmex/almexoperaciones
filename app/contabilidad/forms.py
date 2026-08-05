from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import IntegerField, SelectField, StringField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class AccionForm(FlaskForm):
    """Solo aporta el token CSRF a los formularios sin campos propios."""


class ImportarProvisionesForm(FlaskForm):
    archivo = FileField(
        "Planilla de Provisión de Ingresos",
        validators=[FileRequired("Elige el archivo Excel."), FileAllowed(["xlsx"], "Debe ser un archivo .xlsx")],
    )


class PeriodoDifTcForm(FlaskForm):
    anio = IntegerField("Año", validators=[DataRequired(), NumberRange(min=2000, max=2100)])
    mes = SelectField("Mes", coerce=int, validators=[DataRequired()])
    # Texto y no número: acá el decimal se escribe con coma ("925,48") y
    # FloatField rechaza esa forma. La ruta lo convierte.
    tipo_cambio = StringField("Tipo de cambio", validators=[Optional(), Length(max=30)])
    notas = StringField("Notas", validators=[Optional(), Length(max=255)])


class ImportarMayorForm(FlaskForm):
    archivo = FileField(
        "Mayor contable (.xlsx)",
        validators=[FileRequired("Elige el archivo Excel."), FileAllowed(["xlsx"], "Debe ser un archivo .xlsx")],
    )
