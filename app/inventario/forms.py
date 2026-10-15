from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import BooleanField, DateField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from app.models.oti import OrdenTrabajoInterna


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


class ImportarConteoForm(FlaskForm):
    """El conteo físico subido de a muchos, en vez de fila por fila.

    Sin la casilla de "solo no contados" de los otros importadores: acá el
    archivo ES el conteo, así que si trae una cantidad es porque se contó y
    manda sobre lo que hubiera.
    """

    archivo = FileField(
        "Archivo CSV o Excel con el conteo",
        validators=[DataRequired(), FileAllowed(["csv", "xlsx"], "Debe ser un archivo .csv o .xlsx")],
    )


class CruceDePruebaForm(FlaskForm):
    """Las dos planillas que se comparan sin cargarlas al sistema.

    Los dos archivos son obligatorios: un cruce necesita los dos lados. Con uno
    solo, todo lo del otro sistema aparecería como "falta", que no es un cruce
    sino un listado mal leído.
    """

    archivo_qms = FileField(
        "Archivo QMS",
        validators=[
            DataRequired("Falta el archivo de QMS: un cruce necesita los dos lados."),
            FileAllowed(["csv", "xlsx"], "Debe ser un archivo .csv o .xlsx"),
        ],
    )
    archivo_defontana = FileField(
        "Archivo Defontana",
        validators=[
            DataRequired("Falta el archivo de Defontana: un cruce necesita los dos lados."),
            FileAllowed(["csv", "xlsx"], "Debe ser un archivo .csv o .xlsx"),
        ],
    )


class AccionForm(FlaskForm):
    """Solo aporta el token CSRF a los botones que no envían campos propios."""


class OTIForm(FlaskForm):
    """La cabecera de una OT interna.

    El número no está acá: lo pone el sistema. La numeración de la planilla va
    del 100 al 822 sin un solo salto, y esa continuidad es lo que permite
    nombrar una orden por su número sin ambigüedad. Dejarlo escribir a mano
    abriría la puerta a repetirlo o saltárselo sin querer.

    Los ítems tampoco: son una lista de largo variable y se leen del formulario
    aparte, en la ruta.
    """

    fecha = DateField("Fecha", validators=[DataRequired()])
    estado = SelectField("Estado", validators=[DataRequired()])
    customer = StringField("Solicita", validators=[Optional(), Length(max=120)])
    cliente = StringField("Cliente final", validators=[Optional(), Length(max=120)])
    linea_negocio = StringField("Línea de negocio", validators=[Optional(), Length(max=40)])
    ot_qms = StringField("N° OT en QMS", validators=[Optional(), Length(max=30)])
    fecha_inicio = DateField("Fecha de inicio", validators=[Optional()])
    fecha_termino = DateField("Fecha real de término", validators=[Optional()])
    observaciones = TextAreaField("Observaciones", validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # "SIN ESTADO" no se ofrece: lo pone sólo la carga del historial, para
        # las órdenes viejas cuya planilla no registraba el estado. Elegirlo a
        # mano sería crear a propósito una orden sin decir en qué va.
        self.estado.choices = [(e, e.capitalize()) for e in OrdenTrabajoInterna.ESTADOS]


class ImportarOTIForm(FlaskForm):
    """El registro histórico de OT internas, que vivía en una planilla."""

    archivo = FileField(
        "Planilla de OT internas",
        validators=[DataRequired(), FileAllowed(["xlsx"], "Debe ser un archivo .xlsx")],
    )
