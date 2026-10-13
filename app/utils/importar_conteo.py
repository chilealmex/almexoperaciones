import csv
import io
import re
import unicodedata
from datetime import date, datetime, timezone

from flask import current_app
from sqlalchemy import update

from app.extensions import db
from app.models.conteo_inventario import ItemConteoInventario
from app.utils.codigos import (  # noqa: F401
    clave_sin_ceros,
    codigo_normalizado,
    rarezas_del_codigo,
)
from app.utils.cantidades import a_cantidad, punto_ambiguo
from app.utils.formatting import ZONA_LOCAL

_ESPACIOS_RE = re.compile(r"\s+")
CERO = a_cantidad(0)


def _a_cantidad(valor):
    """Convierte un número de stock a Decimal, conservando los decimales.

    Acepta tanto texto (CSV) como números nativos (Excel vía openpyxl). Los
    decimales no se redondean: hay artículos que se miden en metros o kilos y
    "12,5" es el stock real, no un entero mal escrito.
    """
    return a_cantidad(valor, por_defecto=CERO)


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
    """Limpia el código tal como se va a GUARDAR.

    Quita apóstrofes iniciales (artefacto de Excel), todos los espacios internos
    y los caracteres invisibles de categoría Cf (espacio de ancho cero, guion
    suave, BOM). QMS suele exportar 'ROP- BCAN-M' donde Defontana trae
    'ROP-BCAN-M' para el mismo código, y sin esta limpieza aparecen como dos
    artículos distintos en el cruce; con los invisibles es peor todavía, porque
    en pantalla se ven exactamente iguales.

    El guion NO se toca aquí: se deja el que venga en la planilla para que el
    código guardado siga siendo el del sistema de origen. Unificar los guiones
    es cosa de codigo_normalizado(), que es sólo la clave de comparación.
    """
    texto = str(codigo).strip().lstrip("'").strip()
    sin_invisibles = "".join(c for c in texto if unicodedata.category(c) != "Cf")
    return _ESPACIOS_RE.sub("", sin_invisibles)[:80]


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


def _campos(linea: str, sin_comillas=False) -> list:
    modo = {"quoting": csv.QUOTE_NONE} if sin_comillas else {}
    fila = next(csv.reader([linea], delimiter=";", **modo), [])
    if sin_comillas:
        fila = [_sin_las_comillas_del_formato(c) for c in fila]
    return fila


def _sin_las_comillas_del_formato(campo: str) -> str:
    """Saca las comillas que envuelven al campo, dejando las que son del dato.

    Importa la diferencia: el código 'LAX Bar Set 96"' lleva una comilla al
    final, y sacarla de más lo convierte en otro código que no cruza con el de
    la planilla que vino bien escrita. Se quita una sola de cada extremo —las
    que puso el formato— y las que quedaron duplicadas vuelven a una.
    """
    campo = campo.strip()
    if len(campo) >= 2 and campo.startswith('"') and campo.endswith('"'):
        campo = campo[1:-1]
    return campo.replace('""', '"')


def _comillas_sin_cerrar(texto: str) -> bool:
    return texto.count('"') % 2 == 1


def _filas_del_csv(contenido: str):
    """Las filas de un .csv por punto y coma, recuperando las mal escritas.

    Un campo que lleva comillas dentro —un código como 'LAX Bar Set 96"'— se
    exporta mal cada tanto: la comilla no viene duplicada, y entonces el lector
    se come el separador siguiente. El código se traga la descripción, todas
    las columnas se corren una, y no falla nada: queda un artículo fantasma con
    un código imposible y se pierde el de verdad, sin que nadie lo note.

    Por eso se lee fila por fila y se comprueba que tenga tantas columnas como
    el encabezado. La que no cuadra se vuelve a leer tratando las comillas como
    texto corriente, que es lo que son cuando vienen mal escritas. Una fila que
    quedó corta porque el campo sigue en la línea de abajo —comillas sin
    cerrar— se junta con la siguiente, que es el caso legítimo y se ve igual.

    Devuelve (encabezados, filas, cuántas hubo que recuperar).
    """
    lineas = contenido.splitlines()
    while lineas and not lineas[0].strip():
        lineas.pop(0)
    if not lineas:
        return [], [], 0

    encabezados = _campos(lineas[0])
    cuantas = len(encabezados)
    filas, rotas = [], 0

    pendiente = ""
    for linea in lineas[1:]:
        acumulado = f"{pendiente}\n{linea}" if pendiente else linea
        if _comillas_sin_cerrar(acumulado):
            # El campo sigue en la línea de abajo: es el caso legítimo.
            pendiente = acumulado
            continue
        pendiente = ""
        if not acumulado.strip():
            continue
        campos = _campos(acumulado)
        if len(campos) != cuantas:
            recuperada = _campos(acumulado, sin_comillas=True)
            if len(recuperada) == cuantas:
                campos, rotas = recuperada, rotas + 1
        filas.append(dict(zip(encabezados, campos)))

    if pendiente.strip():   # quedó abierta hasta el final: se lee como se pueda
        campos = _campos(pendiente.replace("\n", " "), sin_comillas=True)
        if len(campos) == cuantas:
            rotas += 1
        filas.append(dict(zip(encabezados, campos)))

    return encabezados, filas, rotas


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

    encabezados, filas, rotas = _filas_del_csv(contenido)
    if rotas:
        # Se avisa, aunque se hayan recuperado: el archivo viene mal y conviene
        # saberlo antes de que alguien lo use para otra cosa.
        current_app.logger.warning(
            "El archivo traía %s fila(s) con comillas mal escritas; se leyeron igual.", rotas
        )
    return encabezados, filas


