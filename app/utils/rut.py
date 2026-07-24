import re

from wtforms.validators import ValidationError

_RUT_LIMPIO_RE = re.compile(r"[^0-9kK]")


def limpiar_rut(rut: str) -> str:
    """Deja solo dígitos y dígito verificador (sin puntos ni guion), mayúscula si es K."""
    return _RUT_LIMPIO_RE.sub("", rut or "").upper()


def calcular_dv(cuerpo: str) -> str:
    suma = 0
    multiplicador = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplicador
        multiplicador = multiplicador + 1 if multiplicador < 7 else 2
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def es_rut_valido(rut: str) -> bool:
    limpio = limpiar_rut(rut)
    if len(limpio) < 2:
        return False
    cuerpo, dv = limpio[:-1], limpio[-1]
    if not cuerpo.isdigit():
        return False
    return calcular_dv(cuerpo) == dv


def formatear_rut(rut: str) -> str:
    limpio = limpiar_rut(rut)
    if len(limpio) < 2:
        return rut
    cuerpo, dv = limpio[:-1], limpio[-1]
    cuerpo_con_puntos = "{:,}".format(int(cuerpo)).replace(",", ".")
    return f"{cuerpo_con_puntos}-{dv}"


def validar_rut(form, field):
    """Validador WTForms."""
    if field.data and not es_rut_valido(field.data):
        raise ValidationError("RUT inválido.")
