import csv
import io
import re

from app.extensions import db
from app.models.conteo_inventario import ItemConteoInventario

_ESPACIOS_RE = re.compile(r"\s+")


def _a_entero(valor) -> int:
    """Convierte un número de stock (típicamente entero, a veces con decimales) a int.

    Acepta tanto texto (CSV) como números nativos (Excel vía openpyxl).
    """
    if valor is None or valor == "":
        return 0
    if isinstance(valor, (int, float)):
        return round(valor)
    limpio = str(valor).strip()
    if not limpio:
        return 0
    try:
        return int(limpio)
    except ValueError:
        pass
    try:
        return round(float(limpio))
    except ValueError:
        return 0


def _a_monto(valor):
    """Convierte un importe exportado por planilla a entero de pesos.

    Acepta números nativos (Excel) y texto con distintos formatos de miles/decimales:
    '19,563,554', '1.961.923', '1.234,56' y '1,234.56' (el último separador manda
    cuando quedan 1-2 dígitos a su derecha; en cualquier otro caso son separadores de
    miles). Devuelve None si no hay dato utilizable.
    """
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return round(valor)

    limpio = str(valor).strip().replace("$", "").replace(" ", "").replace("\xa0", "")
    if not limpio:
        return None
    negativo = limpio.startswith("-") or (limpio.startswith("(") and limpio.endswith(")"))
    limpio = limpio.strip("-()")

    ultimo_separador = max(limpio.rfind(","), limpio.rfind("."))
    if ultimo_separador != -1 and len(limpio) - ultimo_separador - 1 in (1, 2):
        entero = limpio[:ultimo_separador].replace(".", "").replace(",", "")
        decimales = limpio[ultimo_separador + 1 :]
        numero_texto = f"{entero}.{decimales}" if entero else f"0.{decimales}"
    else:
        numero_texto = limpio.replace(".", "").replace(",", "")

    try:
        numero = round(float(numero_texto))
    except ValueError:
        return None
    return -numero if negativo else numero


def _buscar_columna(campos, *palabras_clave):
    """Primera columna cuyo nombre contiene todas las palabras clave (sin distinguir mayúsculas)."""
    for campo in campos or []:
        nombre = campo.lower()
        if all(palabra in nombre for palabra in palabras_clave):
            return campo
    return None


def _normalizar_codigo(codigo) -> str:
    """Normaliza el código para que QMS y Defontana crucen como el mismo artículo.

    Quita apóstrofes iniciales (artefacto de Excel) y TODOS los espacios internos:
    QMS suele exportar 'ROP- BCAN-M' donde Defontana trae 'ROP-BCAN-M' para el mismo
    código, y sin esta limpieza aparecen como dos artículos distintos en el cruce.
    """
    texto = str(codigo).strip().lstrip("'").strip()
    return _ESPACIOS_RE.sub("", texto)[:80]


def _texto(valor, limite: int) -> str:
    """Recorta al límite de la columna: PostgreSQL rechaza los textos que se pasan, SQLite no."""
    if valor is None:
        return ""
    return str(valor).strip()[:limite]


def _es_xlsx(file_storage) -> bool:
    nombre = (file_storage.filename or "").lower()
    if nombre.endswith(".xlsx"):
        return True
    if nombre.endswith(".csv"):
        return False
    # Sin extensión reconocible: un .xlsx es un zip, empieza con "PK".
    inicio = file_storage.stream.read(2)
    file_storage.stream.seek(0)
    return inicio == b"PK"


def _filas_desde_xlsx(file_storage):
    """(encabezados, filas) desde un .xlsx: cada fila es un dict encabezado -> valor nativo."""
    from openpyxl import load_workbook

    libro = load_workbook(file_storage.stream, data_only=True, read_only=True)
    hoja = libro.active
    filas = hoja.iter_rows(values_only=True)
    encabezados = [str(c).strip() if c is not None else "" for c in next(filas, [])]

    def generador():
        for fila in filas:
            if all(valor is None for valor in fila):
                continue
            yield dict(zip(encabezados, fila))

    return encabezados, generador()


def _filas_desde_csv(file_storage, codificaciones=("utf-8-sig",)):
    """(encabezados, filas) desde un .csv separado por punto y coma, con las codificaciones dadas en orden."""
    crudo = file_storage.stream.read()
    for codificacion in codificaciones:
        try:
            contenido = crudo.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("No se pudo leer la codificación del archivo.")

    reader = csv.DictReader(io.StringIO(contenido), delimiter=";")
    return reader.fieldnames, reader


