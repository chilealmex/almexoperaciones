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


class ContratoGeneradoForm(FlaskForm):
    cliente_id = SelectField("Cliente (Arrendatario)", coerce=int, validators=[DataRequired()])
    fecha_contrato = DateField("Fecha del contrato", validators=[DataRequired()])
    correo_arrendador = StringField("Correo de contacto del Arrendador", validators=[Optional(), Email()])

    representante_nombre = StringField("Representante legal del Arrendatario", validators=[DataRequired(), Length(max=150)])
    representante_cedula = StringField("Cédula del representante", validators=[DataRequired(), validar_rut])
    arrendatario_domicilio = StringField("Domicilio del Arrendatario", validators=[DataRequired(), Length(max=255)])
    arrendatario_correo = StringField("Correo del Arrendatario", validators=[DataRequired(), Email()])

    fiador_tipo = SelectField(
        "Tipo de fiador",
        choices=[("natural", "Persona natural"), ("empresa", "Empresa (SpA/S.A.)")],
        validators=[DataRequired()],
    )
    fiador_nombre = StringField("Nombre / Razón social del Fiador", validators=[DataRequired(), Length(max=150)])
    fiador_rut = StringField("RUT / C.I. del Fiador", validators=[DataRequired(), validar_rut])
    fiador_domicilio = StringField("Domicilio del Fiador", validators=[Optional(), Length(max=255)])
    fiador_correo = StringField("Correo del Fiador", validators=[Optional(), Email()])
    fiador_representante = StringField("Representante legal del Fiador (solo si es empresa)", validators=[Optional(), Length(max=150)])

    cotizacion_numero = StringField("N° de Cotización", validators=[DataRequired(), Length(max=30)])
    cotizacion_fecha = DateField("Fecha de la Cotización", validators=[DataRequired()])
    planta_ubicacion = StringField("Ubicación de la Planta Almex", validators=[DataRequired(), Length(max=255)])
    deducible_uf = IntegerField("Deducible de la póliza (UF por evento)", validators=[DataRequired(), NumberRange(min=0)])


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
