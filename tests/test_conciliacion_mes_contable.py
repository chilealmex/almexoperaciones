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


def test_anotarlo_lo_saca_de_la_lista_del_mes(client, db, empresa, usuario_admin):
    """Si quedó contabilizado en otro mes, éste no es su libro.

    Antes se quedaba en la lista con su marca y había que volver a mirarlo
    cada vez para acordarse de que ya estaba explicado.
    """
    conciliacion, _libro, documento = _periodo(db, empresa)
    login(client, "admin@test.cl")
    client.post(_url(conciliacion, documento), data={"mes": "2025-10"}, follow_redirects=True)

    cuerpo = client.get(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra"
    ).get_data(as_text=True)

    assert "1667" not in cuerpo
    # Pero no se pierde: su tarjeta lo cuenta y su filtro lo muestra.
    assert "En otro mes" in cuerpo
    en_otro_mes = client.get(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra?filtro=otro_mes"
    ).get_data(as_text=True)
    assert "1667" in en_otro_mes
    assert "Octubre 2025" in en_otro_mes
    # Y tampoco sale entre los pendientes.
    pendientes = client.get(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra?filtro=pendientes"
    ).get_data(as_text=True)
    assert "1667" not in pendientes


def test_borrar_la_nota_lo_devuelve_a_la_lista(client, db, empresa, usuario_admin):
    conciliacion, _libro, documento = _periodo(db, empresa)
    login(client, "admin@test.cl")
    client.post(_url(conciliacion, documento), data={"mes": "2025-10"}, follow_redirects=True)
    client.post(_url(conciliacion, documento), data={"mes": ""}, follow_redirects=True)

    cuerpo = client.get(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra"
    ).get_data(as_text=True)

    assert "1667" in cuerpo


def test_el_excel_trae_la_columna(client, db, empresa, usuario_admin):
    conciliacion, _libro, documento = _periodo(db, empresa)
    login(client, "admin@test.cl")
    client.post(_url(conciliacion, documento), data={"mes": "2025-10"}, follow_redirects=True)

    r = client.get(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra.xlsx?filtro=otro_mes"
    )

    assert r.status_code == 200
    hoja = openpyxl.load_workbook(io.BytesIO(r.data)).active
    valores = [v for fila in hoja.iter_rows(values_only=True) for v in fila]
    assert "Contabilizado en" in valores
    assert "Octubre 2025" in valores


# ---------- El mes de destino ----------
#
# La misma factura está en los dos meses: en el que la tiene contabilizada
# aparece como "solo en Defontana" y en el que la informa el SII como "solo en
# SII". Anotarla en uno explica también la fila del otro.

def _dos_meses(db, empresa):
    """Octubre con la factura en Defontana y noviembre con la misma en el SII."""
    octubre = ConciliacionSii(empresa_id=empresa.id, anio=2025, mes=10, estado="abierto")
    libro_oct = ConciliacionSiiLibro(libro="compra", cargas=1, n_solo_defontana=1)
    octubre.libros.append(libro_oct)
    libro_oct.documentos.append(ConciliacionSiiDocumento(
        tipo_doc="33", tipo_doc_desc="Factura Electrónica", folio="1667",
        fecha="23/10/2025", rut_defontana="78.031.034-0",
        contraparte_defontana="TRANSPORTES MAPICK SPA",
        neto_defontana=100000, iva_defontana=19000, total_defontana=119000,
        estado="solo_defontana", diferencia_descrita="Solo en Defontana", orden=0,
    ))
    noviembre, libro_nov, en_noviembre = _periodo(db, empresa)
    db.session.add(octubre)
    db.session.commit()
    return octubre, libro_oct.documentos[0], noviembre, en_noviembre


