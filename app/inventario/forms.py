from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, IntegerField, SelectField, BooleanField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models.inventario import MovimientoInventario


class ProductoForm(FlaskForm):
    sku = StringField("SKU", validators=[DataRequired(), Length(max=50)])
    nombre = StringField("Nombre", validators=[DataRequired(), Length(max=150)])
    descripcion = TextAreaField("Descripción", validators=[Optional(), Length(max=255)])
    categoria_id = SelectField("Categoría", coerce=int, validators=[Optional()])
    unidad_medida = StringField("Unidad de medida", default="unidad", validators=[DataRequired(), Length(max=20)])
    stock_minimo = IntegerField("Stock mínimo", default=0, validators=[NumberRange(min=0)])
    precio_costo = IntegerField("Precio costo (CLP)", default=0, validators=[NumberRange(min=0)])
    precio_venta = IntegerField("Precio venta (CLP)", default=0, validators=[NumberRange(min=0)])
    activo = BooleanField("Activo", default=True)


class MovimientoForm(FlaskForm):
    tipo = SelectField("Tipo", choices=[(t, t.capitalize()) for t in MovimientoInventario.TIPOS], validators=[DataRequired()])
    cantidad = IntegerField("Cantidad", validators=[DataRequired(), NumberRange(min=0)])
    tipo_documento = SelectField(
        "Tipo de documento",
        choices=[("", "—")] + [(t, t.replace("_", " ").capitalize()) for t in MovimientoInventario.TIPOS_DOCUMENTO],
        validators=[Optional()],
    )
    numero_documento = StringField("N° de documento", validators=[Optional(), Length(max=50)])
    motivo = StringField("Motivo", validators=[Optional(), Length(max=255)])
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    archivo = FileField("Adjuntar documento", validators=[Optional(), FileAllowed(["pdf", "jpg", "jpeg", "png", "xlsx", "docx"], "Formato no permitido.")])


class ImportarCsvForm(FlaskForm):
    archivo = FileField("Archivo CSV", validators=[DataRequired(), FileAllowed(["csv"], "Debe ser un archivo .csv")])

