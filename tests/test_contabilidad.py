"""Submódulo Contabilidad > Provisión de Ingresos: importar acumulando y editar 4 columnas."""

import io
import re
import pytest
from datetime import date
from pathlib import Path

from openpyxl import Workbook

from app.extensions import db as _db
from app.models.contabilidad import ProvisionIngreso, ReversaProvision
from app.utils.provision_ingresos_excel import PlanillaInvalida, leer_provisiones, mes_legible
from tests.conftest import login

TITULOS = [
    "Mes.año", "Cbte Prov", "OT", "Monto Provisión", "Reversa", "Mes Reversa",
    "Cbte Reversa", "Cliente", "Centro de Costos", "Rut", "Obs", "Saldo",
]


def _planilla(filas, hoja="Control"):
    """Arma un xlsx en memoria con la forma de la planilla real: totales, títulos y datos."""
    libro = Workbook()
    ws = libro.active
    ws.title = hoja
    ws.append([None, None, None, 0, 0, None, None, None, None, None, None, 0])  # fila de totales
    ws.append(TITULOS)
    for fila in filas:
        ws.append(fila)
    memoria = io.BytesIO()
    libro.save(memoria)
    memoria.seek(0)
    return memoria


FILA_1 = [date(2026, 3, 1), 67, 6095, 3700000, 3700000, date(2026, 5, 1), 109,
          "CIA MINERA COLLAHUASI", "EMPNEGVTAVTAPRE", "89468900-5", None, 0]
FILA_2 = [date(2026, 3, 1), 67, 6119, 91035000, None, None, None,
          "MINERA LOS PELAMBRES", "EMPNEGVTAVTAOEM", "96790240-3", None, 91035000]
FILA_3 = [date(2026, 4, 1), 114, 6136, 290000, None, None, None,
          "CONTITECH CHILE S.A.", "EMPNEGVTAVTAOEM", "83070800-6", None, 290000]


# --- Lectura de la planilla ---------------------------------------------


def test_lee_las_lineas_de_la_hoja_control():
    lineas = leer_provisiones(_planilla([FILA_1, FILA_2]))
    assert len(lineas) == 2
    assert lineas[0]["cbte_prov"] == "67"
    assert lineas[0]["ot"] == "6095"
    assert lineas[0]["monto_provision"] == 3_700_000
    assert lineas[0]["mes_reversa"] == "05.2026"
    assert lineas[1]["reversa"] is None
    assert lineas[1]["saldo"] == 91_035_000


def test_el_mes_de_reversa_admite_texto_libre():
    """En la planilla real hay una línea reversada en dos meses: 'may-26 y jun-26'."""
    fila = list(FILA_1)
    fila[5] = "may-26 y jun-26"
    fila[6] = "456-204"
    lineas = leer_provisiones(_planilla([fila]))
    assert lineas[0]["mes_reversa"] == "may-26 y jun-26"
    assert lineas[0]["cbte_reversa"] == "456-204"


def test_se_ignoran_las_filas_sin_los_datos_que_identifican_la_linea():
    lineas = leer_provisiones(_planilla([FILA_1, [None, None, None, 999, None, None, None, None, None, None, None, 0]]))
    assert len(lineas) == 1


def test_un_archivo_sin_la_hoja_control_avisa_en_vez_de_reventar():
    try:
        leer_provisiones(_planilla([FILA_1], hoja="Otra"))
        assert False, "debería haber avisado que falta la hoja Control"
    except PlanillaInvalida as error:
        assert "Control" in str(error)


def test_mes_legible():
    assert mes_legible(date(2026, 5, 1)) == "may-26"
    assert mes_legible(None) == ""


# --- Permisos ------------------------------------------------------------


def test_bodega_no_puede_ver_contabilidad(client, usuario_bodega):
    login(client, "bodega@test.cl")
    assert client.get("/contabilidad/provision-ingresos").status_code == 403


# --- Importar acumulando -------------------------------------------------


