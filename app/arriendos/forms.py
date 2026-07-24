from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SelectField, DateField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Email

from app.models.arriendo import ArriendoSalida, ArriendoEntrada
from app.utils.rut import validar_rut


class ArriendoSalidaForm(FlaskForm):
    activo_fijo_id = SelectField("Activo", coerce=int, validators=[DataRequired()])
    cliente_id = SelectField("Cliente", coerce=int, validators=[DataRequired()])
    fecha_inicio = DateField("Fecha de inicio", validators=[DataRequired()])
    fecha_termino_prevista = DateField("Fecha de término prevista", validators=[DataRequired()])
    monto_periodo = IntegerField("Monto por período (CLP)", validators=[DataRequired(), NumberRange(min=0)])
    periodicidad = SelectField(
        "Periodicidad",
        choices=[(p, p.capitalize()) for p in ArriendoSalida.PERIODICIDADES],
        validators=[DataRequired()],
    )
    condiciones = TextAreaField("Condiciones", validators=[Optional()])


class ProveedorForm(FlaskForm):
    rut = StringField("RUT", validators=[DataRequired(), validar_rut])
    razon_social = StringField("Razón social", validators=[DataRequired(), Length(max=150)])
    giro = StringField("Giro", validators=[Optional(), Length(max=150)])
    direccion = StringField("Dirección", validators=[Optional(), Length(max=200)])
    telefono = StringField("Teléfono", validators=[Optional(), Length(max=30)])
    email = StringField("Correo electrónico", validators=[Optional(), Email()])
    contacto_nombre = StringField("Nombre de contacto", validators=[Optional(), Length(max=120)])


class ArriendoEntradaForm(FlaskForm):
    proveedor_id = SelectField("Proveedor", coerce=int, validators=[DataRequired()])
    descripcion_activo = StringField("Descripción del activo arrendado", validators=[DataRequired(), Length(max=255)])
    numero_contrato = StringField("N° de contrato", validators=[Optional(), Length(max=50)])
    fecha_inicio = DateField("Fecha de inicio", validators=[DataRequired()])
    fecha_termino = DateField("Fecha de término", validators=[DataRequired()])
    monto_periodo = IntegerField("Monto por período (CLP)", validators=[DataRequired(), NumberRange(min=0)])
    periodicidad = SelectField(
        "Periodicidad",
        choices=[(p, p.capitalize()) for p in ArriendoEntrada.PERIODICIDADES],
        validators=[DataRequired()],
    )
    dias_alerta_vencimiento = IntegerField("Días de alerta antes del vencimiento", default=30, validators=[NumberRange(min=0)])
    ubicacion_uso = StringField("Ubicación de uso", validators=[Optional(), Length(max=150)])


class DevolucionForm(FlaskForm):
    fecha_devolucion_real = DateField("Fecha de devolución", validators=[DataRequired()])


class FirmaClienteForm(FlaskForm):
    firma_cliente_nombre = StringField("Nombre de quien firma", validators=[DataRequired(), Length(max=150)])
    firma_imagen = StringField("Firma", validators=[DataRequired()])


class PagoForm(FlaskForm):
    periodo = StringField("Período (AAAA-MM)", validators=[DataRequired(), Length(max=7)])
    monto = IntegerField("Monto (CLP)", validators=[DataRequired(), NumberRange(min=0)])
    numero_documento = StringField("N° de documento", validators=[Optional(), Length(max=50)])