def _leer_filas(file_storage, codificaciones_csv=("utf-8-sig",)):
    """Punto único de entrada: detecta si el archivo es .xlsx o .csv y devuelve (encabezados, filas)."""
    if _es_xlsx(file_storage):
        return _filas_desde_xlsx(file_storage)
    return _filas_desde_csv(file_storage, codificaciones_csv)


# IMPORTANTE: los importadores DE SISTEMA —QMS y Defontana— sólo actualizan lo
# que declara cada sistema (cantidades, costo, unidad, nombre, ubicación).
# Nunca escriben cantidad_fisica, contado_por_id ni contado_en: el conteo
# físico es trabajo de bodega y debe sobrevivir a cualquier reimportación.
#
# El único que escribe el conteo es importar_conteo_fisico(), más abajo, y no
# toca ninguna otra columna: es el mismo trabajo que escribir la cantidad en la
# fila de Stock y conteo, hecho de a muchas.


# Guiones que Excel y Word escriben en vez del normal. Se unifican al '-' de
# toda la vida: "KIT–ST" y "KIT-ST" son el mismo artículo escrito distinto.
def _congela_el_stock(item, solo_no_contados: bool) -> bool:
    """True si a este artículo no hay que actualizarle el stock declarado por el sistema.

    Cuando la toma de inventario dura varios días, bodega cuenta un artículo el
    lunes contra el stock que el sistema declaraba el lunes. Si el martes se
    reimporta el stock, ese artículo pasaría a compararse contra una cifra que ya
    incorpora los movimientos del martes, y aparecería una diferencia que no
    existe: la toma dejaría de cuadrar por culpa de la reimportación, no por un
    error de bodega.

    Por eso, con solo_no_contados=True, a los artículos ya contados se les
    congela la cantidad: siguen comparándose contra la foto del sistema que
    tenían al momento de contarlos. Los que aún no se cuentan sí se actualizan,
    que es justamente lo que se quiere refrescar antes de seguir contando.

    Ojo: sólo se congela la CANTIDAD. Nombre, ubicación, unidad y costo se
    siguen actualizando, porque son datos de referencia que no cambian el
    resultado del conteo (no son movimientos de stock).
    """
    return solo_no_contados and item.cantidad_fisica is not None


def _aplicar_en_lote(cambios: list) -> None:
    """Aplica muchas actualizaciones en una sola ida y vuelta a la base.

    Modificar los objetos del ORM uno por uno parece equivalente, pero al
    guardar SQLAlchemy agrupa los UPDATE por el conjunto de columnas que cambió
    en cada fila. Como aquí cada artículo cambia columnas distintas (el nombre
    sólo si viene, el costo sólo si viene...), se fragmentaba en más de mil
    sentencias, y contra la base remota de Render cada una es una ida y vuelta
    por la red: de ahí que importar tardara minutos.

    Mandando siempre las mismas claves en todos los diccionarios, SQLAlchemy
    puede usar executemany y resolverlo con una sentencia.
    """
    if not cambios:
        return
    # En tandas para no armar una sentencia gigante con miles de parámetros.
    for inicio in range(0, len(cambios), 500):
        db.session.execute(update(ItemConteoInventario), cambios[inicio : inicio + 500])