def test_importar_carga_las_lineas_de_la_planilla(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    respuesta = client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1, FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert ProvisionIngreso.query.filter_by(empresa_id=empresa.id).count() == 2


def test_reimportar_no_duplica_ni_borra_lo_anterior(client, usuario_admin, empresa, db):
    """Lo pedido: cada importación agrega lo nuevo y deja lo que ya estaba."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1, FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    # La segunda planilla repite las dos anteriores y trae una tercera.
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1, FILA_2, FILA_3]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    lineas = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).all()
    assert len(lineas) == 3
    assert {l.ot for l in lineas} == {"6095", "6119", "6136"}


def test_reimportar_actualiza_las_lineas_con_lo_que_trae_la_planilla(client, usuario_admin, empresa, db):
    """La planilla es la fuente de sus propias columnas: al reimportar, lo que
    se haya editado a mano en ellas se reemplaza."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    linea.cliente = "ESCRITO A MANO"
    linea.monto_provision = 1
    _db.session.commit()

    client.post(  # el mismo Excel
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    _db.session.refresh(linea)
    assert linea.cliente == "MINERA LOS PELAMBRES"   # quedó como en la planilla
    assert linea.monto_provision == 91_035_000
    assert linea.saldo == 91_035_000                 # y el saldo se recalculó
    assert ProvisionIngreso.query.count() == 1       # sin duplicar


def test_reimportar_no_borra_las_reversas_cargadas_a_mano(client, usuario_admin, empresa, db):
    """En la planilla cabe una sola reversa por línea; acá pueden ser varias.
    Dejarla mandar aplastaría ese detalle en cada importación."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    _reversar(client, linea, 40_000_000, mes="202605", comprobante="456")
    _reversar(client, linea, 11_035_000, mes="202606", comprobante="789")

    reversada = list(FILA_2)      # la planilla trae otra reversa, de una sola vez
    reversada[4] = 91_035_000
    reversada[5] = date(2026, 7, 1)
    reversada[11] = 0
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([reversada]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    _db.session.refresh(linea)
    assert len(linea.reversas) == 2                  # las dos siguen ahí
    assert linea.reversado == 51_035_000             # y el total es el de ellas
    assert linea.saldo == 91_035_000 - 51_035_000
    assert "202607" not in [r.mes for r in linea.reversas]


def test_la_reversa_de_la_planilla_estrena_el_historial_de_la_linea(client, usuario_admin, empresa, db):
    """En una línea que no existía no hay historial que proteger, así que la
    reversa que trae la planilla pasa a ser la primera de la línea."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1]), "provision.xlsx")},   # reversada en 05.2026
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.one()

    assert len(linea.reversas) == 1
    assert linea.reversas[0].monto == 3_700_000
    assert linea.reversas[0].comprobante == "109"
    # El mes queda normalizado, como el que se carga a mano: en la planilla
    # viene "05.2026" y la pantalla lo muestra como may-26.
    assert linea.reversas[0].mes == "202605"
    assert ">may-26<" in client.get("/contabilidad/provision-ingresos?estado=todas").get_data(as_text=True)


def test_importar_un_archivo_que_no_es_la_planilla_avisa(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    respuesta = client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1], hoja="Hoja1"), "otra.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert "Control" in respuesta.get_data(as_text=True)
    assert ProvisionIngreso.query.count() == 0


# --- Edición de las 4 columnas ------------------------------------------



def _reversar(client, linea, monto, mes="202606", comprobante="456", nota=None):
    """Agrega una reversa como lo hace la pantalla: una a una, no reemplazando."""
    datos = {"monto": str(monto), "mes": mes, "comprobante": comprobante}
    if nota:
        datos["nota"] = nota
    return client.post(
        f"/contabilidad/provision-ingresos/{linea.id}/reversa",
        data=datos, follow_redirects=True,
    )

def test_guardar_no_toca_lo_que_viene_del_excel(client, usuario_admin, empresa, db):
    """La reversa salió de la fila editable: ahora se agrega aparte. Lo que
    sigue sin poder cambiarse ahí es lo que trae la planilla."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()

    client.post(
        "/contabilidad/provision-ingresos/guardar",
        data={
            f"linea-{linea.id}-cbte_prov": linea.cbte_prov,
            f"linea-{linea.id}-ot": linea.ot,
            # Estos no son editables: aunque se envíen, deben ignorarse.
            f"linea-{linea.id}-monto_provision": "1",
            f"linea-{linea.id}-cliente": "OTRO CLIENTE",
        },
        follow_redirects=True,
    )
    _db.session.refresh(linea)
    assert linea.monto_provision == 91_035_000  # intacto
    assert linea.cliente == "MINERA LOS PELAMBRES"  # intacto


def test_las_reversas_se_suman_en_vez_de_reemplazarse(client, usuario_admin, empresa, db):
    """Es el cambio de fondo: una provisión se reversa a veces en partes, en
    meses distintos. Antes cabía una sola y la segunda borraba la primera."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()

    _reversar(client, linea, 40_000_000, mes="202605", comprobante="456")
    _reversar(client, linea, 51_035_000, mes="202606", comprobante="789")

    _db.session.refresh(linea)
    assert len(linea.reversas) == 2
    assert linea.reversado == 91_035_000
    assert linea.saldo == 0
    assert [r.mes for r in linea.reversas] == ["202605", "202606"]
    assert [r.comprobante for r in linea.reversas] == ["456", "789"]


def test_cada_reversa_puede_llevar_su_nota(client, usuario_admin, empresa, db):
    """El respaldo de por qué ese monto quedó así: en una planilla eso se
    discute de memoria."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()

    _reversar(client, linea, 1_000_000, nota="Vino mal de contabilidad, se corrige en julio")

    _db.session.refresh(linea)
    assert linea.reversas[0].nota == "Vino mal de contabilidad, se corrige en julio"
    texto = client.get("/contabilidad/provision-ingresos").get_data(as_text=True)
    assert "Vino mal de contabilidad" in texto


def test_el_admin_puede_borrar_una_reversa_y_el_saldo_vuelve(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    _reversar(client, linea, 40_000_000)
    _db.session.refresh(linea)
    reversa_id = linea.reversas[0].id

    client.post(f"/contabilidad/provision-ingresos/reversa/{reversa_id}/eliminar",
                follow_redirects=True)

    _db.session.refresh(linea)
    assert linea.reversas == []
    assert linea.saldo == 91_035_000   # vuelve a quedar toda la provisión pendiente


def test_reversar_de_mas_no_se_impide_pero_se_avisa(client, usuario_admin, empresa, db):
    """Puede ser un monto mal tecleado que se corrige con la reversa siguiente.
    Lo que no puede es pasar callado: que una planilla no avise es justamente
    lo que hace que el error llegue lejos."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()

    texto = _reversar(client, linea, 100_000_000).get_data(as_text=True)

    _db.session.refresh(linea)
    assert linea.reversado == 100_000_000
    assert linea.reversado_de_mas == 8_965_000
    assert "POR SOBRE lo provisionado" in texto


def test_el_mes_se_guarda_normalizado(client, usuario_admin, empresa, db):
    """Se escribe de muchas formas y todas son el mismo mes. Sin normalizar, la
    vista por mes abriría una columna por cada forma de escribirlo."""
    from app.contabilidad.routes import mes_normalizado

    assert mes_normalizado("09.2026") == "202609"
    assert mes_normalizado("2026-09") == "202609"
    assert mes_normalizado("9/2026") == "202609"
    assert mes_normalizado("202609") == "202609"
    # Lo que no se entiende se guarda tal cual: mejor una columna rara que
    # perder el dato.
    assert mes_normalizado("may-26 y jun-26") == "may-26 y jun-26"


def test_el_mes_se_entiende_escrito_con_letras(client):
    """Es como viene en la planilla de la que salió esto: "may-26". Sin
    entenderlo, la vista por mes abriría una columna "may-26" al lado de la de
    mayo 2026, que es el mismo mes."""
    from app.contabilidad.routes import mes_normalizado

    assert mes_normalizado("may-26") == "202605"
    assert mes_normalizado("may 2026") == "202605"
    assert mes_normalizado("mayo-2026") == "202605"
    assert mes_normalizado("Septiembre 2026") == "202609"
    assert mes_normalizado("sept-26") == "202609"
    # Y un mes que no existe no se inventa: se guarda tal cual.
    assert mes_normalizado("2026-13") == "2026-13"
    assert mes_normalizado("xyz-26") == "xyz-26"


def test_el_mes_se_muestra_como_en_la_planilla(client):
    """Guardado se ordena como 202605, pero nadie lee los meses así."""
    from app.contabilidad.routes import mes_reversa_legible

    assert mes_reversa_legible("202605") == "may-26"
    assert mes_reversa_legible("202612") == "dic-26"
    assert mes_reversa_legible("") == ""
    assert mes_reversa_legible(None) == ""
    # Lo que no es un mes no se disfraza de uno.
    assert mes_reversa_legible("may-26 y jun-26") == "may-26 y jun-26"
    assert mes_reversa_legible("202613") == "202613"


# --- Filtrar por mes de reversa ------------------------------------------


def _dos_reversadas_en_meses_distintos(client, empresa):
    """Dos líneas, reversadas una en mayo y la otra en junio."""
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2, FILA_3]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    pelambres = ProvisionIngreso.query.filter_by(ot="6119").one()
    contitech = ProvisionIngreso.query.filter_by(ot="6136").one()
    _reversar(client, pelambres, 1_000_000, mes="202605", comprobante="456")
    _reversar(client, contitech, 290_000, mes="202606", comprobante="789")
    return pelambres, contitech


