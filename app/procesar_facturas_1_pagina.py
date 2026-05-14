import argparse
import hashlib
import re
import shutil
from pathlib import Path

import fitz
from slugify import slugify

from core.db import get_cursor

BASE_TRABAJO = Path("data/trabajo")
BASE_SALIDA = Path("data/salida")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def limpiar(texto: str) -> str:
    return slugify(texto or "SIN_RAZON_SOCIAL", separator="_").upper()


def extraer_desde_nombre(nombre: str) -> dict:
    stem = Path(nombre).stem.strip()

    m = re.search(
        r"^(?P<asiento>04-\d{4})\s+"
        r"(?P<serie>[A-Z0-9]{2,8})\s+"
        r"(?P<numero>[A-Z0-9]+)\s+"
        r"(?P<ruc>(10|20)\d{9})\s+"
        r"(?P<razon>.+)$",
        stem,
        re.I,
    )

    if not m:
        return {
            "asiento": None,
            "serie": None,
            "numero": None,
            "ruc": None,
            "razon": "SIN_RAZON_SOCIAL",
        }

    return {
        "asiento": m.group("asiento"),
        "serie": m.group("serie").upper(),
        "numero": m.group("numero"),
        "ruc": m.group("ruc"),
        "razon": m.group("razon").strip(),
    }


def nombre_factura(cliente: str, data: dict) -> str:
    return (
        f"{data['asiento']} "
        f"{cliente} FACTURA "
        f"{data['serie']} "
        f"{data['numero']} "
        f"{data['ruc']} "
        f"{limpiar(data['razon'])}.pdf"
    )


def get_or_create_lote(year: int, month: int, cliente: str, entrada: Path, salida: Path) -> int:
    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            INSERT INTO lotes_procesamiento (
                anio,
                mes,
                cliente_abreviatura,
                ruta_entrada,
                ruta_salida,
                estado,
                total_archivos
            )
            VALUES (%s, %s, %s, %s, %s, 'procesando', 0)
            ON CONFLICT (anio, mes, cliente_abreviatura)
            DO UPDATE SET actualizado_en = NOW()
            RETURNING id
        """, (
            year,
            month,
            cliente,
            str(entrada),
            str(salida),
        ))

        return cur.fetchone()["id"]


def registrar_documento_extraido(
    lote_id: int,
    data: dict,
    pdf_origen: Path,
    pdf_destino: Path,
):
    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            INSERT INTO documentos_extraidos (
                lote_id,
                asiento_contable,
                tipo_documental,
                serie,
                numero,
                ruc_emisor,
                razon_social_emisor,
                orden_compra,
                paginas,
                nombre_provisional,
                ruta_provisional,
                nombre_final,
                ruta_final,
                estado,
                fuente_datos,
                requiere_revision,
                motivo_revision
            )
            VALUES (
                %s,
                %s,
                'factura',
                %s,
                %s,
                %s,
                %s,
                NULL,
                '1',
                %s,
                %s,
                %s,
                %s,
                'procesado_sin_oc',
                'filename',
                FALSE,
                NULL
            )
        """, (
            lote_id,
            data["asiento"],
            data["serie"],
            data["numero"],
            data["ruc"],
            data["razon"],
            pdf_origen.name,
            str(pdf_origen),
            pdf_destino.name,
            str(pdf_destino),
        ))


