from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SelectField, DateField, BooleanField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models.activo_fijo import ActivoFijo


class ActivoFijoForm(FlaskForm):
    codigo_activo = StringField("Código de activo", validators=[DataRequired(), Length(max=30)])
    nombre = StringField("Nombre", validators=[DataRequired(), Length(max=150)])
    descripcion = TextAreaField("Descripción", validators=[Optional(), Length(max=255)])
    categoria = SelectField("Categoría", validators=[Optional()])
    fecha_compra = DateField("Fecha de compra", validators=[DataRequired()])
    valor_compra = IntegerField("Valor de compra (CLP)", validators=[DataRequired(), NumberRange(min=0)])
    valor_residual = IntegerField("Valor residual (CLP)", default=0, validators=[NumberRange(min=0)])
    vida_util_meses = IntegerField("Vida útil (meses)", validators=[DataRequired(), NumberRange(min=1)])
    ubicacion = StringField("Ubicación", validators=[Optional(), Length(max=150)])
    numero_factura_compra = StringField("N° de factura de compra", validators=[Optional(), Length(max=50)])
    es_arrendable = BooleanField("Disponible para arrendar a terceros", default=False)


class BajaActivoForm(FlaskForm):
    motivo_baja = TextAreaField("Motivo de la baja", validators=[DataRequired()])
    estado = SelectField(
        "Nuevo estado",
        choices=[("dado_de_baja", "Dado de baja"), ("vendido", "Vendido")],
        validators=[DataRequired()],
    )


class CategoriaActivoForm(FlaskForm):
    nombre = StringField("Nombre de la categoría", validators=[DataRequired(), Length(max=80)])
    descripcion = StringField("Descripción", validators=[Optional(), Length(max=255)])
    activa = BooleanField("Activa", default=True)