def _opciones_del_filtro(texto, nombre):
    """Las opciones (valor, etiqueta) del desplegable de ese filtro, en orden."""
    select = texto.split(f'name="{nombre}"', 1)[1].split("</select>", 1)[0]
    return [
        (m.group(1), m.group(2).strip())
        for m in re.finditer(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', select)
    ]


def test_se_puede_filtrar_por_mes_de_reversa(client, usuario_admin, empresa, db):
    """La provisión se hace un mes y se reversa otro: son dos filtros, no uno."""
    login(client, "admin@test.cl")
    _dos_reversadas_en_meses_distintos(client, empresa)

    mayo = client.get("/contabilidad/provision-ingresos?mes_reversa=202605").get_data(as_text=True)
    assert "PELAMBRES" in mayo
    assert "CONTITECH" not in mayo

    junio = client.get("/contabilidad/provision-ingresos?mes_reversa=202606").get_data(as_text=True)
    assert "CONTITECH" in junio
    assert "PELAMBRES" not in junio


def test_el_filtro_de_mes_de_reversa_no_depende_de_como_este_escrito(client, usuario_admin, empresa, db):
    """Lo cargado antes de este cambio trae "05.2026" y lo nuevo "202605": son
    el mismo mes, y el filtro tiene que encontrar las dos."""
    login(client, "admin@test.cl")
    pelambres, _ = _dos_reversadas_en_meses_distintos(client, empresa)
    pelambres.reversas[0].mes = "05.2026"   # como quedó lo importado de la planilla
    _db.session.commit()

    mayo = client.get("/contabilidad/provision-ingresos?mes_reversa=202605").get_data(as_text=True)
    assert "PELAMBRES" in mayo


def test_el_desplegable_ofrece_los_meses_que_existen_una_sola_vez(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    pelambres, _ = _dos_reversadas_en_meses_distintos(client, empresa)
    # Otra reversa del mismo mes, escrita como la dejó la planilla. Se guarda
    # tal cual a propósito: es lo que trae lo cargado antes de este cambio, y
    # el formulario normaliza al escribir, así que por ahí no se puede probar.
    pelambres.reversas.append(ReversaProvision(monto=1, mes="05.2026"))
    _db.session.commit()

    texto = client.get("/contabilidad/provision-ingresos?estado=todas").get_data(as_text=True)

    opciones = _opciones_del_filtro(texto, "mes_reversa")
    # Dos meses, no tres: la forma vieja y la nueva del mismo mes son una sola
    # opción. Si no, el filtro ofrecería "05.2026" aparte de "may-26" y cada
    # una mostraría la mitad de las líneas.
    assert opciones == [("", "Todos"), ("202606", "jun-26"), ("202605", "may-26")]


def test_filtrar_por_mes_de_reversa_muestra_tambien_las_cerradas(client, usuario_admin, empresa, db):
    """Buscar por mes de reversa es ir a ver algo ya reversado, y lo reversado
    por completo está cerrado: con el filtro de siempre la pantalla saldría
    vacía y parecería que ese mes no tiene nada."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.one()
    _reversar(client, linea, 91_035_000, mes="202605")   # queda cerrada
    assert linea.saldo == 0

    texto = client.get("/contabilidad/provision-ingresos?mes_reversa=202605").get_data(as_text=True)
    assert "PELAMBRES" in texto

    # Pero si pide expresamente las pendientes, se respeta lo que pidió.
    pendientes = client.get(
        "/contabilidad/provision-ingresos?mes_reversa=202605&estado=pendiente"
    ).get_data(as_text=True)
    assert "PELAMBRES" not in pendientes


def test_el_excel_tambien_respeta_el_filtro_de_mes_de_reversa(client, usuario_admin, empresa, db):
    """Si la pantalla muestra un mes, el Excel que se baja al lado tiene que
    traer lo mismo: bajarse todo cuando se está mirando un mes es un error que
    no se nota hasta que alguien suma la columna."""
    from openpyxl import load_workbook

    login(client, "admin@test.cl")
    _dos_reversadas_en_meses_distintos(client, empresa)

    respuesta = client.get("/contabilidad/provision-ingresos/exportar.xlsx?mes_reversa=202605")
    hoja = load_workbook(io.BytesIO(respuesta.data)).active
    texto = "\n".join(
        str(c.value) for fila in hoja.iter_rows() for c in fila if c.value is not None
    )
    assert "PELAMBRES" in texto
    assert "CONTITECH" not in texto


def test_el_excel_trae_el_detalle_de_cada_reversa(client, usuario_admin, empresa, db):
    """El Excel tiene una fila por provisión, así que el detalle va en una
    celda: sin esto, bajarse la planilla dejaría sólo el total y volvería al
    problema de no saber qué se reversó cuándo."""
    from openpyxl import load_workbook

    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.one()
    _reversar(client, linea, 40_000_000, mes="202605", comprobante="456")
    _reversar(client, linea, 11_035_000, mes="202606", comprobante="789", nota="Vino mal")

    respuesta = client.get("/contabilidad/provision-ingresos/exportar.xlsx")
    hoja = load_workbook(io.BytesIO(respuesta.data)).active
    celdas = [str(c.value) for fila in hoja.iter_rows() for c in fila if c.value is not None]
    texto = "\n".join(celdas)

    assert "Detalle de reversas" in texto
    assert "may-26 $40.000.000 cbte 456" in texto
    assert "jun-26 $11.035.000 cbte 789 (Vino mal)" in texto
    assert "may-26 y jun-26" in texto      # la columna de meses, como se escribía antes
    assert "51035000" in celdas            # el total reversado, no la última reversa


# --- Las reversas vistas por mes, como la planilla de contabilidad -------


def test_la_vista_por_mes_pone_una_columna_por_mes(client, usuario_admin, empresa, db):
    """Lo que pidió: cada provisión en una fila, cada mes de reversa en una
    columna, y el monto en la celda que cruza las dos."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.one()
    _reversar(client, linea, 40_000_000, mes="202605", comprobante="456")
    _reversar(client, linea, 11_035_000, mes="202606", comprobante="789")

    texto = client.get("/contabilidad/provision-ingresos/por-mes?estado=todas").get_data(as_text=True)

    assert '<th class="num">may-26</th>' in texto
    assert '<th class="num">jun-26</th>' in texto
    assert "$40.000.000" in texto
    assert "$11.035.000" in texto
    assert "PELAMBRES" in texto
    # El comprobante contable va como burbuja en la casilla, no en una columna.
    assert ">456<" in texto and ">789<" in texto


#: Antes de la primera columna de mes van mes, comprobante, OT, cliente y
#: monto provisionado. Contarlas es lo que permite saber en qué columna cayó
#: cada monto.
COLUMNAS_ANTES_DE_LOS_MESES = 5


def _celdas_de_los_meses(texto, ot):
    """Las celdas de mes de la fila de esa OT, en el orden en que se muestran."""
    cuerpo = texto[texto.index("<tbody>"):texto.index("</tbody>")]
    fila = next(f for f in cuerpo.split("<tr>") if f">{ot}<" in f)
    return fila.split("<td")[1:][COLUMNAS_ANTES_DE_LOS_MESES:]


def test_en_la_vista_por_mes_cada_monto_cae_en_su_mes(client, usuario_admin, empresa, db):
    """Es lo único que esta pantalla tiene que hacer bien: si los montos se
    corren de columna, la pantalla miente y no se nota."""
    login(client, "admin@test.cl")
    _dos_reversadas_en_meses_distintos(client, empresa)

    texto = client.get("/contabilidad/provision-ingresos/por-mes?estado=todas").get_data(as_text=True)

    # Las columnas van en orden: mayo primero, junio después. Se mira el
    # encabezado de la tabla y no la página entera, porque el desplegable del
    # filtro trae los mismos meses en el orden inverso.
    encabezado = texto[texto.index("<thead>"):texto.index("</thead>")]
    assert encabezado.index(">may-26<") < encabezado.index(">jun-26<")

    # La reversa de PELAMBRES es de mayo: su monto va en la columna de mayo y
    # la de junio queda vacía. En CONTITECH, al revés.
    mayo, junio = _celdas_de_los_meses(texto, "6119")[:2]
    assert "$1.000.000" in mayo and "$1.000.000" not in junio
    mayo, junio = _celdas_de_los_meses(texto, "6136")[:2]
    assert "$290.000" not in mayo and "$290.000" in junio


def test_la_vista_por_mes_junta_los_meses_escritos_distinto(client, usuario_admin, empresa, db):
    """Agrupar por el texto guardado abriría dos columnas para el mismo mes:
    lo viejo trae "05.2026" y lo nuevo "202605"."""
    login(client, "admin@test.cl")
    pelambres, _ = _dos_reversadas_en_meses_distintos(client, empresa)
    # Escrito como lo dejó la planilla, guardado tal cual: el formulario
    # normaliza al escribir, así que esta forma sólo llega por la migración de
    # lo que ya estaba cargado, y es justo la que tiene que juntarse.
    pelambres.reversas.append(ReversaProvision(monto=500_000, mes="05.2026", comprobante="457"))
    _db.session.commit()

    texto = client.get("/contabilidad/provision-ingresos/por-mes?estado=todas").get_data(as_text=True)

    assert texto.count('<th class="num">may-26</th>') == 1
    assert "$1.500.000" in texto      # los dos montos de mayo, sumados en la casilla
    assert "05.2026" not in texto


def test_la_vista_por_mes_suma_cada_columna(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    _dos_reversadas_en_meses_distintos(client, empresa)

    texto = client.get("/contabilidad/provision-ingresos/por-mes?estado=todas").get_data(as_text=True)
    pie = texto[texto.index("<tfoot>"):]

    assert "$1.000.000" in pie        # total de mayo
    assert "$290.000" in pie          # total de junio
    assert "$91.325.000" in pie       # provisión total de las dos líneas


def test_la_vista_por_mes_no_pierde_las_reversas_sin_mes(client, usuario_admin, empresa, db):
    """Sin mes no caben en ninguna columna, y dejarlas fuera haría que el total
    de la fila no cuadre con el del listado."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.one()
    _reversar(client, linea, 2_000_000, mes="", comprobante="456")

    texto = client.get("/contabilidad/provision-ingresos/por-mes?estado=todas").get_data(as_text=True)

    assert "Sin mes" in texto
    assert "$2.000.000" in texto


def test_la_nota_se_puede_leer_en_la_casilla(client, usuario_admin, empresa, db):
    """Es el respaldo cuando lo que llegó de contabilidad viene equivocado."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.one()
    _reversar(client, linea, 1_000_000, mes="202605", nota="Mi jefe la puso en mayo, va en junio")

    texto = client.get("/contabilidad/provision-ingresos/por-mes?estado=todas").get_data(as_text=True)

    assert "Mi jefe la puso en mayo, va en junio" in texto


def test_la_vista_por_mes_se_llega_desde_el_listado(client, usuario_admin, empresa, db):
    """Si no hay cómo llegar, la pantalla no existe."""
    login(client, "admin@test.cl")
    texto = client.get("/contabilidad/provision-ingresos").get_data(as_text=True)

    assert "/contabilidad/provision-ingresos/por-mes" in texto
    assert "Ver reversas por mes" in texto


def test_la_vista_por_mes_sin_reversas_no_revienta(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    respuesta = client.get("/contabilidad/provision-ingresos/por-mes?estado=todas")

    assert respuesta.status_code == 200
    assert "Todavía no hay reversas cargadas" in respuesta.get_data(as_text=True)


def test_bodega_no_puede_ver_las_reversas_por_mes(client, usuario_bodega):
    login(client, "bodega@test.cl")
    assert client.get("/contabilidad/provision-ingresos/por-mes").status_code == 403


# --- Pantalla ------------------------------------------------------------


def test_la_pantalla_muestra_las_lineas_y_los_totales(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1, FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    texto = client.get("/contabilidad/provision-ingresos?estado=todas").get_data(as_text=True)
    assert "MINERA LOS PELAMBRES" in texto
    assert "$94.735.000" in texto  # monto provisión total
    assert "$91.035.000" in texto  # saldo total
    assert "Marzo" in texto


def test_el_mes_y_el_ano_se_muestran_en_columnas_separadas(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    texto = client.get("/contabilidad/provision-ingresos?estado=todas").get_data(as_text=True)
    assert "<th>Mes</th><th>Año</th>" in texto
    assert "Marzo" in texto
    assert "2026" in texto


def test_se_puede_filtrar_por_mes_y_por_ano_por_separado(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    otro_ano = list(FILA_1)
    otro_ano[0] = date(2025, 4, 1)
    otro_ano[2] = 9999  # otra OT, para que sea una línea distinta
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1, FILA_2, FILA_3, otro_ano]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    solo_abril = client.get("/contabilidad/provision-ingresos?estado=todas&mes=4").get_data(as_text=True)
    assert "CONTITECH" in solo_abril      # abril 2026
    assert "COLLAHUASI" in solo_abril     # abril 2025, mismo mes distinto año
    assert "PELAMBRES" not in solo_abril  # marzo

    solo_2025 = client.get("/contabilidad/provision-ingresos?estado=todas&anio=2025").get_data(as_text=True)
    assert "9999" in solo_2025
    assert "CONTITECH" not in solo_2025

    abril_2026 = client.get("/contabilidad/provision-ingresos?estado=todas&mes=4&anio=2026").get_data(as_text=True)
    assert "CONTITECH" in abril_2026
    assert "9999" not in abril_2026


def test_la_linea_con_saldo_cero_aparece_como_cerrada(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1, FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    texto = client.get("/contabilidad/provision-ingresos?estado=todas").get_data(as_text=True)
    assert "Cerrado" in texto    # FILA_1 tiene saldo 0
    assert "Pendiente" in texto  # FILA_2 tiene saldo 91.035.000


def test_se_puede_filtrar_por_saldo_mayor_a_cero_y_por_cerradas(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1, FILA_2, FILA_3]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    pendientes = client.get("/contabilidad/provision-ingresos?estado=pendiente").get_data(as_text=True)
    assert "PELAMBRES" in pendientes    # saldo 91.035.000
    assert "CONTITECH" in pendientes    # saldo 290.000
    assert "COLLAHUASI" not in pendientes  # saldo 0, está cerrada

    cerradas = client.get("/contabilidad/provision-ingresos?estado=cerrado").get_data(as_text=True)
    assert "COLLAHUASI" in cerradas
    assert "PELAMBRES" not in cerradas


def test_se_puede_eliminar_una_linea(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    client.post(f"/contabilidad/provision-ingresos/{linea.id}/eliminar", follow_redirects=True)
    assert ProvisionIngreso.query.count() == 0


def test_exportar_devuelve_un_excel(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    respuesta = client.get("/contabilidad/provision-ingresos/exportar.xlsx")
    assert respuesta.status_code == 200
    assert "spreadsheetml" in respuesta.headers["Content-Type"]


def test_eliminar_una_linea_avisa_antes_y_dice_que_se_va_a_perder(client, usuario_admin, empresa, db):
    """El botón de eliminar tiene que pedir confirmación explicando qué línea es."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    texto = client.get("/contabilidad/provision-ingresos?estado=todas").get_data(as_text=True)

    assert "Se eliminar\\u00e1 esta l\\u00ednea de la provisi\\u00f3n" in texto
    assert "no se puede deshacer" in texto
    assert "COLLAHUASI" in texto           # dice de qué línea se trata
    # Y que se pierden las reversas, que son el trabajo que no vuelve con la
    # planilla: ahí cabe una sola y acá puede haber varias.
    assert "Tiene 1 reversa(s) por $3.700.000 en total, y se pierden todas" in texto


def test_el_aviso_de_borrado_no_rompe_el_atributo_aunque_el_cliente_traiga_comillas(client, usuario_admin, empresa, db):
    """El mensaje viaja dentro de un atributo HTML: si se corta, el borrado ocurriría sin preguntar."""
    login(client, "admin@test.cl")
    con_comillas = list(FILA_1)
    con_comillas[7] = 'CLIENTE "RARO" S.A.'
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([con_comillas]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    texto = client.get("/contabilidad/provision-ingresos?estado=todas").get_data(as_text=True)

    # El atributo va con comillas simples y el contenido no puede traer una comilla
    # simple sin escapar, ni una comilla doble cruda que lo corte antes de tiempo.
    inicio = texto.index("onclick='return confirm(")
    fin = texto.index("' title=\"Eliminar\"", inicio)
    atributo = texto[inicio + len("onclick='"):fin]
    assert atributo.startswith("return confirm(")
    assert atributo.endswith(")")
    assert "'" not in atributo, "una comilla simple sin escapar cortaría el atributo"


# --- Saldo calculado y línea cerrada -------------------------------------


def test_el_saldo_sale_de_restar_la_reversa_a_la_provision(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},   # provisión 91.035.000, sin reversa
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    assert linea.saldo == 91_035_000

    _reversar(client, linea, "$40.000.000")

    _db.session.refresh(linea)
    assert linea.saldo == 91_035_000 - 40_000_000  # no se escribe: se calcula


def test_al_reversar_todo_el_saldo_queda_en_cero_y_la_linea_se_cierra(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    _reversar(client, linea, 91_035_000)

    _db.session.refresh(linea)
    assert linea.saldo == 0

    texto = client.get("/contabilidad/provision-ingresos?estado=todas").get_data(as_text=True)
    assert "saldo-cerrado" in texto          # la celda va en verde
    assert "Cerrado" in texto


def test_se_cierra_recien_cuando_las_reversas_suman_la_provision(client, usuario_admin, empresa, db):
    """Lo que motivó el cambio: una reversa en partes. Con la primera la línea
    sigue abierta, y recién la última la cierra."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()

    _reversar(client, linea, 41_035_000, mes="202605", comprobante="456")
    _db.session.refresh(linea)
    assert linea.saldo == 50_000_000, "con la primera parte la línea sigue abierta"

    _reversar(client, linea, 50_000_000, mes="202606", comprobante="204")
    _db.session.refresh(linea)
    assert linea.reversado == 91_035_000
    assert linea.saldo == 0
    assert len(linea.reversas) == 2
    assert linea.meses_reversados == ["202605", "202606"]


def test_una_linea_cerrada_no_acepta_otra_reversa(client, usuario_admin, empresa, db):
    """Saldo en $0: queda con candado. Otra reversa la dejaría reversada por
    sobre lo provisionado, así que se rechaza y se dice qué hacer en su lugar."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1]), "provision.xlsx")},   # ya viene reversada, saldo 0
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    assert linea.saldo == 0
    assert linea.reversado == 3_700_000   # la reversa de la planilla, ya cargada

    texto = _reversar(client, linea, 1).get_data(as_text=True)

    _db.session.refresh(linea)
    assert linea.reversado == 3_700_000   # intacta
    assert len(linea.reversas) == 1
    assert linea.saldo == 0
    assert "ya está reversada por completo" in texto
    assert "elimínala primero" in texto


def test_una_linea_cerrada_no_cambia_de_comprobante_ni_de_ot(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    assert linea.saldo == 0

    client.post(
        "/contabilidad/provision-ingresos/guardar",
        data={f"linea-{linea.id}-cbte_prov": "PISADO", f"linea-{linea.id}-ot": "9999"},
        follow_redirects=True,
    )
    _db.session.refresh(linea)
    assert (linea.cbte_prov, linea.ot) == ("67", "6095")


def test_un_superadmin_si_puede_reversar_una_linea_cerrada(client, empresa, db):
    """Hace falta para arreglar un monto mal escrito que dejó la línea en $0."""
    from tests.test_permissions import _crear_superadmin

    _crear_superadmin(db, empresa)
    login(client, "super@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    assert linea.saldo == 0

    _reversar(client, linea, 1_000_000)

    _db.session.refresh(linea)
    assert linea.reversado == 4_700_000
    assert linea.saldo == -1_000_000


def test_la_columna_de_reversa_es_el_total_y_el_saldo_ya_no_se_escribe(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    texto = client.get("/contabilidad/provision-ingresos?estado=todas").get_data(as_text=True)

    # La columna ya no es "la" reversa: es el total de las que haya, y el
    # detalle de cada una va en la de al lado.
    assert '<th class="num">Total Reversado</th>' in texto
    assert "<th>Reversas</th>" in texto
    assert f'name="linea-{linea.id}-reversa"' not in texto  # dejó de ser una casilla de la fila
    assert f'name="linea-{linea.id}-saldo"' not in texto    # el saldo dejó de ser un campo
    assert f'id="saldo-{linea.id}"' in texto                # ahora es una celda calculada
    assert "data-confirmar-cambio" in texto                 # y avisa antes de pisar un dato


def test_las_casillas_para_agregar_no_ensanchan_la_tabla(client, usuario_admin, empresa, db):
    """Pedido explícito: la tabla no tiene que verse tan ancha. Las cuatro
    casillas para cargar una reversa son lo que más ancho pedía, y en una
    tabla de 14 columnas eso dejaba el saldo fuera de la pantalla."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    texto = client.get("/contabilidad/provision-ingresos?estado=todas").get_data(as_text=True)

    # Plegadas: el formulario existe, pero dentro de un <details> cerrado.
    assert 'class="agregar-reversa"' in texto
    assert "agregar-reversa\" open" not in texto
    assert 'name="monto"' in texto
    # Y la celda del detalle tiene ancho tope en vez de estirarse con la
    # reversa más larga.
    assert 'class="celda-reversas"' in texto
    estilos = (Path(__file__).resolve().parent.parent / "app/static/css/custom.css").read_text()
    assert "max-width" in estilos.split(".celda-reversas {", 1)[1].split("}", 1)[0]


# --- Plantilla descargable ----------------------------------------------


def test_la_plantilla_se_descarga_con_las_columnas_de_la_planilla(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    respuesta = client.get("/contabilidad/provision-ingresos/plantilla.xlsx")
    assert respuesta.status_code == 200
    assert "spreadsheetml" in respuesta.headers["Content-Type"]

    from openpyxl import load_workbook
    hoja = load_workbook(io.BytesIO(respuesta.data))["Control"]
    titulos = [c.value for c in hoja[1] if c.value]
    assert titulos == [
        "Mes", "Año", "Cbte Prov", "OT", "Monto Provisión", "Reversa", "Mes Reversa",
        "Cbte Reversa", "Cliente", "Centro de Costos", "Rut", "Obs", "Saldo",
    ]


def test_la_plantilla_descargada_se_puede_llenar_y_volver_a_subir(client, usuario_admin, empresa, db):
    """El circuito completo: bajar la plantilla, escribir en ella y cargarla."""
    login(client, "admin@test.cl")
    from openpyxl import load_workbook

    descargada = client.get("/contabilidad/provision-ingresos/plantilla.xlsx").data
    libro = load_workbook(io.BytesIO(descargada))
    hoja = libro["Control"]
    hoja.delete_rows(2)  # se borra la fila de ejemplo, como haría cualquiera
    hoja.append([7, 2026, 900, 7001, 5_000_000, None, None, None,
                 "CLIENTE DE PRUEBA", "CENTRO-1", "76000000-1", None, 5_000_000])
    memoria = io.BytesIO()
    libro.save(memoria)
    memoria.seek(0)

    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (memoria, "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    assert linea.cliente == "CLIENTE DE PRUEBA"
    assert linea.monto_provision == 5_000_000
    assert linea.saldo == 5_000_000
    assert linea.ot == "7001"


def test_se_siguen_leyendo_las_planillas_con_los_titulos_en_la_segunda_fila(client, usuario_admin, empresa, db):
    """La planilla original trae una fila de totales encima de los títulos."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1, FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert ProvisionIngreso.query.filter_by(empresa_id=empresa.id).count() == 2


def test_la_pantalla_ofrece_descargar_la_plantilla(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    texto = client.get("/contabilidad/provision-ingresos?estado=todas").get_data(as_text=True)
    assert "Descargar plantilla" in texto


# --- Mes y Año en columnas separadas ------------------------------------

TITULOS_MES_ANIO = [
    "Mes", "Año", "Cbte Prov", "OT", "Monto Provisión", "Reversa", "Mes Reversa",
    "Cbte Reversa", "Cliente", "Centro de Costos", "Rut", "Obs", "Saldo",
]


def _planilla_mes_anio(filas):
    from openpyxl import Workbook
    libro = Workbook()
    ws = libro.active
    ws.title = "Control"
    ws.append(TITULOS_MES_ANIO)
    for fila in filas:
        ws.append(fila)
    memoria = io.BytesIO()
    libro.save(memoria)
    memoria.seek(0)
    return memoria


def test_se_puede_indicar_el_periodo_con_mes_y_ano_por_separado(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla_mes_anio([
            [7, 2026, 511, 6250, 339150, None, None, None, "TTM CHILE S.A.",
             "EMPNEGVTAVTAOEM", "89026600-2", None, 339150],
        ]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    assert linea.mes_ano == date(2026, 7, 1)
    assert linea.cbte_prov == "511"
    assert linea.ot == "6250"
    assert linea.monto_provision == 339150


def test_la_plantilla_trae_mes_y_ano_separados(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    from openpyxl import load_workbook

    hoja = load_workbook(io.BytesIO(client.get("/contabilidad/provision-ingresos/plantilla.xlsx").data))["Control"]
    assert [c.value for c in hoja[1] if c.value][:4] == ["Mes", "Año", "Cbte Prov", "OT"]


def test_un_mes_fuera_de_rango_no_se_carga(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla_mes_anio([
            [13, 2026, 511, 6250, 339150, None, None, None, "TTM", "C", "1-9", None, 339150],
        ]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert ProvisionIngreso.query.count() == 0


def test_si_los_datos_no_calzan_con_los_titulos_se_avisa(client, usuario_admin, empresa, db):
    """Pasa al insertar una columna en los títulos sin correr también los datos."""
    login(client, "admin@test.cl")
    corrida = [7, 2026, None, 511, 6250, 339150, None, None, None, "TTM CHILE S.A.", "C", "1-9", None]
    respuesta = client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla_mes_anio([corrida]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)
    assert "corridos" in texto or "debajo de su" in texto
    assert ProvisionIngreso.query.count() == 0


def test_reimportar_no_borra_las_lineas_que_ya_no_vienen_en_la_planilla(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1, FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert ProvisionIngreso.query.filter_by(empresa_id=empresa.id).count() == 2

    client.post(  # una planilla con solo una de las dos
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_1]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert ProvisionIngreso.query.filter_by(empresa_id=empresa.id).count() == 2


def test_al_actualizar_desde_la_planilla_el_saldo_se_recalcula(client, usuario_admin, empresa, db):
    """El saldo no se copia de la planilla: sale de la provisión que trae menos
    lo reversado. Si la planilla corrige el monto, el saldo se mueve con él."""
    login(client, "admin@test.cl")
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    _reversar(client, linea, 40_000_000)
    assert linea.saldo == 51_035_000

    corregida = list(FILA_2)
    corregida[3] = 100_000_000           # la planilla corrige el monto provisionado
    corregida[11] = 999                  # y trae un saldo que no cuadra: se ignora
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([corregida]), "provision.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    _db.session.refresh(linea)
    assert linea.monto_provision == 100_000_000
    assert linea.saldo == 100_000_000 - 40_000_000


# --- Cargar una línea a mano, sin pasar por el Excel ---

def _datos_linea(**cambios):
    datos = {
        "mes": 6, "anio": 2026, "cbte_prov": "453", "ot": "6241",
        "monto_provision": "450000", "cliente": "TTM CHILE S.A.",
        "centro_costos": "EMPNEGVTAVTAOEM", "rut": "89026600-2", "obs": "",
    }
    datos.update(cambios)
    return datos


def test_agregar_una_linea_a_mano(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    respuesta = client.post("/contabilidad/provision-ingresos/nueva",
                            data=_datos_linea(), follow_redirects=True)
    assert respuesta.status_code == 200

    linea = ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()
    assert linea.mes_ano == date(2026, 6, 1)
    assert linea.cbte_prov == "453"
    assert linea.ot == "6241"
    assert linea.monto_provision == 450000
    assert linea.cliente == "TTM CHILE S.A."
    assert linea.saldo == 450000  # sin reversa todavía, queda pendiente entero


def test_el_monto_se_acepta_con_formato_de_pantalla(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post("/contabilidad/provision-ingresos/nueva",
                data=_datos_linea(monto_provision="$1.310.000"), follow_redirects=True)

    linea = ProvisionIngreso.query.one()
    assert linea.monto_provision == 1310000


def test_no_se_puede_repetir_periodo_comprobante_y_ot(client, usuario_admin, empresa, db):
    """La restricción de la base existe; hay que avisar antes, no reventar."""
    login(client, "admin@test.cl")
    client.post("/contabilidad/provision-ingresos/nueva", data=_datos_linea(), follow_redirects=True)
    respuesta = client.post("/contabilidad/provision-ingresos/nueva",
                            data=_datos_linea(monto_provision="999"), follow_redirects=True)

    assert respuesta.status_code == 200
    assert "Ya existe una línea" in respuesta.get_data(as_text=True)
    assert ProvisionIngreso.query.count() == 1
    assert ProvisionIngreso.query.one().monto_provision == 450000  # no se pisó


def test_la_linea_a_mano_se_puede_reversar_como_cualquier_otra(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    client.post("/contabilidad/provision-ingresos/nueva", data=_datos_linea(), follow_redirects=True)
    linea = ProvisionIngreso.query.one()

    _reversar(client, linea, 450000)

    linea = ProvisionIngreso.query.one()
    assert linea.reversado == 450000
    assert linea.saldo == 0


def test_un_monto_ilegible_no_crea_la_linea(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    respuesta = client.post("/contabilidad/provision-ingresos/nueva",
                            data=_datos_linea(monto_provision="abc"), follow_redirects=True)
    assert "no se entiende" in respuesta.get_data(as_text=True)
    assert ProvisionIngreso.query.count() == 0


def test_sin_permiso_de_edicion_no_se_puede_agregar(client, usuario_bodega, empresa, db):
    login(client, "bodega@test.cl")
    respuesta = client.post("/contabilidad/provision-ingresos/nueva", data=_datos_linea())
    assert respuesta.status_code == 403
    assert ProvisionIngreso.query.count() == 0


# --- Al entrar se muestran solo las pendientes ---

def _dos_lineas(empresa, db):
    pendiente = ProvisionIngreso(empresa_id=empresa.id, mes_ano=date(2026, 6, 1),
                                 cbte_prov="1", ot="PEND", monto_provision=500, saldo=500)
    cerrada = ProvisionIngreso(empresa_id=empresa.id, mes_ano=date(2026, 6, 1),
                               cbte_prov="2", ot="CERR", monto_provision=500, saldo=0)
    # Reversada por completo: su reversa es una fila aparte, que es de lo
    # que se trata este cambio.
    cerrada.reversas.append(ReversaProvision(monto=500, mes="202606", comprobante="456"))
    db.session.add_all([pendiente, cerrada])
    db.session.commit()


def test_al_entrar_solo_se_ven_las_pendientes(client, usuario_admin, empresa, db):
    _dos_lineas(empresa, db)
    login(client, "admin@test.cl")

    texto = client.get("/contabilidad/provision-ingresos").get_data(as_text=True)
    assert "PEND" in texto
    assert "CERR" not in texto
    assert "Mostrando" in texto  # avisa que no las está mostrando todas


def test_se_pueden_ver_todas_a_proposito(client, usuario_admin, empresa, db):
    """'Todas' tiene que seguir funcionando: por eso viaja con valor propio."""
    _dos_lineas(empresa, db)
    login(client, "admin@test.cl")

    texto = client.get("/contabilidad/provision-ingresos?estado=todas").get_data(as_text=True)
    assert "PEND" in texto
    assert "CERR" in texto


def test_el_filtro_de_cerradas_sigue_funcionando(client, usuario_admin, empresa, db):
    _dos_lineas(empresa, db)
    login(client, "admin@test.cl")

    texto = client.get("/contabilidad/provision-ingresos?estado=cerrado").get_data(as_text=True)
    assert "CERR" in texto
    assert "PEND" not in texto


def test_los_desplegables_de_mes_y_anio_no_cargan_todas_las_lineas(client, usuario_admin, empresa, db):
    """Se arman con consultas DISTINCT, no trayendo el histórico a memoria."""
    for n in range(30):
        linea = ProvisionIngreso(
            empresa_id=empresa.id, mes_ano=date(2025 if n % 2 else 2026, (n % 12) + 1, 1),
            cbte_prov=str(n), ot=f"OT{n}", monto_provision=100, saldo=0)
        linea.reversas.append(ReversaProvision(monto=100, mes="202601"))
        db.session.add(linea)
    db.session.commit()

    login(client, "admin@test.cl")
    texto = client.get("/contabilidad/provision-ingresos").get_data(as_text=True)
    # Aunque ninguna línea se muestre (todas cerradas), los filtros siguen completos
    assert "2025" in texto and "2026" in texto


# --- Cambiar el comprobante de provisión y la OT -------------------------
#
# Son parte de la llave con que se reconoce la línea al importar —mes,
# comprobante y OT—, así que cambiarlos no es editar un dato más: la línea
# deja de calzar con la de la planilla. Se puede, pero avisando.


def _guardar(client, linea, **campos):
    datos = {
        f"linea-{linea.id}-reversa": "",
        f"linea-{linea.id}-mes_reversa": "",
        f"linea-{linea.id}-cbte_reversa": "",
        f"linea-{linea.id}-cbte_prov": linea.cbte_prov,
        f"linea-{linea.id}-ot": linea.ot,
    }
    datos.update({f"linea-{linea.id}-{k}": v for k, v in campos.items()})
    return client.post(
        "/contabilidad/provision-ingresos/guardar", data=datos, follow_redirects=True
    )


def _una_linea(client, empresa, fila=FILA_2):
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([fila]), "p.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    return ProvisionIngreso.query.filter_by(empresa_id=empresa.id).one()


def test_se_puede_cambiar_la_ot(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    linea = _una_linea(client, empresa)

    _guardar(client, linea, ot="9999")

    assert ProvisionIngreso.query.one().ot == "9999"


def test_se_puede_cambiar_el_comprobante_de_provision(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    linea = _una_linea(client, empresa)

    _guardar(client, linea, cbte_prov="888")

    assert ProvisionIngreso.query.one().cbte_prov == "888"


def test_al_cambiarlos_se_avisa_que_la_planilla_ya_no_los_reconoce(
    client, usuario_admin, empresa, db
):
    """El aviso importa más que el cambio: si no, la próxima importación
    duplica la línea y nadie sabe por qué."""
    login(client, "admin@test.cl")
    linea = _una_linea(client, empresa)

    cuerpo = _guardar(client, linea, ot="9999").get_data(as_text=True)

    assert "6119" in cuerpo and "9999" in cuerpo
    assert "líneas nuevas" in cuerpo or "línea" in cuerpo
    assert "ya no las va a reconocer" in cuerpo


def test_no_se_avisa_si_no_se_cambio_nada(client, usuario_admin, empresa, db):
    login(client, "admin@test.cl")
    linea = _una_linea(client, empresa)

    cuerpo = _guardar(client, linea).get_data(as_text=True)

    assert "ya no las va a reconocer" not in cuerpo


def test_dos_lineas_del_mismo_mes_no_pueden_quedar_iguales(
    client, usuario_admin, empresa, db
):
    """La base lo prohíbe; dejarlo llegar hasta allá sería un error 500."""
    login(client, "admin@test.cl")
    # Las dos abiertas y del mismo mes y comprobante: una línea cerrada no se
    # toca, así que no serviría para probar el choque.
    otra_fila = [date(2026, 3, 1), 67, 7777, 500000, None, None, None,
                 "OTRO CLIENTE", "EMPNEGVTAVTAOEM", "83070800-6", None, 500000]
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla([FILA_2, otra_fila]), "p.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    una = ProvisionIngreso.query.filter_by(ot="7777").one()
    otra = ProvisionIngreso.query.filter_by(ot="6119").one()

    cuerpo = _guardar(client, una, ot=otra.ot, cbte_prov=otra.cbte_prov).get_data(as_text=True)

    assert "Ya hay otra línea" in cuerpo
    # Y la línea quedó como estaba: el rechazo no la deja a medias
    assert ProvisionIngreso.query.filter_by(ot="7777").one().cbte_prov == "67"
    assert ProvisionIngreso.query.count() == 2


def test_no_se_pueden_dejar_en_blanco(client, usuario_admin, empresa, db):
    """Son obligatorios en la base: vaciarlos sería un error 500."""
    login(client, "admin@test.cl")
    linea = _una_linea(client, empresa)

    cuerpo = _guardar(client, linea, ot="").get_data(as_text=True)

    assert "no pueden ir en blanco" in cuerpo
    assert ProvisionIngreso.query.one().ot == "6119"


def test_cambiarlos_pide_confirmacion_en_la_pantalla(client, usuario_admin, empresa, db):
    """Lo que ella pidió: que avise antes, no después."""
    login(client, "admin@test.cl")
    _una_linea(client, empresa)

    cuerpo = client.get("/contabilidad/provision-ingresos?estado=todas").get_data(as_text=True)

    assert 'name="linea-' in cuerpo and "-ot\"" in cuerpo
    assert "data-confirmar-cambio" in cuerpo
    assert "parte de cómo se reconoce la línea al importar" in cuerpo


def test_el_choque_se_comprueba_con_el_texto_ya_recortado(client, usuario_admin, empresa, db):
    """La columna guarda 30 caracteres. Comparar con el texto largo dejaría
    pasar dos que van a terminar iguales en la base, y eso es un error 500."""
    login(client, "admin@test.cl")
    largo = "A" * 30
    filas = [
        [date(2026, 3, 1), 67, largo, 500000, None, None, None,
         "UNO", "EMPNEGVTAVTAOEM", "83070800-6", None, 500000],
        [date(2026, 3, 1), 67, "7777", 500000, None, None, None,
         "OTRO", "EMPNEGVTAVTAOEM", "83070800-6", None, 500000],
    ]
    client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla(filas), "p.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    linea = ProvisionIngreso.query.filter_by(ot="7777").one()

    # Difiere del otro sólo después del carácter 30: al recortar quedan iguales.
    cuerpo = _guardar(client, linea, ot=largo + "DISTINTO").get_data(as_text=True)

    assert "Ya hay otra línea" in cuerpo
    assert ProvisionIngreso.query.filter_by(ot="7777").one() is not None


# --- El mes se puede escribir con letras -------------------------------
#
# La columna se llama "Mes" y la aplicación muestra los meses por su nombre en
# todas las pantallas, así que escribir "septiembre" es lo natural. Pedir el
# número a secas rechazaba la planilla entera sin que se entendiera por qué: el
# mensaje culpaba a las columnas corridas, que estaban perfectas.


@pytest.mark.parametrize("escrito, esperado", [
    ("septiembre", 9), ("Septiembre", 9), ("SEPTIEMBRE", 9),
    ("sep", 9), ("sept", 9), ("Sep.", 9),
    ("marzo", 3), ("dic", 12), ("may", 5),
    (3, 3), ("3", 3), ("12", 12),
])
def test_el_mes_se_entiende_con_letras_o_con_numero(escrito, esperado):
    from app.utils.provision_ingresos_excel import numero_de_mes

    assert numero_de_mes(escrito) == esperado


def test_una_fecha_en_la_columna_del_mes_tambien_sirve():
    """Escribir "sep-26" hace que Excel lo guarde como fecha: la celda deja de
    traer un mes y trae un día entero. Es el mismo tropiezo con otra forma."""
    from datetime import datetime

    from app.utils.provision_ingresos_excel import numero_de_mes

    assert numero_de_mes(date(2026, 9, 1)) == 9
    assert numero_de_mes(datetime(2026, 9, 1)) == 9


@pytest.mark.parametrize("escrito", ["0", "13", "", None, "cualquier cosa", "x"])
def test_lo_que_no_es_un_mes_no_se_inventa(escrito):
    from app.utils.provision_ingresos_excel import numero_de_mes

    assert numero_de_mes(escrito) is None


def test_la_planilla_con_el_mes_en_letras_entra(client, usuario_admin, empresa, db):
    """El caso real que no dejaba subir el archivo."""
    login(client, "admin@test.cl")
    filas = [
        ["septiembre", 2026, 749, 6333, 3060000, None, None, None,
         "POLIMIN COMERCIAL", "EMPNEGVTAVTACAU", "79760310-4", None, None],
        ["septiembre", 2026, 749, 6339, 3420000, None, None, None,
         "SOC. CONTRACTUAL MINERA", "EMPNEGVTAVTAOEM", "96701340-4", None, None],
    ]

    respuesta = client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla_mes_anio(filas), "p.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert ProvisionIngreso.query.filter_by(empresa_id=empresa.id).count() == 2
    assert ProvisionIngreso.query.filter_by(ot="6333").one().mes_ano == date(2026, 9, 1)


def test_si_el_mes_no_se_entiende_el_mensaje_apunta_al_mes(client, usuario_admin, empresa, db):
    """Antes culpaba a las columnas corridas y mandaba a revisar algo que
    estaba bien: se perdía el tiempo buscando donde no era."""
    login(client, "admin@test.cl")
    filas = [["mes que no existe", 2026, 749, 6333, 3060000, None, None, None,
              "CLIENTE", "CENTRO", "79760310-4", None, None]]

    cuerpo = client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla_mes_anio(filas), "p.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    ).get_data(as_text=True)

    assert "no se entendió el mes" in cuerpo
    assert "septiembre" in cuerpo  # el mensaje muestra cómo escribirlo
    assert "columnas que indican los títulos" not in cuerpo


def test_si_de_verdad_faltan_las_columnas_el_mensaje_sigue_siendo_ese(
    client, usuario_admin, empresa, db
):
    """El mensaje viejo sigue estando para el problema que sí describe."""
    login(client, "admin@test.cl")
    filas = [["septiembre", 2026, None, None, 3060000, None, None, None,
              "CLIENTE", "CENTRO", "79760310-4", None, None]]

    cuerpo = client.post(
        "/contabilidad/provision-ingresos/importar",
        data={"archivo": (_planilla_mes_anio(filas), "p.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    ).get_data(as_text=True)

    assert "columnas que indican los títulos" in cuerpo