def registrar_documento_agrupado_factura_1(
    year: int,
    month: int,
    cliente: str,
    data: dict,
    archivo_fuente: str,
    pdf_origen: Path,
    pdf_destino: Path,
    hash_sha256: str,
):
    clave = f"FACTURA|{data['ruc']}|{data['serie']}|{data['numero']}"

    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            INSERT INTO documentos_agrupados (
                asiento_contable,
                archivo_fuente,
                tipo_documental,
                clave_documental,
                serie,
                numero,
                pagina_inicio,
                pagina_fin,
                paginas,
                nombre_provisional,
                ruta_provisional,
                nombre_archivo,
                ruta_archivo,
                ruta_final,
                estado,
                cliente_abreviatura,
                anio,
                mes,
                origen
            )
            VALUES (
                %s,
                %s,
                'FACTURA',
                %s,
                %s,
                %s,
                1,
                1,
                '1',
                %s,
                %s,
                %s,
                %s,
                %s,
                'distribuido_sin_oc',
                %s,
                %s,
                %s,
                'factura_1_pagina'
            )
            ON CONFLICT DO NOTHING
        """, (
            data["asiento"],
            archivo_fuente,
            clave,
            data["serie"],
            data["numero"],
            pdf_origen.name,
            str(pdf_origen),
            pdf_destino.name,
            str(pdf_destino),
            str(pdf_destino),
            cliente,
            year,
            month,
        ))


def registrar_revision(lote_id: int, pdf: Path, motivo: str):
    data = extraer_desde_nombre(pdf.name)

    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            INSERT INTO documentos_extraidos (
                lote_id,
                asiento_contable,
                tipo_documental,
                serie,
                numero,
                ruc_emisor,
                razon_social_emisor,
                paginas,
                nombre_provisional,
                ruta_provisional,
                estado,
                fuente_datos,
                requiere_revision,
                motivo_revision
            )
            VALUES (
                %s, %s, 'otro', %s, %s, %s, %s, '1',
                %s, %s, 'revision', 'filename',
                TRUE, %s
            )
        """, (
            lote_id,
            data.get("asiento"),
            data.get("serie"),
            data.get("numero"),
            data.get("ruc"),
            data.get("razon"),
            pdf.name,
            str(pdf),
            motivo,
        ))


def procesar(year: int, cliente: str, month: int):
    cliente = cliente.upper()
    month_str = f"{month:02d}"

    pendientes = BASE_TRABAJO / str(year) / cliente / month_str / "pendientes"
    salida = BASE_SALIDA / str(year) / cliente / month_str / "sin_oc"

    salida.mkdir(parents=True, exist_ok=True)

    lote_id = get_or_create_lote(year, month, cliente, pendientes, salida)

    pdfs = sorted(pendientes.glob("*.pdf"))

    print(f"Pendientes: {pendientes}")
    print(f"PDF encontrados: {len(pdfs)}")

    procesados = 0
    revision = 0

    for pdf in pdfs:
        try:
            with fitz.open(pdf) as doc:
                paginas = doc.page_count
        except Exception as e:
            registrar_revision(lote_id, cliente, year, month, pdf, f"No se pudo abrir PDF: {e}")
            print(f"[REVISION] No se pudo abrir: {pdf.name}")
            revision += 1
            continue

        if paginas != 1:
            continue

        data = extraer_desde_nombre(pdf.name)

        if not data["asiento"] or not data["serie"] or not data["numero"] or not data["ruc"]:
            registrar_revision(
                lote_id=lote_id,
                cliente=cliente,
                year=year,
                month=month,
                pdf=pdf,
                motivo="Nombre no cumple formato de factura 1 página",
            )
            
            registrar_revision(
                lote_id=lote_id,
                pdf=pdf,
                motivo="Nombre no cumple formato de factura 1 página",
            )

            print(f"[REVISION] Nombre no cumple formato: {pdf.name}")
            revision += 1
            continue

        nuevo_nombre = nombre_factura(cliente, data)
        destino = salida / nuevo_nombre

        hash_pdf = sha256_file(pdf)
        origen_original = pdf

        shutil.move(str(pdf), str(destino))

        registrar_documento_extraido(
            lote_id=lote_id,
            data=data,
            pdf_origen=origen_original,
            pdf_destino=destino,
        )

        registrar_documento_agrupado_factura_1(
            year=year,
            month=month,
            cliente=cliente,
            data=data,
            archivo_fuente=origen_original.name,
            pdf_origen=origen_original,
            pdf_destino=destino,
            hash_sha256=hash_pdf,
        )

        procesados += 1
        print(f"[FACTURA 1 PAG] {origen_original.name} -> {nuevo_nombre}")

    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            UPDATE lotes_procesamiento
            SET total_archivos = total_archivos + %s,
                estado = 'procesado_parcial',
                actualizado_en = NOW()
            WHERE id = %s
        """, (procesados, lote_id))

    print(f"Procesados: {procesados}")
    print(f"Revisión: {revision}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)

    args = parser.parse_args()

    procesar(args.year, args.cliente, args.month)