def _leer_filas(file_storage, codificaciones_csv=("utf-8-sig",)):
    """Punto único de entrada: detecta si el archivo es .xlsx o .csv y devuelve (encabezados, filas)."""
    if _es_xlsx(file_storage):
        return _filas_desde_xlsx(file_storage)
    return _filas_desde_csv(file_storage, codificaciones_csv)


# IMPORTANTE: los importadores sólo actualizan lo que declara cada sistema
# (cantidades, costo, unidad, nombre, ubicación). Nunca escriben cantidad_fisica,
# contado_por_id ni contado_en: el conteo físico es trabajo de bodega y debe
# sobrevivir a cualquier reimportación de QMS o Defontana.


def _items_existentes(empresa_id: int) -> dict:
    """Trae todos los items de la empresa en una sola consulta.

    Consultar código por código genera miles de round-trips contra la base de datos
    remota y agota el tiempo de la petición.
    """
    return {
        item.codigo: item
        for item in ItemConteoInventario.query.filter_by(empresa_id=empresa_id).all()
    }


def importar_qms(file_storage, empresa_id: int) -> dict:
    """Archivo 'Distribución Valor Stock CLP' de QMS (.csv o .xlsx): código único, descripción,
    stock, línea de negocio, categoría, unidad y costo unitario."""
    encabezados, reader = _leer_filas(file_storage)

    columna_codigo = next((c for c in encabezados if "digo" in c.lower() and "nico" in c.lower()), None)
    columna_nombre = next((c for c in encabezados if "descripci" in c.lower()), None)
    columna_stock = "Stock" if "Stock" in encabezados else _buscar_columna(encabezados, "stock")
    columna_linea = "Linea Negocio" if "Linea Negocio" in encabezados else _buscar_columna(encabezados, "linea")
    columna_ubicacion = "ubicacion_bodega"
    columna_unidad = _buscar_columna(encabezados, "unidad")
    columna_categoria = _buscar_columna(encabezados, "categor")
    columna_costo = _buscar_columna(encabezados, "valor", "unitario")
    columna_valor_total = _buscar_columna(encabezados, "valor", "total")

    if not columna_codigo or not columna_nombre:
        raise ValueError("No se encontraron las columnas de código/descripción esperadas en el archivo QMS.")

    acumulado = {}  # codigo -> dict con datos agregados
    for fila in reader:
        codigo = _normalizar_codigo(fila.get(columna_codigo) or "")
        if not codigo:
            continue
        cantidad = _a_entero(fila.get(columna_stock, "0"))
        if codigo not in acumulado:
            acumulado[codigo] = {
                "cantidad": 0,
                "nombre": _texto(fila.get(columna_nombre), 255),
                "linea_negocio": _texto(fila.get(columna_linea), 120) if columna_linea else "",
                "ubicacion": _texto(fila.get(columna_ubicacion), 255) or _texto(fila.get("Sucursal"), 255),
                "categoria": _texto(fila.get(columna_categoria), 120) if columna_categoria else "",
                "unidad": _texto(fila.get(columna_unidad), 20) if columna_unidad else "",
                "costo": None,
            }
        acumulado[codigo]["cantidad"] += cantidad

        # Costo unitario: viene explícito o se deduce del valor total de la fila
        costo = _a_monto(fila.get(columna_costo)) if columna_costo else None
        if costo is None and columna_valor_total and cantidad:
            total = _a_monto(fila.get(columna_valor_total))
            if total:
                costo = round(total / cantidad)
        if costo and acumulado[codigo]["costo"] is None:
            acumulado[codigo]["costo"] = costo

    existentes = _items_existentes(empresa_id)
    filas_creadas = 0
    filas_actualizadas = 0
    nuevos = []
    for codigo, datos in acumulado.items():
        item = existentes.get(codigo)
        if item is None:
            item = ItemConteoInventario(empresa_id=empresa_id, codigo=codigo, cantidad_defontana=0)
            nuevos.append(item)
            filas_creadas += 1
        else:
            filas_actualizadas += 1
        item.cantidad_qms = datos["cantidad"]
        if datos["nombre"]:
            item.nombre = datos["nombre"]
        if datos["linea_negocio"]:
            item.linea_negocio = datos["linea_negocio"]
        if datos["ubicacion"] and not item.ubicacion:
            item.ubicacion = datos["ubicacion"]
        if datos["categoria"]:
            item.categoria = datos["categoria"]
        if datos["unidad"]:
            item.unidad_qms = datos["unidad"]
        if datos["costo"] is not None:
            item.costo_unitario_qms = datos["costo"]

    if nuevos:
        db.session.add_all(nuevos)
    db.session.commit()
    return {"total_codigos": len(acumulado), "creados": filas_creadas, "actualizados": filas_actualizadas}


