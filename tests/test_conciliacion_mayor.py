"""El Libro Mayor: en qué quedó contabilizado cada documento.

La conciliación compara lo que el SII informa contra lo que dice el libro de
Defontana. Faltaba la tercera verdad: en qué cuentas quedó el asiento. El
mayor la tiene — el IVA en la cuenta de IVA y el total en la de proveedores (o
clientes, en ventas)— y si esos dos calzan con lo informado, el neto quedó
bien contabilizado, porque neto = total − IVA.

Cada línea del mayor nombra su documento en la descripción:
"FCA#1043902 Proveedor 76.754.296-8 FEDEX EXPRESS CHILE SPA".
"""

import io

import openpyxl
import pytest

from app.models.contabilidad import (
    ConciliacionSii,
    ConciliacionSiiDocumento,
    ConciliacionSiiLibro,
)
from app.utils.conciliacion_sii import (
    ArchivoInvalido,
    comparar_con_mayor,
    juntar_mayores,
    leer_libro_mayor,
)
from tests.conftest import login


def _mayor(cuenta, nombre, lineas):
    """Un Libro Mayor de Defontana: un ".xls" que es HTML."""
    filas = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in fila) + "</tr>" for fila in lineas
    )
    html = f"""<html><head><title>Libro Mayor</title></head><body>
    <table><tr><td>Shaw Almex Chile SpA</td><td>Fecha :05/11/2026</td></tr></table>
    <table>
      <tr><td>Libro Mayor</td></tr>
      <tr><td>Período del 01/01/2026 al 31/12/2026</td></tr>
      <tr><td>Fecha</td><td>Número</td><td>Tipo</td><td>Descripción</td>
          <td>Débito $</td><td>Crédito $</td><td>Deudor $</td><td>Acreedor $</td></tr>
      <tr><td>{cuenta} {nombre}</td></tr>
      <tr><td>Saldo Anterior</td><td>0</td><td>0</td></tr>
      {filas}
      <tr><td>Total</td><td>0</td><td>0</td><td>0</td><td>0</td></tr>
    </table></body></html>"""
    return io.BytesIO(html.encode("cp1252"))


def _linea(fecha, numero, tipo, desc, debito="0", credito="0"):
    return [fecha, numero, tipo, desc, debito, credito, "0", "0"]


# El caso real: FCA#74074161 del 01-11, IVA 1.621 y total 10.150.
IVA_NOV = _mayor("1.1.1090.10.01", "IVA CREDITO FISCAL", [
    _linea("01/11/2026", "261100001", "Cpra_FCA",
           "FCA#74074161 Proveedor 76.124.890-1 CORREOS DE CHILE", debito="1,621"),
])
PROV_NOV = _mayor("2.1.1070.20.01", "PROVEEDORES NACIONALES", [
    _linea("01/11/2026", "261100001", "Cpra_FCA",
           "FCA#74074161 Cuota 1 Proveedor 76.124.890-1 CORREOS DE CHILE", credito="10,150"),
])


def _leer_los_dos():
    return juntar_mayores([leer_libro_mayor(IVA_NOV), leer_libro_mayor(PROV_NOV)])


def _documento(**extra):
    base = dict(folio="74074161", estado="coincide",
                rut_sii="76124890-1", rut_defontana="76.124.890-1",
                iva_sii=1621, iva_defontana=1621,
                total_sii=10150, total_defontana=10150)
    base.update(extra)
    return base


def test_se_lee_la_cuenta_y_lo_que_aporta():
    IVA_NOV.seek(0)
    mayor = leer_libro_mayor(IVA_NOV)

    assert mayor["cuenta"] == "1.1.1090.10.01"
    assert mayor["nombre"] == "IVA CREDITO FISCAL"
    # Se reconoce por el nombre: esta cuenta aporta el IVA del documento.
    assert mayor["clase"] == "iva"
    assert mayor["documentos"] == {("74074161", "761248901"): 1621}
    assert mayor["meses"] == {("74074161", "761248901"): "2026-11"}


def test_la_cuenta_de_proveedores_aporta_el_total_y_suma_al_haber():
    PROV_NOV.seek(0)
    mayor = leer_libro_mayor(PROV_NOV)

    assert mayor["clase"] == "total"
    # Es una cuenta de pasivo (empieza en 2): el crédito es el monto, en
    # positivo. Sin el signo, el total saldría en −10.150.
    assert mayor["documentos"] == {("74074161", "761248901"): 10150}


