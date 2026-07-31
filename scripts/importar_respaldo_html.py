"""Traspasa un respaldo (.json) de la antigua herramienta HTML de control de
importaciones hacia las tablas del módulo de Importaciones.

El respaldo se descarga desde esa herramienta en Respaldo > "Descargar
respaldo (.json)". Este script es seguro de ejecutar más de una vez: no
duplica proveedores (por nombre), registros de DIN (por N° + folio) ni
importaciones (por N° PEI) que ya existan.

Uso:
    python scripts/importar_respaldo_html.py respaldo_importaciones_20260731.json
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.importacion import (
    DinRegistro,
    Importacion,
    ImportacionAsientoLinea,
    ImportacionGrupoMeta,
    ProveedorImportacion,
)
from app.utils import importaciones_calculo as calculo

TIPO_SALDO = {"A Favor": "a_favor", "En Contra": "en_contra"}
TIPO_JS_A_PY = {
    "facturaAgencia": "factura_agencia",
    "din": "din",
    "cuadratura": "cuadratura",
    "cuadraturaUpsDhl": "cuadratura_ups_dhl",
    "costeo": "costeo",
    "ajuste": "ajuste",
}
ESTADOS_DIN_VALIDOS = {"pendiente", "revision", "pagado"}
ESTADOS_IMPORT_VALIDOS = {"pendiente", "costeando", "cerrado"}


def _texto(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _entero(valor):
    if valor in (None, ""):
        return 0
    try:
        return int(round(float(valor)))
    except (TypeError, ValueError):
        return 0


def _numero(valor):
    if valor in (None, ""):
        return 0.0
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def _fecha(valor):
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def importar_proveedores(empresa_id, proveedores):
    existentes = {p.nombre.strip().lower() for p in ProveedorImportacion.query.filter_by(empresa_id=empresa_id)}
    creados = 0
    for p in proveedores:
        nombre = _texto(p.get("nombre"))
        if not nombre or nombre.lower() in existentes:
            continue
        db.session.add(
            ProveedorImportacion(
                empresa_id=empresa_id,
                rut=_texto(p.get("rut")),
                nombre=nombre,
                pais=_texto(p.get("pais")),
                tratado_tlc=_texto(p.get("tratado")),
            )
        )
        existentes.add(nombre.lower())
        creados += 1
    return creados


def importar_din(empresa_id, registros):
    existentes = {(r.numero or "", r.folio or "") for r in DinRegistro.query.filter_by(empresa_id=empresa_id)}
    creados = 0
    for r in registros:
        clave = (_texto(r.get("numero")) or "", _texto(r.get("folio")) or "")
        if clave in existentes:
            continue
        estado = r.get("estado") if r.get("estado") in ESTADOS_DIN_VALIDOS else "pendiente"
        db.session.add(
            DinRegistro(
                empresa_id=empresa_id,
                numero=_texto(r.get("numero")),
                oc=_texto(r.get("oc")),
                agencia=_texto(r.get("agencia")),
                n_doc_agencia=_texto(r.get("nDocAgencia")),
                monto_doc_agencia=_entero(r.get("montoDocAgencia")),
                proveedor=_texto(r.get("proveedor")),
                n_invoice=_texto(r.get("nInvoice")),
                estado=estado,
                rut=_texto(r.get("rut")),
                razon_social=_texto(r.get("razonSocial")),
                formulario=_texto(r.get("formulario")),
                folio=_texto(r.get("folio")),
                fecha_pago=_fecha(r.get("fechaPago")),
                vcto=_fecha(r.get("vcto")),
                advalorem=_entero(r.get("advalorem")),
                total_pagado=_entero(r.get("totalPagado")),
            )
        )
        existentes.add(clave)
        creados += 1
    return creados


def _agregar_lineas(importacion, entries):
    for tipo_js, lineas in (entries or {}).items():
        tipo_py = TIPO_JS_A_PY.get(tipo_js)
        if not tipo_py:
            continue
        for orden, linea in enumerate(lineas):
            db.session.add(
                ImportacionAsientoLinea(
                    importacion=importacion,
                    tipo=tipo_py,
                    rol=_texto(linea.get("role")),
                    orden=orden,
                    proveedor=_texto(linea.get("proveedor")),
                    fecha=_fecha(linea.get("fecha")),
                    tipo_doc=_texto(linea.get("tipoDoc")),
                    n_doc=_texto(linea.get("nDoc")),
                    cuenta=_texto(linea.get("cuenta")),
                    debe=_entero(linea.get("debe")),
                    haber=_entero(linea.get("haber")),
                    ecomex=_entero(linea.get("ecomex")) if "ecomex" in linea else None,
                    dif=_entero(linea.get("dif")) if "dif" in linea else None,
                    descripcion=_texto(linea.get("descripcion")),
                    cbte_linea=_texto(linea.get("cbteLinea")),
                    n_cuenta=_texto(linea.get("nCuenta")),
                )
            )


def _agregar_metas(importacion, group_meta):
    for tipo_js, meta in (group_meta or {}).items():
        tipo_py = TIPO_JS_A_PY.get(tipo_js)
        if not tipo_py:
            continue
        db.session.add(
            ImportacionGrupoMeta(
                importacion=importacion,
                tipo=tipo_py,
                cbte=_texto(meta.get("cbte")),
                saldo_anterior_monto=_entero(meta.get("saldoAnteriorMonto")),
                saldo_nuevo_tipo=TIPO_SALDO.get(meta.get("saldoNuevoTipo"), "a_favor"),
                saldo_nuevo_cuenta=_texto(meta.get("saldoNuevoCuenta")),
                saldo_nuevo_monto=_entero(meta.get("saldoNuevoMonto")),
                monto_usd=_numero(meta.get("montoUsd")),
                tipo_cambio=_numero(meta.get("tipoCambio")),
                proveedor=_texto(meta.get("proveedor")),
                fecha=_fecha(meta.get("fecha")),
                tipo_doc=_texto(meta.get("tipoDoc")),
                n_doc=_texto(meta.get("nDoc")),
            )
        )


def importar_importaciones(empresa_id, imports_json):
    peis_existentes = {(i.pei or "") for i in Importacion.query.filter_by(empresa_id=empresa_id) if i.pei}
    creados = 0
    for imp_json in imports_json:
        pei = _texto(imp_json.get("pei"))
        if pei and pei in peis_existentes:
            continue

        estado = imp_json.get("estado") if imp_json.get("estado") in ESTADOS_IMPORT_VALIDOS else "pendiente"
        importacion = Importacion(
            empresa_id=empresa_id,
            fecha_pei=_fecha(imp_json.get("fechaPei")),
            pei=pei,
            imp=_texto(imp_json.get("imp")),
            proveedor_nombre=_texto(imp_json.get("proveedor")),
            oc=_texto(imp_json.get("oc")),
            monto=_entero(imp_json.get("monto")),
            agencia=_texto(imp_json.get("agencia")),
            tipo_saldo=TIPO_SALDO.get(imp_json.get("tipoSaldo"), "a_favor"),
            saldo_agencia=_entero(imp_json.get("saldoAgencia")),
            pais=_texto(imp_json.get("pais")),
            tratado_tlc=_texto(imp_json.get("tratado")),
            notas=_texto(imp_json.get("notas")),
            estado=estado,
        )
        db.session.add(importacion)
        db.session.flush()

        _agregar_lineas(importacion, imp_json.get("entries"))
        _agregar_metas(importacion, imp_json.get("groupMeta"))

        # Por si el respaldo no traía completa alguna de las 6 plantillas.
        calculo.sembrar_lineas_plantilla(importacion)
        calculo.recalcular(importacion)

        if pei:
            peis_existentes.add(pei)
        creados += 1

    return creados


def main():
    if len(sys.argv) != 2:
        print("Uso: python scripts/importar_respaldo_html.py <respaldo.json>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)

    app = create_app()
    with app.app_context():
        empresa_id = app.config["EMPRESA_ID"]

        proveedores_creados = importar_proveedores(empresa_id, data.get("proveedores") or [])
        db.session.commit()

        din_creados = importar_din(empresa_id, data.get("dinRecords") or [])
        db.session.commit()

        importaciones_creadas = importar_importaciones(empresa_id, data.get("imports") or [])
        db.session.commit()

        print(f"Proveedores creados: {proveedores_creados}")
        print(f"Registros DIN creados: {din_creados}")
        print(f"Importaciones creadas: {importaciones_creadas}")


if __name__ == "__main__":
    main()