def _marcar_ausentes_en_lote(items, codigos_del_archivo, campo: str, equivalentes=None) -> None:
    """Apaga la marca del sistema recién importado en los artículos que no venían.

    'items' son los que ya existían antes de esta importación, así que los
    recién creados quedan fuera por construcción: un artículo creado por ESTA
    planilla no puede estar ausente de ella. El otro sistema no se toca, porque
    de esa planilla no sabemos nada en esta pasada.

    Los códigos del archivo se traducen antes de comparar: un artículo unido a
    mano viene con el código del otro sistema, y sin traducirlo se lo daría por
    ausente justo después de haberle actualizado el stock.
    """
    equivalentes = equivalentes or {}
    presentes = set()
    for codigo in codigos_del_archivo:
        clave = codigo_normalizado(codigo)
        presentes.add(equivalentes.get(clave, clave))
    ids = [
        item.id
        for item in items
        if getattr(item, campo) and codigo_normalizado(item.codigo) not in presentes
    ]
    for inicio in range(0, len(ids), 500):
        db.session.execute(
            update(ItemConteoInventario)
            .where(ItemConteoInventario.id.in_(ids[inicio : inicio + 500]))
            .values(**{campo: False})
        )


def _items_de_la_empresa(empresa_id: int) -> list:
    """Todos los artículos de la empresa, incluidos los códigos repetidos.

    Una sola consulta: pedirlos de a uno genera miles de idas y vueltas contra
    la base remota y agota el tiempo de la petición.
    """
    return ItemConteoInventario.query.filter_by(empresa_id=empresa_id).all()


def _por_codigo_normalizado(items) -> dict:
    """Indexa por código normalizado para cruzar QMS y Defontana como el mismo artículo.

    Si hay duplicados de antes, gana el que tenga conteo físico registrado (y
    entre iguales, el más antiguo), para no dejar huérfano el trabajo de bodega.
    """
    por_codigo = {}
    for item in sorted(items, key=lambda i: (i.cantidad_fisica is None, i.id)):
        por_codigo.setdefault(codigo_normalizado(item.codigo), item)
    return por_codigo


def leer_qms(file_storage) -> dict:
    """Lee la planilla de QMS y devuelve {código: datos}, sin tocar la base.

    Separada de importar_qms() para poder comparar dos planillas sin guardar
    nada: si la lectura viviera dentro del importador, la única forma de ver un
    cruce sería escribirlo antes en el maestro.
    """
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
        cantidad = _a_cantidad(fila.get(columna_stock, "0"))
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

    return acumulado


def importar_qms(file_storage, empresa_id: int, solo_no_contados: bool = False) -> dict:
    """Carga en el maestro la planilla 'Distribución Valor Stock CLP' de QMS.

    Con solo_no_contados=True no se toca el stock de los artículos que ya tienen
    conteo físico registrado (ver _congela_el_stock).
    """
    acumulado = leer_qms(file_storage)

    items = _items_de_la_empresa(empresa_id)
    existentes = _por_codigo_normalizado(items)
    # Códigos que alguien ya retiró al unificar dos líneas del mismo artículo.
    # Sin esto la planilla —que sigue trayendo el código viejo— lo recrearía y
    # habría que rehacer la unión en cada carga.
    redirigidos = _redirecciones_de_unificaciones(empresa_id)
    filas_creadas = 0
    filas_actualizadas = 0
    filas_congeladas = 0
    nuevos = []
    cambios = []
    for codigo, datos in acumulado.items():
        clave = codigo_normalizado(codigo)
        item = existentes.get(redirigidos.get(clave, clave))
        if item is None:
            item = ItemConteoInventario(empresa_id=empresa_id, codigo=codigo, cantidad_defontana=0,
                                        en_qms=True, en_defontana=False)
            item.cantidad_qms = datos["cantidad"]
            item.nombre = datos["nombre"] or None
            item.linea_negocio = datos["linea_negocio"] or None
            item.ubicacion = datos["ubicacion"] or None
            item.categoria = datos["categoria"] or None
            item.unidad_qms = datos["unidad"] or None
            item.costo_unitario_qms = datos["costo"]
            nuevos.append(item)
            filas_creadas += 1
            continue

        congelado = _congela_el_stock(item, solo_no_contados)
        if congelado:
            filas_congeladas += 1
        else:
            filas_actualizadas += 1
        # Se manda siempre el mismo juego de columnas (con el valor que ya tenía
        # cuando la planilla no trae dato) para que salga en una sola sentencia.
        cambios.append({
            "id": item.id,
            # El código guardado también se limpia. Una fila creada antes de que
            # existiera esta limpieza se queda con sus espacios para siempre: el
            # importador la encuentra por la clave —que ya los ignora— y le
            # actualiza el stock, pero nunca le toca el código. Limpiarlo no
            # mueve la clave, así que el artículo sigue siendo el mismo.
            "codigo": _normalizar_codigo(item.codigo),
            "cantidad_qms": item.cantidad_qms if congelado else datos["cantidad"],
            "nombre": datos["nombre"] or item.nombre,
            "linea_negocio": datos["linea_negocio"] or item.linea_negocio,
            "ubicacion": item.ubicacion or datos["ubicacion"] or item.ubicacion,
            "categoria": datos["categoria"] or item.categoria,
            "unidad_qms": datos["unidad"] or item.unidad_qms,
            "costo_unitario_qms": datos["costo"] if datos["costo"] is not None else item.costo_unitario_qms,
            "en_qms": True,
        })

    if nuevos:
        db.session.add_all(nuevos)
    _aplicar_en_lote(cambios)
    _marcar_ausentes_en_lote(items, acumulado.keys(), "en_qms", redirigidos)
    db.session.commit()
    return {
        "total_codigos": len(acumulado),
        "creados": filas_creadas,
        "actualizados": filas_actualizadas,
        "congelados": filas_congeladas,
    }


