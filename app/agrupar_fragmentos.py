import argparse
from pathlib import Path

import fitz

from core.db import get_cursor


BASE_TRABAJO = Path("data/trabajo")
BASE_SALIDA = Path("data/salida")


def same_group(a, b) -> bool:
    if a["archivo_fuente"] != b["archivo_fuente"]:
        return False

    if b["es_reverso"]:
        return True

    if a["tipo_detectado"] != b["tipo_detectado"]:
        return False

    if not a["clave_documental"] or not b["clave_documental"]:
        return False

    return a["clave_documental"] == b["clave_documental"]


def build_nombre(grupo):
    first = grupo[0]
    last = grupo[-1]

    asiento = first["asiento_contable"]
    tipo = first["tipo_detectado"].upper()
    page_start = first["pagina"]
    page_end = last["pagina"]

    clave = first["clave_documental"] or ""

    if clave.startswith("OS|"):
        numero = clave.split("|")[1]
        return f"{asiento} OS {numero} P{page_start:03d}-P{page_end:03d}.pdf"

    if clave.startswith("OC|"):
        numero = clave.split("|")[1]
        return f"{asiento} OC {numero} P{page_start:03d}-P{page_end:03d}.pdf"

    if clave.startswith("FACTURA|"):
        _, ruc, serie, numero = clave.split("|")
        return f"{asiento} FACTURA {serie} {numero} {ruc} P{page_start:03d}-P{page_end:03d}.pdf"

    if clave.startswith("GUIA|"):
        _, ruc, serie, numero = clave.split("|")
        return f"{asiento} GUIA_REMISION {serie} {numero} {ruc} P{page_start:03d}-P{page_end:03d}.pdf"

    if clave.startswith("NI|"):
        numero = clave.split("|")[1]
        return f"{asiento} NOTA_INGRESO {numero} P{page_start:03d}-P{page_end:03d}.pdf"

    return f"{asiento} {tipo} P{page_start:03d}-P{page_end:03d}.pdf"


def export_group(pdf_path: Path, pages: list[int], output_pdf: Path):
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    src = fitz.open(pdf_path)
    dst = fitz.open()

    for page_number in pages:
        dst.insert_pdf(src, from_page=page_number - 1, to_page=page_number - 1)

    dst.save(output_pdf)

    dst.close()
    src.close()


def make_groups(rows):
    grupos = []

    actual = []

    for row in rows:
        if not actual:
            actual.append(row)
            continue

        prev = actual[-1]

        if row["pagina"] == prev["pagina"] + 1 and same_group(prev, row):
            actual.append(row)
        else:
            grupos.append(actual)
            actual = [row]

    if actual:
        grupos.append(actual)

    return grupos


def process(year: int, cliente: str, month: int):
    pendientes = BASE_TRABAJO / str(year) / cliente / f"{month:02d}" / "pendientes"

    provisional = (
        BASE_SALIDA
        / str(year)
        / cliente
        / f"{month:02d}"
        / "provisional"
    )

    with get_cursor() as (_, cur):
        cur.execute(
            """
            SELECT *
            FROM documentos_paginas
            WHERE estado = 'detectado'
            ORDER BY archivo_fuente, pagina
            """
        )
        rows = cur.fetchall()

    por_archivo = {}

    for row in rows:
        por_archivo.setdefault(row["archivo_fuente"], []).append(row)

    total = 0

    for archivo_fuente, items in por_archivo.items():
        pdf_path = pendientes / archivo_fuente

        if not pdf_path.exists():
            print(f"[WARN] No existe PDF fuente: {pdf_path}")
            continue

        grupos = make_groups(items)

        for grupo in grupos:
            pages = [x["pagina"] for x in grupo]
            nombre = build_nombre(grupo)
            output_pdf = provisional / nombre

            export_group(pdf_path, pages, output_pdf)

            first = grupo[0]
            last = grupo[-1]

            with get_cursor(commit=True) as (_, cur):
                cur.execute(
                    """
                    INSERT INTO documentos_agrupados (
                        asiento_contable,
                        archivo_fuente,
                        tipo_documental,
                        clave_documental,
                        serie,
                        numero,
                        orden_servicio,
                        orden_compra,
                        pagina_inicio,
                        pagina_fin,
                        paginas,
                        nombre_provisional,
                        ruta_provisional
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        first["asiento_contable"],
                        archivo_fuente,
                        first["tipo_detectado"],
                        first["clave_documental"],
                        first.get("serie"),
                        first.get("numero"),
                        first["clave_documental"].split("|")[1]
                        if first["clave_documental"] and first["clave_documental"].startswith("OS|")
                        else None,
                        first["clave_documental"].split("|")[1]
                        if first["clave_documental"] and first["clave_documental"].startswith("OC|")
                        else None,
                        first["pagina"],
                        last["pagina"],
                        ",".join(map(str, pages)),
                        nombre,
                        str(output_pdf),
                    ),
                )

            total += 1
            print(f"[AGRUPADO] {nombre}")

    print(f"Total agrupados: {total}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)
    args = parser.parse_args()

    process(args.year, args.cliente, args.month)