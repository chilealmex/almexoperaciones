"""Un documento que quedó contabilizado en otro mes.

En Defontana el libro en que cae un documento lo decide su "fecha contable",
que es un campo distinto de la fecha del documento. Cuando esa fecha queda en
el mes equivocado, el documento aparece en un período y falta en el otro sin
que ninguno de los dos sistemas esté mal: el SII informa la factura 1667 en
noviembre y el libro de Defontana la tiene en octubre.

Anotarlo deja dicho dónde está el documento, lo saca de lo pendiente de este
mes y no toca ningún monto.
"""

import io

import openpyxl

from app.models.contabilidad import (
    ConciliacionSii,
    ConciliacionSiiDocumento,
    ConciliacionSiiLibro,
)
from tests.conftest import login


def _periodo(db, empresa, *, anio=2025, mes=11, estado="abierto"):
    conciliacion = ConciliacionSii(empresa_id=empresa.id, anio=anio, mes=mes, estado=estado)
    libro = ConciliacionSiiLibro(libro="compra", cargas=1, n_solo_sii=1)
    conciliacion.libros.append(libro)
    documento = ConciliacionSiiDocumento(
        tipo_doc="33", tipo_doc_desc="Factura Electrónica", folio="1667",
        fecha="23/10/2025", rut_sii="78031034-0", contraparte_sii="TRANSPORTES MAPICK SPA",
        neto_sii=100000, iva_sii=19000, total_sii=119000,
        estado="solo_sii", diferencia_descrita="Solo en SII", orden=0,
    )
    libro.documentos.append(documento)
    db.session.add(conciliacion)
    db.session.commit()
    return conciliacion, libro, documento


def _url(conciliacion, documento):
    return f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra/{documento.id}/mes-contable"


def test_anotar_el_mes_lo_deja_dicho_en_el_documento(client, db, empresa, usuario_admin):
    conciliacion, _libro, documento = _periodo(db, empresa)
    login(client, "admin@test.cl")

    r = client.post(_url(conciliacion, documento), data={"mes": "2025-10"}, follow_redirects=True)

    assert r.status_code == 200
    assert documento.mes_contable == "2025-10"
    assert documento.mes_contable_texto == "Octubre 2025"
    assert documento.mes_contable_por_id == usuario_admin.id
    assert documento.mes_contable_en is not None


def test_el_documento_anotado_deja_de_estar_pendiente(client, db, empresa, usuario_admin):
    conciliacion, libro, documento = _periodo(db, empresa)
    assert libro.pendientes == 1
    login(client, "admin@test.cl")

    client.post(_url(conciliacion, documento), data={"mes": "2025-10"}, follow_redirects=True)

    assert libro.n_otro_mes == 1
    assert libro.pendientes == 0
    # Sin tocar los montos ni el estado: el documento sigue siendo "solo en SII"
    # en este período, sólo que ya se sabe por qué.
    assert documento.estado == "solo_sii"
    assert documento.total_sii == 119000


def test_quitar_la_nota_lo_devuelve_a_pendiente(client, db, empresa, usuario_admin):
    conciliacion, libro, documento = _periodo(db, empresa)
    login(client, "admin@test.cl")
    client.post(_url(conciliacion, documento), data={"mes": "2025-10"}, follow_redirects=True)

    client.post(_url(conciliacion, documento), data={"mes": ""}, follow_redirects=True)

    assert documento.mes_contable is None
    assert libro.n_otro_mes == 0
    assert libro.pendientes == 1


def test_un_mes_inventado_no_se_guarda(client, db, empresa, usuario_admin):
    # Llega texto de un formulario: un mes imposible dejaría una nota que
    # después no se puede ni leer ni ordenar.
    conciliacion, _libro, documento = _periodo(db, empresa)
    login(client, "admin@test.cl")

    client.post(_url(conciliacion, documento), data={"mes": "2025-13"}, follow_redirects=True)

    assert documento.mes_contable is None


def test_no_se_cuenta_dos_veces_el_que_ademas_esta_aceptado(client, db, empresa, usuario_admin):
    # Si contara en los dos grupos, el mes quedaría con menos pendientes de los
    # que tiene.
    conciliacion, libro, documento = _periodo(db, empresa)
    login(client, "admin@test.cl")
    client.post(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra/{documento.id}/aceptar",
        data={"motivo": "revisada"}, follow_redirects=True,
    )
    client.post(_url(conciliacion, documento), data={"mes": "2025-10"}, follow_redirects=True)

    assert libro.n_aceptados == 1
    assert libro.n_otro_mes == 0
    assert libro.pendientes == 0


def test_en_un_periodo_cerrado_no_se_puede_anotar(client, db, empresa, usuario_admin):
    conciliacion, _libro, documento = _periodo(db, empresa, estado="cerrado")
    login(client, "admin@test.cl")

    r = client.post(_url(conciliacion, documento), data={"mes": "2025-10"}, follow_redirects=True)

    assert documento.mes_contable is None
    assert "cerrado" in r.get_data(as_text=True).lower()


def test_la_pantalla_lo_muestra_y_deja_filtrarlo(client, db, empresa, usuario_admin):
    conciliacion, _libro, documento = _periodo(db, empresa)
    login(client, "admin@test.cl")
    client.post(_url(conciliacion, documento), data={"mes": "2025-10"}, follow_redirects=True)

    cuerpo = client.get(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra"
    ).get_data(as_text=True)

    assert "Octubre 2025" in cuerpo
    assert "En otro mes" in cuerpo
    # Y el documento ya no sale entre los pendientes.
    pendientes = client.get(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra?filtro=pendientes"
    ).get_data(as_text=True)
    assert "1667" not in pendientes
    en_otro_mes = client.get(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra?filtro=otro_mes"
    ).get_data(as_text=True)
    assert "1667" in en_otro_mes


def test_el_excel_trae_la_columna(client, db, empresa, usuario_admin):
    conciliacion, _libro, documento = _periodo(db, empresa)
    login(client, "admin@test.cl")
    client.post(_url(conciliacion, documento), data={"mes": "2025-10"}, follow_redirects=True)

    r = client.get(f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra.xlsx")

    assert r.status_code == 200
    hoja = openpyxl.load_workbook(io.BytesIO(r.data)).active
    valores = [v for fila in hoja.iter_rows(values_only=True) for v in fila]
    assert "Contabilizado en" in valores
    assert "Octubre 2025" in valores