def importar_defontana(file_storage, empresa_id: int) -> dict:
    """Archivo de inventario por bodega de Defontana (.csv o .xlsx): CodArticulo, Descripción,
    CodBodega, Nombre Bodega, Saldo Stock."""
    encabezados, reader = _leer_filas(file_storage, codificaciones_csv=("cp1252", "latin-1", "utf-8-sig"))

    columna_codigo = next((c for c in encabezados if "codarticulo" in c.lower()), None)
    columna_nombre = next((c for c in encabezados if "descripci" in c.lower()), None)
    columna_stock = next((c for c in encabezados if "saldo" in c.lower()), None)
    columna_bodega = next((c for c in encabezados if "nombre bodega" in c.lower()), None)
    columna_unidad = _buscar_columna(encabezados, "unidad")
    # Defontana exporta el costo con nombres distintos según el informe
    columna_costo = (
        _buscar_columna(encabezados, "costo", "unitario")
        or _buscar_columna(encabezados, "costo", "promedio")
        or _buscar_columna(encabezados, "costo")
        or _buscar_columna(encabezados, "valor", "unitario")
    )
    columna_valor_total = _buscar_columna(encabezados, "valor", "total") or _buscar_columna(
        encabezados, "total", "costo"
    )

    if not columna_codigo or not columna_stock:
        raise ValueError("No se encontraron las columnas de código/stock esperadas en el archivo de Defontana.")

    acumulado = {}
    for fila in reader:
        codigo = _normalizar_codigo(fila.get(columna_codigo) or "")
        if not codigo:
            continue
        cantidad = _a_entero(fila.get(columna_stock, "0"))
        bodega = _texto(fila.get(columna_bodega), 255) if columna_bodega else ""
        if codigo not in acumulado:
            acumulado[codigo] = {
                "cantidad": 0,
                "nombre": _texto(fila.get(columna_nombre), 255) if columna_nombre else "",
                "bodegas": set(),
                "unidad": _texto(fila.get(columna_unidad), 20) if columna_unidad else "",
                "costo": None,
            }
        acumulado[codigo]["cantidad"] += cantidad
        if bodega and cantidad:
            acumulado[codigo]["bodegas"].add(bodega)

        costo = _a_monto(fila.get(columna_costo)) if columna_costo else None
        if costo is None and columna_valor_total and cantidad:
            total = _a_monto(fila.get(columna_valor_total))
            if total:
                costo = round(total / cantidad)
        if costo and acumulado[codigo]["costo"] is None:
            acumulado[codigo]["costo"] = costo

    existentes = _items_existentes(empresa_id)
    filas_creadas = 0
    filas_actualizadas = 0
    nuevos = []
    for codigo, datos in acumulado.items():
        item = existentes.get(codigo)
        if item is None:
            item = ItemConteoInventario(empresa_id=empresa_id, codigo=codigo, cantidad_qms=0)
            nuevos.append(item)
            filas_creadas += 1
        else:
            filas_actualizadas += 1
        item.cantidad_defontana = datos["cantidad"]
        if datos["nombre"] and not item.nombre:
            item.nombre = datos["nombre"]
        if datos["bodegas"] and not item.ubicacion:
            item.ubicacion = ", ".join(sorted(datos["bodegas"]))[:255]
        if datos["unidad"]:
            item.unidad_defontana = datos["unidad"]
        if datos["costo"] is not None:
            item.costo_unitario_defontana = datos["costo"]

    if nuevos:
        db.session.add_all(nuevos)
    db.session.commit()
    return {"total_codigos": len(acumulado), "creados": filas_creadas, "actualizados": filas_actualizadas}