def leer_defontana(file_storage) -> dict:
    """Lee la planilla de Defontana y devuelve {código: datos}, sin tocar la base."""
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
        cantidad = _a_cantidad(fila.get(columna_stock, "0"))
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

    return acumulado


def importar_defontana(file_storage, empresa_id: int, solo_no_contados: bool = False) -> dict:
    """Carga en el maestro el inventario por bodega de Defontana."""
    acumulado = leer_defontana(file_storage)

    items = _items_de_la_empresa(empresa_id)
    existentes = _por_codigo_normalizado(items)
    # Las dos decisiones que alguien ya tomó sobre estos códigos: la pareja
    # confirmada entre sistemas y la línea retirada al unificar. Sin esto
    # habría que rehacer las dos uniones en cada carga.
    equivalentes = _encadenar(
        _traducciones_confirmadas(empresa_id), _redirecciones_de_unificaciones(empresa_id)
    )
    filas_creadas = 0
    filas_actualizadas = 0
    filas_congeladas = 0
    nuevos = []
    cambios = []
    for codigo, datos in acumulado.items():
        bodegas = ", ".join(sorted(datos["bodegas"]))[:255] if datos["bodegas"] else ""
        clave = codigo_normalizado(codigo)
        item = existentes.get(equivalentes.get(clave, clave))
        if item is None:
            item = ItemConteoInventario(empresa_id=empresa_id, codigo=codigo, cantidad_qms=0,
                                        en_defontana=True, en_qms=False)
            item.cantidad_defontana = datos["cantidad"]
            item.nombre = datos["nombre"] or None
            item.ubicacion = bodegas or None
            item.unidad_defontana = datos["unidad"] or None
            item.costo_unitario_defontana = datos["costo"]
            nuevos.append(item)
            filas_creadas += 1
            continue

        congelado = _congela_el_stock(item, solo_no_contados)
        if congelado:
            filas_congeladas += 1
        else:
            filas_actualizadas += 1
        cambios.append({
            "id": item.id,
            # Igual que en QMS: se limpia el código guardado, que de otro modo
            # se queda con los espacios con que se creó.
            "codigo": _normalizar_codigo(item.codigo),
            "cantidad_defontana": item.cantidad_defontana if congelado else datos["cantidad"],
            "nombre": item.nombre or datos["nombre"] or item.nombre,
            "ubicacion": item.ubicacion or bodegas or item.ubicacion,
            "unidad_defontana": datos["unidad"] or item.unidad_defontana,
            "costo_unitario_defontana": (
                datos["costo"] if datos["costo"] is not None else item.costo_unitario_defontana
            ),
            "en_defontana": True,
        })

    if nuevos:
        db.session.add_all(nuevos)
    _aplicar_en_lote(cambios)
    _marcar_ausentes_en_lote(items, acumulado.keys(), "en_defontana", equivalentes)
    db.session.commit()
    return {
        "total_codigos": len(acumulado),
        "creados": filas_creadas,
        "actualizados": filas_actualizadas,
        "congelados": filas_congeladas,
    }


