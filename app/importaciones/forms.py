from flask_wtf import FlaskForm
from wtforms import DateField, FloatField, IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

TRATADO_CHOICES = [("SI", "Sí"), ("NO", "No"), ("PARCIAL", "Parcial")]


class ImportacionForm(FlaskForm):
    fecha_pei = DateField("Fecha PEI", validators=[Optional()])
    pei = StringField("N° PEI", validators=[Optional(), Length(max=30)])
    imp = StringField("N° IMP", validators=[Optional(), Length(max=30)])
    proveedor_nombre = StringField("Proveedor", validators=[Optional(), Length(max=150)])
    oc = StringField("N° OC", validators=[Optional(), Length(max=30)])
    monto = IntegerField("Monto guía (CLP)", validators=[Optional(), NumberRange(min=0)], default=0)
    agencia = StringField("Agencia", validators=[Optional(), Length(max=100)])
    tipo_saldo = SelectField(
        "Tipo de saldo", choices=[("a_favor", "A favor"), ("en_contra", "En contra")], default="a_favor"
    )
    saldo_agencia = IntegerField("Monto saldo agencia (CLP)", validators=[Optional(), NumberRange(min=0)], default=0)
    pais = StringField("País", validators=[Optional(), Length(max=80)])
    tratado_tlc = SelectField("Tratado libre comercio", choices=TRATADO_CHOICES, validators=[Optional()])
    estado = SelectField(
        "Estado",
        choices=[("pendiente", "Pendiente"), ("costeando", "Costeando"), ("cerrado", "Cerrado")],
        default="pendiente",
    )
    notas = TextAreaField("Notas", validators=[Optional(), Length(max=2000)])


class ProveedorImportacionForm(FlaskForm):
    rut = StringField("RUT / Aux", validators=[Optional(), Length(max=20)])
    nombre = StringField("Nombre", validators=[DataRequired(), Length(max=150)])
    pais = StringField("País", validators=[Optional(), Length(max=80)])
    tratado_tlc = SelectField("Tratado libre comercio", choices=TRATADO_CHOICES, validators=[Optional()])


class DinRegistroForm(FlaskForm):
    numero = StringField("N°", validators=[Optional(), Length(max=30)])
    oc = StringField("N° OC", validators=[Optional(), Length(max=30)])
    agencia = StringField("Agencia", validators=[Optional(), Length(max=100)])
    n_doc_agencia = StringField("N° Doc Agencia", validators=[Optional(), Length(max=30)])
    monto_doc_agencia = IntegerField("Monto Doc Agencia", validators=[Optional(), NumberRange(min=0)], default=0)
    proveedor = StringField("Proveedor / Cliente", validators=[Optional(), Length(max=150)])
    n_invoice = StringField("N° Invoice", validators=[Optional(), Length(max=40)])
    estado = SelectField(
        "Estado",
        choices=[("pendiente", "Pendiente"), ("revision", "Revisión"), ("pagado", "Pagado")],
        default="pendiente",
    )
    rut = StringField("RUT", validators=[Optional(), Length(max=20)])
    razon_social = StringField("Nombre / Razón social", validators=[Optional(), Length(max=150)])
    formulario = StringField("Form.", validators=[Optional(), Length(max=10)])
    folio = StringField("Folio", validators=[Optional(), Length(max=30)])
    fecha_pago = DateField("Fecha pago", validators=[Optional()])
    vcto = DateField("Vencimiento", validators=[Optional()])
    advalorem = IntegerField("Advalorem", validators=[Optional(), NumberRange(min=0)], default=0)
    total_pagado = IntegerField("Total pagado", validators=[Optional(), NumberRange(min=0)], default=0)


class AccionForm(FlaskForm):
    """Formulario vacío, solo para llevar el token CSRF en botones de acción (eliminar, agregar línea...)."""


class CosteoImportacionForm(FlaskForm):
    n_importacion = StringField("N° Importación", validators=[Optional(), Length(max=30)])
    fecha_llegada = DateField("Fecha llegada", validators=[Optional()])
    guia_despacho = StringField("Guía de despacho", validators=[Optional(), Length(max=40)])
    proveedor = StringField("Proveedor", validators=[Optional(), Length(max=150)])
    modo_venta = StringField("Modo de venta", validators=[Optional(), Length(max=40)])
    purchase_order = StringField("Purchase Order", validators=[Optional(), Length(max=40)])
    orden_trabajo = StringField("Orden de trabajo", validators=[Optional(), Length(max=60)])
    responsable_costeo = StringField("Responsable costeo", validators=[Optional(), Length(max=120)])
    tipo_flete_proyectado = StringField("Tipo de flete proyectado", validators=[Optional(), Length(max=20)])
    solicitud_compra = StringField("Solicitud de compra", validators=[Optional(), Length(max=40)])
    tasa_ad_valorem = FloatField(
        "Tasa Ad Valorem (%)", validators=[Optional(), NumberRange(min=0, max=100)], default=6
    )
    estado = SelectField(
        "Estado",
        choices=[("en_proceso", "En proceso"), ("listo", "Listo para contabilizar"), ("contabilizado", "Contabilizado")],
        default="en_proceso",
    )
    importacion_id = SelectField("Importación (PEI) vinculada", coerce=int, validators=[Optional()])

    # --- Control DIN de esta importación ---
    din_agencia = StringField("Agencia", validators=[Optional(), Length(max=100)])
    din_n_doc_agencia = StringField("N° Doc Agencia", validators=[Optional(), Length(max=40)])
    din_monto_doc_agencia = IntegerField("Monto Doc Agencia", validators=[Optional(), NumberRange(min=0)])
    din_n_invoice = StringField("N° Invoice", validators=[Optional(), Length(max=40)])
    din_estado = SelectField(
        "Estado DIN",
        choices=[("", "—"), ("pendiente", "Pendiente"), ("revision", "Revisión"), ("pagado", "Pagado")],
        validators=[Optional()],
    )
    din_rut = StringField("RUT", validators=[Optional(), Length(max=20)])
    din_razon_social = StringField("Nombre / Razón social", validators=[Optional(), Length(max=150)])
    din_formulario = StringField("Form.", validators=[Optional(), Length(max=10)])
    din_folio = StringField("Folio", validators=[Optional(), Length(max=30)])
    din_fecha_pago = DateField("Fecha pago", validators=[Optional()])
    din_vcto = DateField("Vencimiento", validators=[Optional()])
    din_advalorem_clp = IntegerField("Advalorem", validators=[Optional(), NumberRange(min=0)])
    din_total_pagado = IntegerField("Total pagado", validators=[Optional(), NumberRange(min=0)])
