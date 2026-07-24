from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SelectField, TextAreaField, DateField, BooleanField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Email

from app.models.contrato import ContratoCliente
from app.utils.rut import validar_rut


class ClienteForm(FlaskForm):
    rut = StringField("RUT", validators=[DataRequired(), validar_rut])
    razon_social = StringField("Razón social", validators=[DataRequired(), Length(max=150)])
    giro = StringField("Giro", validators=[Optional(), Length(max=150)])
    direccion = StringField("Dirección", validators=[Optional(), Length(max=200)])
    comuna = StringField("Comuna", validators=[Optional(), Length(max=80)])
    ciudad = StringField("Ciudad", validators=[Optional(), Length(max=80)])
    telefono = StringField("Teléfono", validators=[Optional(), Length(max=30)])
    email = StringField("Correo electrónico", validators=[Optional(), Email()])
    contacto_nombre = StringField("Nombre de contacto", validators=[Optional(), Length(max=120)])
    activo = BooleanField("Activo", default=True)


class ContratoForm(FlaskForm):
    cliente_id = SelectField("Cliente", coerce=int, validators=[DataRequired()])
    numero_contrato = StringField("N° de contrato", validators=[DataRequired(), Length(max=50)])
    objeto = StringField("Objeto del contrato", validators=[DataRequired(), Length(max=255)])
    fecha_inicio = DateField("Fecha de inicio", validators=[DataRequired()])
    fecha_termino = DateField("Fecha de término", validators=[DataRequired()])
    monto = IntegerField("Monto (CLP)", validators=[DataRequired(), NumberRange(min=0)])
    periodicidad_pago = SelectField(
        "Periodicidad de pago",
        choices=[(p, p.capitalize()) for p in ContratoCliente.PERIODICIDADES],
        validators=[DataRequired()],
    )
    dias_alerta_vencimiento = IntegerField(
        "Días de alerta antes del vencimiento", default=30, validators=[NumberRange(min=0)]
    )
    notas = TextAreaField("Notas", validators=[Optional()])