def _encadenar(*mapas) -> dict:
    """Un solo mapa que aplica los otros en orden, de izquierda a derecha.

    Un código de Defontana puede tener que dar dos saltos: primero el de la
    pareja confirmada, que lo lleva al código de QMS, y después el de una
    unificación, si esa línea de QMS se unió después con otra. Los
    importadores resuelven un salto, así que la cadena se arma acá.
    """
    resuelto = {}
    for clave in {k for mapa in mapas for k in mapa}:
        destino = clave
        for mapa in mapas:
            destino = mapa.get(destino, destino)
        if destino != clave:
            resuelto[clave] = destino
    return resuelto


def _registrar_unificacion(empresa_id, codigo_vigente, codigo_retirado, usuario_id) -> None:
    """El import va acá dentro por el mismo ciclo que _traducciones_confirmadas()."""
    from app.models.codigo_unificado import registrar_unificacion

    registrar_unificacion(empresa_id, codigo_vigente, codigo_retirado, usuario_id)


def _redirecciones_de_unificaciones(empresa_id) -> dict:
    """{clave retirada: clave vigente} de las líneas ya unificadas."""
    from app.models.codigo_unificado import redirecciones

    return redirecciones(empresa_id)


def _traducciones_confirmadas(empresa_id) -> dict:
    """{clave Defontana: clave QMS} de las equivalencias ya confirmadas.

    El import va acá dentro y no arriba porque el modelo de equivalencias usa
    codigo_normalizado() de este mismo módulo, y arriba sería un ciclo.
    """
    from app.models.equivalencia_codigo import traducciones

    return traducciones(empresa_id)


def articulos_fuera_de_ambas_planillas(empresa_id: int) -> list:
    """Artículos que dejaron de aparecer tanto en QMS como en Defontana."""
    return (
        ItemConteoInventario.query.filter_by(empresa_id=empresa_id, en_qms=False, en_defontana=False)
        .order_by(ItemConteoInventario.codigo)
        .all()
    )


def grupos_duplicados(empresa_id: int) -> list:
    """Artículos cuyo código es el mismo escrito distinto.

    Se agrupan sin espacios, acentos ni mayúsculas, y también sin los ceros de
    relleno: "011-CON-OTH-01" y "11-CON-OTH-01" son el mismo artículo, y el
    cero de adelante lo pone quien exporta.

    Esto sólo *propone* el grupo. Unirlo lo decide una persona desde la
    pantalla, que es la protección: la llave del importador no cambia.

    Devuelve una lista de grupos (2 o más artículos cada uno), ordenados por
    código, para poder revisarlos y unificarlos desde la pantalla.
    """
    from collections import defaultdict as _dd

    por_clave = _dd(list)
    for item in ItemConteoInventario.query.filter_by(empresa_id=empresa_id).all():
        por_clave[clave_sin_ceros(item.codigo)].append(item)
    grupos = [sorted(items, key=lambda i: i.id) for items in por_clave.values() if len(items) > 1]
    return sorted(grupos, key=lambda g: g[0].codigo)


def _primero(valores):
    return next((v for v in valores if v not in (None, "")), None)


