from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired


class AccionForm(FlaskForm):
    """Solo aporta el token CSRF a los formularios sin campos propios."""


class ImportarProvisionesForm(FlaskForm):
    archivo = FileField(
        "Planilla de Provisión de Ingresos",
        validators=[FileRequired("Elige el archivo Excel."), FileAllowed(["xlsx"], "Debe ser un archivo .xlsx")],
    )