def test_el_documento_se_busca_por_folio_y_rut_aunque_se_escriban_distinto():
    # El mayor escribe el RUT con puntos y el SII sin ellos; el prefijo "FCA"
    # no se parece a los códigos del SII, así que no se usa para cruzar.
    IVA_NOV.seek(0); PROV_NOV.seek(0)
    visto = comparar_con_mayor(_documento(), _leer_los_dos())

    assert visto["estado"] == "cuadra"
    assert visto["iva_mayor"] == 1621
    assert visto["total_mayor"] == 10150
    assert visto["mes_mayor"] == "2026-11"


def test_si_el_iva_contabilizado_no_calza_lo_dice():
    IVA_NOV.seek(0); PROV_NOV.seek(0)
    visto = comparar_con_mayor(_documento(iva_defontana=1900), _leer_los_dos())

    assert visto["estado"] == "dif_iva"
    assert visto["iva_mayor"] == 1621


def test_y_si_no_calza_el_total():
    IVA_NOV.seek(0); PROV_NOV.seek(0)
    visto = comparar_con_mayor(_documento(total_defontana=12000), _leer_los_dos())

    assert visto["estado"] == "dif_total"


def test_un_peso_de_redondeo_no_es_una_diferencia():
    IVA_NOV.seek(0); PROV_NOV.seek(0)
    visto = comparar_con_mayor(_documento(iva_defontana=1622), _leer_los_dos())

    assert visto["estado"] == "cuadra"


def test_el_que_no_esta_en_el_mayor_lo_dice():
    IVA_NOV.seek(0); PROV_NOV.seek(0)
    visto = comparar_con_mayor(_documento(folio="999"), _leer_los_dos())

    assert visto["estado"] == "falta"
    assert visto["iva_mayor"] is None
    assert visto["total_mayor"] is None


def test_el_que_solo_informa_el_sii_se_compara_contra_el_sii():
    # No está en el libro de Defontana, así que sus montos de Defontana son 0:
    # comparando contra ellos, todo saldría distinto.
    IVA_NOV.seek(0); PROV_NOV.seek(0)
    visto = comparar_con_mayor(
        _documento(estado="solo_sii", rut_defontana=None,
                   iva_defontana=0, total_defontana=0),
        _leer_los_dos(),
    )

    assert visto["estado"] == "cuadra"


def test_una_nota_de_credito_queda_en_negativo_por_el_lado_de_la_cuenta():
    # En la nota de crédito el IVA va al haber y el proveedor al debe: con el
    # signo de cada cuenta, los dos quedan negativos, igual que en el resto
    # del cruce.
    iva = _mayor("1.1.1090.10.01", "IVA CREDITO FISCAL", [
        _linea("05/11/2026", "261100023", "Cpra_NCC",
               "NCC#1295765 Proveedor 90.844.000-1 EMPRESA", credito="9,443")])
    prov = _mayor("2.1.1070.20.01", "PROVEEDORES NACIONALES", [
        _linea("05/11/2026", "261100023", "Cpra_NCC",
               "NCC#1295765 Cuota 1 Proveedor 90.844.000-1 EMPRESA", debito="59,143")])

    mayor = juntar_mayores([leer_libro_mayor(iva), leer_libro_mayor(prov)])

    assert mayor["iva"][("1295765", "908440001")] == -9443
    assert mayor["total"][("1295765", "908440001")] == -59143


def test_un_archivo_que_no_es_libro_mayor_se_rechaza_con_un_mensaje_claro():
    with pytest.raises(ArchivoInvalido) as error:
        leer_libro_mayor(io.BytesIO(b"<html><body><table><tr><td>otra cosa</td></tr></table></body></html>"))

    assert "Libro Mayor" in str(error.value)


def test_un_mayor_sin_documentos_tambien():
    vacio = _mayor("2.1.1070.20.01", "PROVEEDORES NACIONALES", [
        _linea("05/11/2026", "261100099", "EGRESO", "Pago a proveedores", debito="100")])

    with pytest.raises(ArchivoInvalido) as error:
        leer_libro_mayor(vacio)

    assert "no trae líneas con documento" in str(error.value)


# ---------- La pantalla ----------