def unificar_grupo(items: list, usuario_id=None) -> ItemConteoInventario:
    """Deja un solo artículo con la suma de los duplicados y borra el resto.

    La fila que queda es la que todavía viene en alguna de las dos planillas.
    Importa cuál: el importador reconoce al artículo por su código, así que si
    quedara el código viejo —el que ya no trae ningún sistema— la próxima
    importación no lo encontraría y volvería a crear el otro. El duplicado
    reaparecería solo.

    Los códigos que se retiran quedan guardados apuntando al que queda. Sin eso
    la unión duraba hasta la próxima importación: la planilla sigue trayendo el
    código retirado —quien exporta no cambió nada— y el duplicado volvía a
    aparecer en cada carga.

    Entre las que vienen en una planilla, se prefiere la que tiene conteo
    físico y, entre iguales, la más antigua. El conteo no se pierde en ningún
    caso: se traspasa a la que queda, venga de donde venga.

    Las cantidades se suman, porque cada fila era stock declarado por
    separado, y los datos de texto que falten en la fila que queda se
    completan con los de las otras.
    """
    if len(items) < 2:
        return items[0] if items else None

    ordenados = sorted(
        items,
        key=lambda i: (not (i.en_qms or i.en_defontana), i.cantidad_fisica is None, i.id),
    )
    principal, resto = ordenados[0], ordenados[1:]

    principal.cantidad_qms = sum(i.cantidad_qms or 0 for i in ordenados)
    principal.cantidad_defontana = sum(i.cantidad_defontana or 0 for i in ordenados)
    # Si cualquiera de las filas estaba en un sistema, la que queda lo está:
    # es la misma mercadería. Importa cuando cada sistema escribió el código a
    # su manera y cada fila quedó marcada en uno solo: sin esto, la fila unida
    # diría "Falta en Defontana" aunque Defontana sí lo tenga, con el otro
    # código.
    principal.en_qms = any(i.en_qms for i in ordenados)
    principal.en_defontana = any(i.en_defontana for i in ordenados)

    contadas = [i.cantidad_fisica for i in ordenados if i.cantidad_fisica is not None]
    principal.cantidad_fisica = sum(contadas) if contadas else None
    contador = next((i for i in ordenados if i.cantidad_fisica is not None), None)
    if contador is not None:
        principal.contado_por_id = contador.contado_por_id
        principal.contado_por_texto = contador.contado_por_texto
        principal.contado_en = contador.contado_en

    for campo in ("nombre", "linea_negocio", "ubicacion", "categoria", "unidad_qms",
                  "unidad_defontana", "costo_unitario_qms", "costo_unitario_defontana"):
        if getattr(principal, campo) in (None, ""):
            setattr(principal, campo, _primero(getattr(i, campo) for i in ordenados))

    for item in resto:
        _registrar_unificacion(principal.empresa_id, principal.codigo, item.codigo, usuario_id)
        db.session.delete(item)
    return principal





# "Totales", "Total general", "Totales (3180)": la fila de cierre que varios
# informes ponen al final, con la suma de toda la columna. No es un artículo:
# cargarla dejaría un conteo de 83.807 unidades sobre un código inventado.
ES_FILA_TOTAL = re.compile(r"^total(es)?\b", re.IGNORECASE)


# La exportación de Stock y conteo escribe la fecha así, en hora de Chile. Los
# otros formatos son los que sale escribiendo a mano quien llena la planilla.
FORMATOS_FECHA_CONTEO = (
    "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
)


