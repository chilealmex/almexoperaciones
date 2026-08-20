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


class NuevaProvisionForm(FlaskForm):
    """Una línea de Provisión de Ingresos cargada a mano, sin pasar por el Excel.

    Solo pide lo que identifica y describe la provisión. La reversa y el saldo
    no van aquí: se llenan después en la tabla, igual que en las líneas que
    llegan importando, y el saldo lo calcula la aplicación.
    """

    mes = SelectField("Mes", coerce=int, validators=[DataRequired()])
    anio = IntegerField("Año", validators=[DataRequired(), NumberRange(min=2000, max=2100)])
    cbte_prov = StringField("Cbte Prov", validators=[DataRequired(), Length(max=30)])
    ot = StringField("OT", validators=[DataRequired(), Length(max=30)])
    # Texto y no número: en pantalla el monto se escribe "$1.310.000" y un
    # IntegerField lo rechaza. La ruta lo convierte con _parse_entero.
    monto_provision = StringField("Monto Provisión", validators=[DataRequired()])
    cliente = StringField("Cliente", validators=[Optional(), Length(max=200)])
    centro_costos = StringField("Centro de Costos", validators=[Optional(), Length(max=60)])
    rut = StringField("RUT", validators=[Optional(), Length(max=20)])
    obs = StringField("Obs", validators=[Optional(), Length(max=255)])


class PeriodoDifTcForm(FlaskForm):
    anio = IntegerField("Año", validators=[DataRequired(), NumberRange(min=2000, max=2100)])
    mes = SelectField("Mes", coerce=int, validators=[DataRequired()])
    # Texto y no número: acá el decimal se escribe con coma ("925,48") y
    # FloatField rechaza esa forma. La ruta lo convierte.
    # Uno por moneda, como la tabla de la planilla.
    tipo_cambio_usd = StringField("Tipo de cambio USD", validators=[Optional(), Length(max=30)])
    tipo_cambio_eur = StringField("Tipo de cambio EUR", validators=[Optional(), Length(max=30)])
    notas = StringField("Notas", validators=[Optional(), Length(max=255)])


class ImportarMayorForm(FlaskForm):
    archivo = FileField(
        "Mayor contable (.xlsx)",
        validators=[FileRequired("Elige el archivo Excel."), FileAllowed(["xlsx"], "Debe ser un archivo .xlsx")],
    )


class ConciliacionSiiForm(FlaskForm):
    """Los cuatro archivos de un mes: el RCV del SII y los libros de Defontana.

    Los cuatro son opcionales por separado, pero cada libro necesita su par: sin
    el archivo del SII y el de Defontana no hay nada que cruzar. Es normal tener
    listo el de compras y estar esperando el de ventas, así que se permite
    cargar uno ahora y el otro después, sobre el mismo período.
    """

    anio = IntegerField("Año", validators=[DataRequired(), NumberRange(min=2000, max=2100)])
    mes = SelectField("Mes", coerce=int, validators=[DataRequired()])

    sii_compra = FileField(
        "RCV Compra (SII)",
        validators=[Optional(), FileAllowed(["csv"], "El RCV del SII se descarga en .csv")],
    )
    defontana_compra = FileField(
        "Libro de Compras (Defontana)",
        validators=[Optional(), FileAllowed(["xls", "xlsx", "html", "htm"], "El libro de Defontana se descarga en .xls")],
    )
    sii_venta = FileField(
        "RCV Venta (SII)",
        validators=[Optional(), FileAllowed(["csv"], "El RCV del SII se descarga en .csv")],
    )
    defontana_venta = FileField(
        "Libro de Ventas (Defontana)",
        validators=[Optional(), FileAllowed(["xls", "xlsx", "html", "htm"], "El libro de Defontana se descarga en .xls")],
    )
