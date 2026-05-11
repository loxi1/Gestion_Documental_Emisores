import argparse
import re
import shutil
import hashlib
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
        r"(?P<serie>[A-Z0-9]{2,6})\s+"
        r"(?P<numero>\d+)\s+"
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
        f"{cliente} FACTURA "
        f"{data['serie']} "
        f"{data['numero']} "
        f"{data['ruc']} "
        f"{limpiar(data['razon'])}.pdf"
    )


def get_or_create_lote(year: int, month: int, cliente: str, entrada: Path, salida: Path) -> int:
    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            """
            INSERT INTO lotes_procesamiento (
                anio, mes, cliente_abreviatura, ruta_entrada, ruta_salida, estado, total_archivos
            )
            VALUES (%s, %s, %s, %s, %s, 'procesando', 0)
            ON CONFLICT (anio, mes, cliente_abreviatura)
            DO UPDATE SET actualizado_en = NOW()
            RETURNING id
            """,
            (year, month, cliente, str(entrada), str(salida)),
        )
        return cur.fetchone()["id"]


def registrar_documento(
    lote_id: int,
    cliente: str,
    data: dict,
    pdf_origen: Path,
    pdf_destino: Path,
    hash_sha256: str,
):
    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            """
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
                %s, %s, 'factura', %s, %s, %s, %s,
                NULL, '1',
                %s, %s,
                %s, %s,
                'procesado_sin_oc',
                'filename',
                FALSE,
                NULL
            )
            """,
            (
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
            ),
        )

registrar_documento_agrupado_factura_1(
    year=year,
    month=month,
    cliente=cliente,
    data=data,
    pdf_destino=destino,
)


def procesar(year: int, cliente: str, month: int):
    pendientes = BASE_TRABAJO / str(year) / cliente / f"{month:02d}" / "pendientes"
    salida = BASE_SALIDA / str(year) / cliente / f"{month:02d}" / "sin_oc"

    salida.mkdir(parents=True, exist_ok=True)

    lote_id = get_or_create_lote(year, month, cliente, pendientes, salida)

    pdfs = sorted(pendientes.glob("*.pdf"))

    print(f"Pendientes: {pendientes}")
    print(f"PDF encontrados: {len(pdfs)}")

    procesados = 0

    for pdf in pdfs:
        with fitz.open(pdf) as doc:
            paginas = doc.page_count

        if paginas != 1:
            continue

        data = extraer_desde_nombre(pdf.name)

        if not data["serie"] or not data["numero"] or not data["ruc"]:
            print(f"[REVISION] Nombre no cumple formato: {pdf.name}")
            continue

        nuevo_nombre = nombre_factura(cliente, data)
        destino = salida / nuevo_nombre

        hash_pdf = sha256_file(pdf)

        shutil.move(str(pdf), str(destino))

        registrar_documento(
            lote_id=lote_id,
            cliente=cliente,
            data=data,
            pdf_origen=pdf,
            pdf_destino=destino,
            hash_sha256=hash_pdf,
        )

        procesados += 1
        print(f"[FACTURA 1 PAG] {pdf.name} -> {nuevo_nombre}")

    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            """
            UPDATE lotes_procesamiento
            SET total_archivos = total_archivos + %s,
                estado = 'procesado_parcial',
                actualizado_en = NOW()
            WHERE id = %s
            """,
            (procesados, lote_id),
        )

    print(f"Procesados: {procesados}")

def registrar_documento_agrupado_factura_1(
    year: int,
    month: int,
    cliente: str,
    data: dict,
    pdf_destino: Path,
):
    clave = f"FACTURA|{data['ruc']}|{data['serie']}|{data['numero']}"

    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            INSERT INTO documentos_agrupados (
                asiento_contable,
                clave_documental,
                tipo_documental,
                nombre_archivo,
                ruta_archivo,
                ruta_final,
                paginas,
                estado,
                cliente_abreviatura,
                anio,
                mes,
                origen
            )
            VALUES (%s,%s,'FACTURA',%s,%s,%s,'1','distribuido_sin_oc',%s,%s,%s,'factura_1_pagina')
            ON CONFLICT DO NOTHING
        """, (
            data["asiento"],
            clave,
            pdf_destino.name,
            str(pdf_destino),
            str(pdf_destino),
            cliente,
            year,
            month,
        ))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)
    args = parser.parse_args()

    procesar(args.year, args.cliente, args.month)