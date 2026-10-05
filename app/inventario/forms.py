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


class ImportarAmbosForm(FlaskForm):
    """Los dos sistemas de una vez, para actualizar el cruce sin salir de él.

    Los dos archivos son opcionales por separado, pero hay que mandar al menos
    uno: así sirve tanto para refrescar los dos lados como para volver a subir
    sólo el que se arregló.
    """

    archivo_qms = FileField(
        "Archivo QMS",
        validators=[FileAllowed(["csv", "xlsx"], "Debe ser un archivo .csv o .xlsx")],
    )
    archivo_defontana = FileField(
        "Archivo Defontana",
        validators=[FileAllowed(["csv", "xlsx"], "Debe ser un archivo .csv o .xlsx")],
    )
    # Marcado por defecto, igual que en Importar: durante una toma que dura
    # varios días es lo que se quiere casi siempre, y desmarcarlo altera
    # conteos ya hechos.
    solo_no_contados = BooleanField(
        "Actualizar solo los artículos que aún no se han contado",
        default=True,
    )

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        if not (self.archivo_qms.data or self.archivo_defontana.data):
            self.archivo_qms.errors.append(
                "Elige al menos uno de los dos archivos."
            )
            return False
        return True


class AccionForm(FlaskForm):
    """Solo aporta el token CSRF a los botones que no envían campos propios."""