def test_el_mes_de_destino_dice_de_donde_viene_la_nota(client, db, empresa, usuario_admin):
    octubre, en_octubre, noviembre, _en_noviembre = _dos_meses(db, empresa)
    login(client, "admin@test.cl")

    client.post(
        f"/contabilidad/conciliacion-sii/{octubre.id}/compra/{en_octubre.id}/mes-contable",
        data={"mes": "2025-11"}, follow_redirects=True,
    )

    cuerpo = client.get(
        f"/contabilidad/conciliacion-sii/{noviembre.id}/compra"
    ).get_data(as_text=True)

    assert "anotada desde Octubre 2025" in cuerpo
    # Y con el camino de vuelta al mes que la anotó
    assert f"/contabilidad/conciliacion-sii/{octubre.id}/compra?filtro=otro_mes" in cuerpo


def test_sin_anotación_el_otro_mes_no_dice_nada(client, db, empresa, usuario_admin):
    _octubre, _en_octubre, noviembre, _en_noviembre = _dos_meses(db, empresa)
    login(client, "admin@test.cl")

    cuerpo = client.get(
        f"/contabilidad/conciliacion-sii/{noviembre.id}/compra"
    ).get_data(as_text=True)

    assert "anotada desde" not in cuerpo


def test_la_nota_de_otro_libro_no_se_cruza(client, db, empresa, usuario_admin):
    # Lo anotado en el libro de compras no tiene nada que decirle al de
    # ventas, aunque coincidan el tipo y el folio.
    octubre, en_octubre, noviembre, _en_noviembre = _dos_meses(db, empresa)
    ventas = ConciliacionSiiLibro(libro="venta", cargas=1, n_solo_sii=1)
    noviembre.libros.append(ventas)
    ventas.documentos.append(ConciliacionSiiDocumento(
        tipo_doc="33", tipo_doc_desc="Factura Electrónica", folio="1667",
        fecha="23/11/2025", rut_sii="78031034-0", estado="solo_sii", orden=0,
    ))
    db.session.commit()
    login(client, "admin@test.cl")
    client.post(
        f"/contabilidad/conciliacion-sii/{octubre.id}/compra/{en_octubre.id}/mes-contable",
        data={"mes": "2025-11"}, follow_redirects=True,
    )

    cuerpo = client.get(
        f"/contabilidad/conciliacion-sii/{noviembre.id}/venta"
    ).get_data(as_text=True)

    assert "anotada desde" not in cuerpo


def test_anotar_un_documento_en_su_propio_mes_no_se_avisa_a_si_mismo(
    client, db, empresa, usuario_admin
):
    # Anotar noviembre en un documento de noviembre no dice nada nuevo: el
    # aviso es para el otro mes, no para el suyo.
    _octubre, _en_octubre, noviembre, en_noviembre = _dos_meses(db, empresa)
    login(client, "admin@test.cl")

    client.post(
        f"/contabilidad/conciliacion-sii/{noviembre.id}/compra/{en_noviembre.id}/mes-contable",
        data={"mes": "2025-11"}, follow_redirects=True,
    )

    cuerpo = client.get(
        f"/contabilidad/conciliacion-sii/{noviembre.id}/compra?filtro=otro_mes"
    ).get_data(as_text=True)

    assert "anotada desde" not in cuerpo


def test_la_nota_de_otra_empresa_no_se_mezcla(client, db, empresa, usuario_admin):
    # Cada empresa tiene su contabilidad: una factura con el mismo folio en
    # otra empresa no tiene nada que decir acá.
    from app.models.empresa import Empresa

    otra = Empresa(rut="77.000.000-1", razon_social="Otra Empresa SPA")
    db.session.add(otra)
    db.session.commit()
    ajena = ConciliacionSii(empresa_id=otra.id, anio=2025, mes=10, estado="abierto")
    libro_ajeno = ConciliacionSiiLibro(libro="compra", cargas=1)
    ajena.libros.append(libro_ajeno)
    libro_ajeno.documentos.append(ConciliacionSiiDocumento(
        tipo_doc="33", folio="1667", estado="solo_defontana", orden=0,
        mes_contable="2025-11",
    ))
    db.session.add(ajena)
    db.session.commit()
    _octubre, _en_octubre, noviembre, _en_noviembre = _dos_meses(db, empresa)
    login(client, "admin@test.cl")

    cuerpo = client.get(
        f"/contabilidad/conciliacion-sii/{noviembre.id}/compra"
    ).get_data(as_text=True)

    assert "anotada desde" not in cuerpo
