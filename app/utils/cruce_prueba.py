"""Comparar dos planillas sin cargarlas al sistema.

El maestro de artículos es uno solo y lo miran todos los submódulos de
Inventario. Para ver un cruce no hace falta escribirlo: se leen las dos
planillas, se arman artículos en memoria y se comparan. Los artículos que
salen de acá nunca entran a la sesión de la base de datos, así que no se
guardan por mucho que se los recorra.

Las decisiones ya tomadas en Unificar códigos sí se leen —las parejas
confirmadas y las líneas unidas—, porque si no la prueba mostraría como
"Falta en QMS" pares que alguien ya resolvió. Leerlas no las cambia.
"""

from decimal import Decimal, InvalidOperation

from app.models.conteo_inventario import ItemConteoInventario
from app.utils.codigos import codigo_normalizado

# La misma escala con que la columna guarda las cantidades, para que la
# prueba y lo importado se vean igual.
CERO = Decimal("0.000")


def _cantidad(valor):
    """Vuelve a Decimal una cantidad que pasó por el guardado.

    A propósito NO usa a_cantidad(): ése lee como lo escribe una persona, donde
    el punto son los miles, y acá el texto lo escribió str(Decimal). Leer así
    "7.000" —siete, con tres decimales— lo convertiría en siete mil, y el cruce
    mostraría mil veces el stock que hay.
    """
    if valor is None or valor == "":
        return CERO
    if isinstance(valor, Decimal):
        return valor
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return CERO


def comparar(lectura_qms: dict, lectura_defontana: dict, equivalencias=None) -> list:
    """Artículos en memoria con los dos lados puestos, listos para el cruce.

    `equivalencias` traduce la clave de un código al del artículo con que ya se
    unió. Devuelve una lista ordenada por código, sin tocar la base.
    """
    equivalencias = equivalencias or {}
    por_clave = {}

    def fila(clave, codigo):
        if clave not in por_clave:
            por_clave[clave] = ItemConteoInventario(
                codigo=codigo,
                cantidad_qms=CERO,
                cantidad_defontana=CERO,
                en_qms=False,
                en_defontana=False,
            )
        return por_clave[clave]

    # QMS primero: cuando el mismo artículo está en los dos, el código que se
    # muestra es el de QMS, igual que al importar.
    for codigo, datos in lectura_qms.items():
        clave = equivalencias.get(codigo_normalizado(codigo), codigo_normalizado(codigo))
        item = fila(clave, codigo)
        item.cantidad_qms = item.cantidad_qms + _cantidad(datos.get("cantidad"))
        item.en_qms = True
        item.nombre = item.nombre or datos.get("nombre") or None
        item.linea_negocio = item.linea_negocio or datos.get("linea_negocio") or None
        item.ubicacion = item.ubicacion or datos.get("ubicacion") or None
        item.categoria = item.categoria or datos.get("categoria") or None
        item.unidad_qms = datos.get("unidad") or None
        item.costo_unitario_qms = datos.get("costo")

    for codigo, datos in lectura_defontana.items():
        clave = equivalencias.get(codigo_normalizado(codigo), codigo_normalizado(codigo))
        item = fila(clave, codigo)
        item.cantidad_defontana = item.cantidad_defontana + _cantidad(datos.get("cantidad"))
        item.en_defontana = True
        item.nombre = item.nombre or datos.get("nombre") or None
        bodegas = datos.get("bodegas") or []
        item.ubicacion = item.ubicacion or (", ".join(sorted(bodegas))[:255] if bodegas else None)
        item.unidad_defontana = datos.get("unidad") or None
        item.costo_unitario_defontana = datos.get("costo")

    return sorted(por_clave.values(), key=lambda i: i.codigo)


def para_guardar(lectura: dict) -> dict:
    """Deja lo leído en tipos que se pueden guardar como JSON.

    Los importadores trabajan con Decimal y con un conjunto de bodegas; ninguno
    de los dos sobrevive a json.dumps().
    """
    limpio = {}
    for codigo, datos in lectura.items():
        fila = {}
        for campo, valor in datos.items():
            if isinstance(valor, (set, frozenset)):
                fila[campo] = sorted(valor)
            elif isinstance(valor, (str, int, float, bool, type(None), list)):
                fila[campo] = valor
            else:   # Decimal
                fila[campo] = str(valor)
        limpio[codigo] = fila
    return limpio