def _periodo(db, empresa, **extra):
    conciliacion = ConciliacionSii(empresa_id=empresa.id, anio=2026, mes=11)
    libro = ConciliacionSiiLibro(libro="compra", cargas=1, n_coincide=1)
    conciliacion.libros.append(libro)
    documento = ConciliacionSiiDocumento(
        tipo_doc="33", tipo_doc_desc="Factura Electrónica", folio="74074161",
        fecha="01/11/2026", rut_sii="76124890-1", rut_defontana="76.124.890-1",
        contraparte_sii="CORREOS DE CHILE", contraparte_defontana="CORREOS DE CHILE",
        iva_sii=1621, iva_defontana=extra.get("iva_defontana", 1621),
        total_sii=10150, total_defontana=10150,
        estado="coincide", orden=0,
    )
    libro.documentos.append(documento)
    db.session.add(conciliacion)
    db.session.commit()
    return conciliacion, libro, documento


def _subir(client, conciliacion, **extra):
    IVA_NOV.seek(0); PROV_NOV.seek(0)
    datos = {"mayor": [(io.BytesIO(IVA_NOV.read()), "mayor-iva.xls"),
                       (io.BytesIO(PROV_NOV.read()), "mayor-proveedores.xls")]}
    datos.update(extra)
    return client.post(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra/mayor",
        data=datos, content_type="multipart/form-data", follow_redirects=True,
    )


def test_cargar_el_mayor_deja_lo_contabilizado_en_cada_documento(client, db, empresa, usuario_admin):
    conciliacion, libro, documento = _periodo(db, empresa)
    login(client, "admin@test.cl")

    r = _subir(client, conciliacion)

    assert r.status_code == 200
    assert documento.iva_mayor == 1621
    assert documento.total_mayor == 10150
    assert documento.mayor_estado == "cuadra"
    assert documento.mes_mayor == "2026-11"
    assert libro.n_mayor_dif == 0
    assert libro.mayor_cargado_en is not None
    assert "IVA CREDITO FISCAL" in (libro.mayor_cuentas or "")


def test_cuando_lo_contabilizado_no_calza_queda_contado(client, db, empresa, usuario_admin):
    conciliacion, libro, documento = _periodo(db, empresa, iva_defontana=1900)
    login(client, "admin@test.cl")

    _subir(client, conciliacion)

    assert documento.mayor_estado == "dif_iva"
    assert libro.n_mayor_dif == 1
    cuerpo = client.get(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra?filtro=mayor_dif"
    ).get_data(as_text=True)
    assert "74074161" in cuerpo


def test_hacen_falta_las_dos_cuentas(client, db, empresa, usuario_admin):
    # El IVA sale de una cuenta y el total de la otra: con una sola, la mitad
    # de la comparación no existe.
    conciliacion, _libro, documento = _periodo(db, empresa)
    login(client, "admin@test.cl")
    IVA_NOV.seek(0)

    r = client.post(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra/mayor",
        data={"mayor": [(io.BytesIO(IVA_NOV.read()), "mayor-iva.xls")]},
        content_type="multipart/form-data", follow_redirects=True,
    )

    assert "proveedores o clientes" in r.get_data(as_text=True)
    assert documento.mayor_estado is None


def test_en_un_periodo_cerrado_no_se_carga(client, db, empresa, usuario_admin):
    conciliacion, _libro, documento = _periodo(db, empresa)
    conciliacion.estado = "cerrado"
    db.session.commit()
    login(client, "admin@test.cl")

    r = _subir(client, conciliacion)

    assert documento.mayor_estado is None
    assert "cerrado" in r.get_data(as_text=True).lower()


def test_lo_del_mayor_sobrevive_al_recalcular(client, db, empresa, usuario_admin):
    # La conciliación se recalcula mientras se corrigen asientos; volver a
    # subir el mayor en cada recálculo sería rehacer el mismo trabajo.
    conciliacion, libro, _documento = _periodo(db, empresa)
    login(client, "admin@test.cl")
    _subir(client, conciliacion)

    client.post(
        f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra/recalcular",
        follow_redirects=True,
    )

    documento = libro.documentos[0]
    assert documento.iva_mayor == 1621
    assert documento.total_mayor == 10150
    assert documento.mayor_estado == "cuadra"


def test_el_excel_trae_lo_del_mayor(client, db, empresa, usuario_admin):
    conciliacion, _libro, _documento = _periodo(db, empresa)
    login(client, "admin@test.cl")
    _subir(client, conciliacion)

    r = client.get(f"/contabilidad/conciliacion-sii/{conciliacion.id}/compra.xlsx")

    hoja = openpyxl.load_workbook(io.BytesIO(r.data)).active
    valores = [v for fila in hoja.iter_rows(values_only=True) for v in fila]
    assert "IVA en el mayor" in valores
    assert "Total en el mayor" in valores
    assert 1621 in valores and 10150 in valores
    assert "Cuadra con el mayor" in valores
