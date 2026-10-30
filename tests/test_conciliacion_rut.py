"""El RUT de la contraparte, escrito de dos maneras.

Defontana exporta el RUT con puntos —"77.197.637-9"— y el SII sin ellos
—"77197637-9"—: es el mismo contribuyente. El cruce ya lo sabe (compara sólo
lo que identifica al RUT), pero la pantalla los comparaba como texto y pintaba
de rojo filas que cuadran, así que el rojo dejó de significar algo.

Cuando el RUT es de verdad otro, eso sí tiene que verse: en rojo y en el
estado del documento.
"""

from app.models.contabilidad import (
    ConciliacionSii,
    ConciliacionSiiDocumento,
    ConciliacionSiiLibro,
)
from app.utils.conciliacion_sii import cruzar
from tests.conftest import login


def _celda_del_rut(cuerpo, rut):
    """La celda de la tabla, no el data- del botón que también lleva el RUT."""
    marca = f">{rut}</td>"
    assert marca in cuerpo, f"no encontré la celda de {rut}"
    fin = cuerpo.index(marca)
    return cuerpo[cuerpo.rindex("<td", 0, fin):fin + len(marca)]


def _documento(**extra):
    base = dict(
        tipo_doc="33", tipo_doc_desc="Factura Electrónica", folio="281681",
        fecha="10/08/2025", estado="coincide", orden=0,
        neto_sii=100000, neto_defontana=100000,
        total_sii=119000, total_defontana=119000,
    )
    base.update(extra)
    return ConciliacionSiiDocumento(**base)


def _periodo(db, empresa, documento):
    conciliacion = ConciliacionSii(empresa_id=empresa.id, anio=2025, mes=8)
    libro = ConciliacionSiiLibro(libro="compra", cargas=1, n_coincide=1)
    conciliacion.libros.append(libro)
    libro.documentos.append(documento)
    db.session.add(conciliacion)
    db.session.commit()
    return conciliacion


def test_el_mismo_rut_con_y_sin_puntos_no_es_una_diferencia():
    d = _documento(rut_sii="77197637-9", rut_defontana="77.197.637-9")

    assert d.rut_distinto is False
    # Pero sí se sabe que están escritos distinto, para poder explicarlo.
    assert d.rut_escrito_distinto is True


def test_tampoco_cambian_el_verificador_en_minuscula_ni_los_ceros_de_relleno():
    assert _documento(rut_sii="11652869-K", rut_defontana="11.652.869-k").rut_distinto is False
    assert _documento(rut_sii="76568660-1", rut_defontana="076.568.660-1").rut_distinto is False


def test_un_rut_de_otro_contribuyente_si_es_una_diferencia():
    d = _documento(rut_sii="77197637-9", rut_defontana="76.568.660-1")

    assert d.rut_distinto is True
    assert d.rut_escrito_distinto is False


def test_si_falta_el_rut_de_un_lado_no_se_marca_nada():
    # "Solo en SII" no tiene con qué comparar: marcarlo en rojo diría que hay
    # un RUT distinto donde no hay ninguno.
    assert _documento(rut_sii="77197637-9", rut_defontana=None).rut_distinto is False
    assert _documento(rut_sii=None, rut_defontana="77.197.637-9").rut_distinto is False


def test_la_pantalla_no_pinta_de_rojo_el_mismo_rut_escrito_distinto(
    client, db, empresa, usuario_admin
):
    conciliacion = _periodo(db, empresa, _documento(
        rut_sii="77197637-9", rut_defontana="77.197.637-9",
        contraparte_sii="COMERCIAL KAM LIMITADA", contraparte_defontana="COMERCIAL KAM LIMITADA",
    ))
    login(client, "admin@test.cl")

    cuerpo = client.get(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra"
    ).get_data(as_text=True)

    assert "text-danger" not in _celda_del_rut(cuerpo, "77.197.637-9")
    assert "El mismo RUT, escrito distinto" in cuerpo


def test_la_pantalla_si_pinta_de_rojo_el_rut_de_otro_contribuyente(
    client, db, empresa, usuario_admin
):
    conciliacion = _periodo(db, empresa, _documento(
        estado="dif_datos", rut_sii="77197637-9", rut_defontana="76.568.660-1",
        diferencia_descrita="RUT: 77197637-9 vs 76.568.660-1",
    ))
    login(client, "admin@test.cl")

    cuerpo = client.get(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra"
    ).get_data(as_text=True)

    assert "text-danger" in _celda_del_rut(cuerpo, "76.568.660-1")


def test_y_el_rut_distinto_queda_en_el_estado_del_documento():
    """Lo que pidió: si después de normalizar siguen sin cruzar, que se vea."""
    sii = [{"tipo_doc": "33", "folio": "281681", "fecha": "10/08/2025",
            "rut": "77197637-9", "contraparte": "COMERCIAL KAM LIMITADA",
            "neto": 100000, "exento": 0, "iva": 19000, "total": 119000}]
    defontana = [{"tipo_doc": "33", "folio": "281681", "fecha": "10/08/2025",
                  "rut": "76.568.660-1", "contraparte": "EASY RETAIL S.A.",
                  "neto": 100000, "exento": 0, "iva": 19000, "total": 119000}]

    resultado = cruzar(sii, defontana, "compra")

    fila = resultado["filas"][0]
    assert fila["estado"] == "dif_datos"
    assert "RUT" in fila["diferencia_descrita"]
    assert resultado["conteos"]["dif_datos"] == 1


def test_el_mismo_rut_escrito_distinto_no_ensucia_el_estado():
    sii = [{"tipo_doc": "33", "folio": "281681", "fecha": "10/08/2025",
            "rut": "77197637-9", "contraparte": "COMERCIAL KAM LIMITADA",
            "neto": 100000, "exento": 0, "iva": 19000, "total": 119000}]
    defontana = [{"tipo_doc": "33", "folio": "281681", "fecha": "10/08/2025",
                  "rut": "77.197.637-9", "contraparte": "COMERCIAL KAM LTDA",
                  "neto": 100000, "exento": 0, "iva": 19000, "total": 119000}]

    resultado = cruzar(sii, defontana, "compra")

    assert resultado["filas"][0]["estado"] == "coincide"
    assert resultado["conteos"]["coincide"] == 1
