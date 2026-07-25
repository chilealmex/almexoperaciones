import csv
import io
from datetime import datetime, timezone

from app.extensions import db
from app.models.conteo_inventario import ItemConteoInventario


def _a_entero(valor: str) -> int:
    """Convierte un número de stock (típicamente entero, a veces con decimales) a int, sin asumir formato de miles."""
    if not valor:
        return 0
    limpio = valor.strip()
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


def _normalizar_codigo(codigo: str) -> str:
    """Quita apóstrofes iniciales (artefacto de Excel) y espacios para que ambos sistemas crucen."""
    return codigo.strip().lstrip("'").strip()


def _obtener_item(empresa_id: int, codigo: str) -> ItemConteoInventario:
    item = ItemConteoInventario.query.filter_by(empresa_id=empresa_id, codigo=codigo).first()
    if item is None:
        item = ItemConteoInventario(empresa_id=empresa_id, codigo=codigo, cantidad_qms=0, cantidad_defontana=0)
        db.session.add(item)
    return item


def importar_qms(file_storage, empresa_id: int) -> dict:
    """Archivo 'Distribución Valor Stock CLP' de QMS: código único, descripción, stock, línea de negocio, ubicación."""
    contenido = file_storage.stream.read().decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(contenido), delimiter=";")

    columna_codigo = next((c for c in reader.fieldnames if "digo" in c.lower() and "nico" in c.lower()), None)
    columna_nombre = next((c for c in reader.fieldnames if "descripci" in c.lower()), None)
    columna_stock = "Stock"
    columna_linea = "Linea Negocio"
    columna_ubicacion = "ubicacion_bodega"

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
                "nombre": (fila.get(columna_nombre) or "").strip(),
                "linea_negocio": (fila.get(columna_linea) or "").strip(),
                "ubicacion": (fila.get(columna_ubicacion) or "").strip() or (fila.get("Sucursal") or "").strip(),
            }
        acumulado[codigo]["cantidad"] += cantidad

    filas_creadas = 0
    filas_actualizadas = 0
    for codigo, datos in acumulado.items():
        item = ItemConteoInventario.query.filter_by(empresa_id=empresa_id, codigo=codigo).first()
        es_nuevo = item is None
        if es_nuevo:
            item = ItemConteoInventario(empresa_id=empresa_id, codigo=codigo)
            db.session.add(item)
        item.cantidad_qms = datos["cantidad"]
        if datos["nombre"]:
            item.nombre = datos["nombre"]
        if datos["linea_negocio"]:
            item.linea_negocio = datos["linea_negocio"]
        if datos["ubicacion"] and not item.ubicacion:
            item.ubicacion = datos["ubicacion"]
        if es_nuevo:
            filas_creadas += 1
        else:
            filas_actualizadas += 1

    db.session.commit()
    return {"total_codigos": len(acumulado), "creados": filas_creadas, "actualizados": filas_actualizadas}


def importar_defontana(file_storage, empresa_id: int) -> dict:
    """Archivo de inventario por bodega de Defontana: CodArticulo, Descripción, CodBodega, Nombre Bodega, Saldo Stock."""
    crudo = file_storage.stream.read()
    for codificacion in ("cp1252", "latin-1", "utf-8-sig"):
        try:
            contenido = crudo.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("No se pudo leer la codificación del archivo de Defontana.")

    reader = csv.DictReader(io.StringIO(contenido), delimiter=";")
    columna_codigo = next((c for c in reader.fieldnames if "codarticulo" in c.lower()), None)
    columna_nombre = next((c for c in reader.fieldnames if "descripci" in c.lower()), None)
    columna_stock = next((c for c in reader.fieldnames if "saldo" in c.lower()), None)
    columna_bodega = next((c for c in reader.fieldnames if "nombre bodega" in c.lower()), None)

    if not columna_codigo or not columna_stock:
        raise ValueError("No se encontraron las columnas de código/stock esperadas en el archivo de Defontana.")

    acumulado = {}
    for fila in reader:
        codigo = _normalizar_codigo(fila.get(columna_codigo) or "")
        if not codigo:
            continue
        cantidad = _a_entero(fila.get(columna_stock, "0"))
        bodega = (fila.get(columna_bodega) or "").strip() if columna_bodega else ""
        if codigo not in acumulado:
            acumulado[codigo] = {
                "cantidad": 0,
                "nombre": (fila.get(columna_nombre) or "").strip() if columna_nombre else "",
                "bodegas": set(),
            }
        acumulado[codigo]["cantidad"] += cantidad
        if bodega and cantidad:
            acumulado[codigo]["bodegas"].add(bodega)

    filas_creadas = 0
    filas_actualizadas = 0
    for codigo, datos in acumulado.items():
        item = ItemConteoInventario.query.filter_by(empresa_id=empresa_id, codigo=codigo).first()
        es_nuevo = item is None
        if es_nuevo:
            item = ItemConteoInventario(empresa_id=empresa_id, codigo=codigo)
            db.session.add(item)
        item.cantidad_defontana = datos["cantidad"]
        if datos["nombre"] and not item.nombre:
            item.nombre = datos["nombre"]
        if datos["bodegas"] and not item.ubicacion:
            item.ubicacion = ", ".join(sorted(datos["bodegas"]))
        if es_nuevo:
            filas_creadas += 1
        else:
            filas_actualizadas += 1

    db.session.commit()
    return {"total_codigos": len(acumulado), "creados": filas_creadas, "actualizados": filas_actualizadas}
