from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms.validators import DataRequired


class ImportarCsvForm(FlaskForm):
    archivo = FileField(
        "Archivo CSV o Excel",
        validators=[DataRequired(), FileAllowed(["csv", "xlsx"], "Debe ser un archivo .csv o .xlsx")],
    )
