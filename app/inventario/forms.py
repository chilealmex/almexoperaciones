from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import BooleanField
from wtforms.validators import DataRequired


class ImportarCsvForm(FlaskForm):
    archivo = FileField(
        "Archivo CSV o Excel",
        validators=[DataRequired(), FileAllowed(["csv", "xlsx"], "Debe ser un archivo .csv o .xlsx")],
    )
    # Marcado por defecto: durante una toma que dura varios días es lo que se
    # quiere casi siempre, y desmarcarlo altera conteos ya hechos.
    solo_no_contados = BooleanField(
        "Actualizar solo los artículos que aún no se han contado",
        default=True,
    )


class AccionForm(FlaskForm):
    """Solo aporta el token CSRF a los botones que no envían campos propios."""