def _a_fecha_de_conteo(valor):
    """La fecha del conteo, en UTC. None si la celda viene vacía.

    La planilla la llena gente en Chile y la exportación sale en hora local
    ("13-10-2026 10:30"), pero en la base las fechas se guardan en UTC. Sin
    convertir, cada conteo quedaría corrido tres o cuatro horas según la época
    del año, y en el borde del día cambiaría de fecha.

    Levanta ValueError si hay algo escrito que no se entiende: adivinar una
    fecha es peor que informar la fila.
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        fecha = valor
    elif isinstance(valor, date):  # una celda con fecha pero sin hora
        fecha = datetime(valor.year, valor.month, valor.day)
    else:
        texto = str(valor).strip()
        if not texto:
            return None
        for formato in FORMATOS_FECHA_CONTEO:
            try:
                fecha = datetime.strptime(texto, formato)
                break
            except ValueError:
                continue
        else:
            raise ValueError(texto)
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=ZONA_LOCAL)
    return fecha.astimezone(timezone.utc)


def _clave_de_persona(texto) -> str:
    """El nombre como para compararlo: sin tildes, sin espacios de más, en minúsculas.

    Quien llena la planilla escribe "Juan Pérez", "JUAN PEREZ" o "Juan  Perez",
    y las tres son la misma persona.
    """
    if not texto:
        return ""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn"
    )
    return _ESPACIOS_RE.sub(" ", sin_tildes).strip().lower()


def _personas_de_la_empresa(empresa_id: int) -> dict:
    """Nombre escrito -> id de usuario, para reconocer a quién contó.

    Se aceptan las tres formas en que una persona aparece nombrada en el
    sistema: su nombre completo (que es lo que sale en la exportación), su
    nombre de usuario y su correo.
    """
    from app.models.usuario import Usuario

    mapa = {}
    for usuario in Usuario.query.filter_by(empresa_id=empresa_id).all():
        for escrito in (usuario.nombre_completo, usuario.nombre_usuario, usuario.email):
            clave = _clave_de_persona(escrito)
            if clave:
                mapa.setdefault(clave, usuario.id)
    return mapa


def _columna_de_cantidad(encabezados, excluir):
    """La columna con lo contado, sin confundirla con "Contado por".

    "contado" es palabra de las dos, y la exportación de Stock y conteo trae
    ambas. Si "Contado por" se tomara como la cantidad, el conteo entero se
    cargaría leyendo nombres de personas.
    """
    candidatos = [c for c in encabezados or [] if c not in excluir]
    for palabra in ("físico", "fisico", "contado", "cantidad", "stock"):
        columna = _buscar_columna(candidatos, palabra)
        if columna:
            return columna
    return None


def leer_conteo_fisico(file_storage) -> tuple:
    """Lee el archivo de conteo físico: devuelve (filas, problemas).

    Cada fila es un dict con código, cantidad, quién contó y cuándo. 'problemas'
    junta lo que no se pudo leer, para decirlo al final en vez de descartarlo en
    silencio.

    Las columnas de quién y cuándo son opcionales: si no vienen, el conteo queda
    a nombre de quien sube el archivo y con la hora de la importación. Si vienen
    —y vienen, porque la exportación de Stock y conteo las trae— mandan ellas:
    el conteo lo hizo bodega, no quien lo sube, y lo hizo otro día.

    Se aceptan decimales: hay artículos que se cuentan en metros, kilos o
    litros. Un punto con tres dígitos detrás —"3.125"— no se adivina: en Chile
    es separador de miles tanto como decimal, y elegir mal guarda mil veces la
    cantidad real. Escribiéndolo a mano la pantalla pregunta; acá no hay a
    quién preguntar, así que esa fila se informa y no se carga.
    """
    encabezados, reader = _leer_filas(file_storage)
    columna_codigo = (
        _buscar_columna(encabezados, "código") or _buscar_columna(encabezados, "codigo")
        or _buscar_columna(encabezados, "artículo") or _buscar_columna(encabezados, "articulo")
    )
    columna_quien = _buscar_columna(encabezados, "contado", "por")
    columna_fecha = (
        _buscar_columna(encabezados, "fecha", "conteo") or _buscar_columna(encabezados, "fecha")
    )
    columna_cantidad = _columna_de_cantidad(encabezados, {columna_codigo, columna_quien, columna_fecha})
    if not columna_codigo or not columna_cantidad:
        raise ValueError(
            "No encontré las columnas del conteo. Hace falta una de código "
            "(“Código”, “Artículo”) y una de cantidad (“Stock físico”, “Contado”, “Cantidad”)."
        )

    filas = []
    problemas = {"ambiguos": [], "sin_numero": [], "negativos": [], "vacias": 0, "fechas_malas": []}
    for fila in reader:
        codigo = _normalizar_codigo(fila.get(columna_codigo) or "")
        if not codigo or ES_FILA_TOTAL.match(codigo):
            continue
        crudo = fila.get(columna_cantidad)
        texto = "" if crudo is None else str(crudo).strip()
        # Una celda vacía no borra el conteo que ya había: el archivo puede
        # traer todo el maestro y sólo algunas filas contadas.
        if texto == "":
            problemas["vacias"] += 1
            continue
        if punto_ambiguo(texto):
            problemas["ambiguos"].append(f"{codigo} ({texto})")
            continue
        cantidad = a_cantidad(crudo)
        if cantidad is None:
            problemas["sin_numero"].append(f"{codigo} ({texto})")
            continue
        if cantidad < 0:
            problemas["negativos"].append(f"{codigo} ({texto})")
            continue
        # Una fecha que no se entiende no bota la fila: la cantidad es el dato
        # que importa y ya se leyó bien. Se informa y esa fila queda con la hora
        # de la importación.
        try:
            cuando = _a_fecha_de_conteo(fila.get(columna_fecha)) if columna_fecha else None
        except ValueError as e:
            problemas["fechas_malas"].append(f"{codigo} ({e})")
            cuando = None
        quien = _ESPACIOS_RE.sub(" ", str(fila.get(columna_quien) or "")).strip() if columna_quien else ""
        filas.append({"codigo": codigo, "cantidad": cantidad, "quien": quien, "cuando": cuando})
    return filas, problemas


def _mismo_conteo(item, cantidad, por_id, por_texto, cuando) -> bool:
    """Si la fila no cambiaría nada de lo ya registrado.

    Importa para el resumen: volver a subir el mismo archivo tiene que decir
    que no cambió nada, no que se actualizaron tres mil artículos. Con ese
    número ella revisa lo que se movió, y si lo dice todo no sirve de nada.

    La fecha se compara con un minuto de tolerancia porque la exportación la
    escribe sin segundos: al volver a subirla, el segundo que se perdió haría
    aparecer como cambio cada una de las filas.
    """
    if item.cantidad_fisica is None or item.cantidad_fisica != cantidad:
        return False
    if item.contado_por_id != por_id or (item.contado_por_texto or "") != (por_texto or ""):
        return False
    if cuando is None:  # el archivo no dice cuándo: no hay con qué contradecir lo guardado
        return True
    if item.contado_en is None:
        return False
    guardado = item.contado_en
    if guardado.tzinfo is None:  # la base devuelve la fecha sin zona, guardada en UTC
        guardado = guardado.replace(tzinfo=timezone.utc)
    return abs((guardado - cuando).total_seconds()) < 60


def importar_conteo_fisico(file_storage, empresa_id: int, usuario_id=None) -> dict:
    """Carga el conteo físico desde un archivo. No toca nada más.

    Escribe sólo cantidad_fisica, contado_por_id y contado_en: ni las
    cantidades de los sistemas, ni el costo, ni la unidad, ni el nombre. Es
    escribir la cantidad en la fila de Stock y conteo, de a muchas.

    El conteo que ya había se reemplaza: subir "el conteo actualizado" y que
    las correcciones no entren sería lo contrario de lo que se pidió. Se
    informa cuántos cambiaron para poder revisarlo.

    Un código que no está en el maestro se informa y no se carga: el maestro se
    arma con las planillas de QMS y Defontana, no con el conteo.
    """
    filas, problemas = leer_conteo_fisico(file_storage)

    items = _items_de_la_empresa(empresa_id)
    existentes = _por_codigo_normalizado(items)
    # Un código que alguien retiró al unificar sigue viniendo en las planillas
    # de bodega: hay que mandarlo al artículo que quedó, igual que hacen los
    # otros importadores.
    redirigidos = _redirecciones_de_unificaciones(empresa_id)
    personas = _personas_de_la_empresa(empresa_id)

    ahora = datetime.now(timezone.utc)
    cambios, sin_codigo, iguales = [], [], 0
    # Cuántos venían contados de antes con otra cantidad. Si la toma anterior se
    # finalizó primero, esto es 0 y el archivo entra sobre un conteo en blanco;
    # si no es 0, la captura se está mezclando con una toma a medio hacer y hay
    # que poder verlo.
    pisados = 0
    # Nombres de la columna "Contado por" que no son usuarios del sistema. Se
    # guardan igual como texto —son el único registro de quién contó— pero se
    # informan, porque muchas veces es un nombre escrito distinto.
    sin_usuario = []
    vistos = set()
    for fila in filas:
        clave = codigo_normalizado(fila["codigo"])
        item = existentes.get(redirigidos.get(clave, clave))
        if item is None:
            sin_codigo.append(fila["codigo"])
            continue
        # El mismo código dos veces en el archivo: manda la última fila, que es
        # lo mismo que pasaría escribiéndolo dos veces en la pantalla.
        vistos.add(item.id)

        # Si el archivo no trae quién contó, queda a nombre de quien lo sube.
        if fila["quien"]:
            encontrado = personas.get(_clave_de_persona(fila["quien"]))
            por_id = encontrado
            por_texto = None if encontrado else fila["quien"]
            if not encontrado and fila["quien"] not in sin_usuario:
                sin_usuario.append(fila["quien"])
        else:
            por_id, por_texto = usuario_id, None

        if _mismo_conteo(item, fila["cantidad"], por_id, por_texto, fila["cuando"]):
            iguales += 1
            continue
        if item.cantidad_fisica is not None and item.cantidad_fisica != fila["cantidad"]:
            pisados += 1
        cambios.append({"id": item.id, "cantidad_fisica": fila["cantidad"],
                        "contado_por_id": por_id, "contado_por_texto": por_texto,
                        "contado_en": fila["cuando"] or ahora})

    _aplicar_en_lote(cambios)
    db.session.commit()
    return {
        "total_filas": len(filas),
        "actualizados": len(cambios),
        "sin_cambio": iguales,
        "pisados": pisados,
        "sin_codigo": sin_codigo,
        "sin_usuario": sin_usuario,
        "articulos": len(vistos),
        **problemas,
    }
