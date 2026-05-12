import argparse
from pathlib import Path

from core.db import get_cursor
from core.qr_reader import decode_qr_from_pdf
from core.qr_parser import parse_qr_payload
from core.qr_utils import decode_qr_from_pdf_pro


def build_clave(tipo: str, ruc: str | None, serie: str | None, numero: str | None) -> str | None:
    if not tipo or not serie or not numero:
        return None

    if tipo == "factura":
        return f"FACTURA|{ruc or 'SINRUC'}|{serie}|{numero}"

    if tipo == "guia_remision":
        return f"GUIA|{ruc or 'SINRUC'}|{serie}|{numero}"

    return None


def aplicar_qr_a_data(parsed: dict) -> dict:
    tipo = parsed.get("tipo_documental")
    serie = parsed.get("serie")
    numero = parsed.get("numero")
    ruc = parsed.get("ruc_emisor")

    return {
        "tipo": tipo,
        "serie": serie,
        "numero": numero,
        "ruc": ruc,
        "clave_documental": build_clave(tipo, ruc, serie, numero),
    }


def resolver_ruta_pagina(row: dict, year: int, cliente: str, month: int) -> Path:
    if row.get("ruta_pagina_pdf"):
        return Path(row["ruta_pagina_pdf"])

    nombre = row["archivo_fuente"].replace(".pdf", "")
    pagina = row["pagina"]

    return Path("storage") / "tmp" / "pages" / str(year) / cliente / f"{month:02d}" / f"{nombre}_P{pagina}.pdf"


def procesar(year: int, cliente: str, month: int):
    cliente = cliente.upper()

    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT *
            FROM documentos_paginas
            WHERE requiere_qr = TRUE
              AND qr_procesado = FALSE
              AND cliente_abreviatura = %s
              AND anio = %s
              AND mes = %s
            ORDER BY archivo_fuente, pagina
        """, (cliente, year, month))
        rows = cur.fetchall()

    print(f"Páginas pendientes QR: {len(rows)}")

    debug_dir = Path("storage") / "tmp" / "qr_debug" / str(year) / cliente / f"{month:02d}"

    for row in rows:
        pdf_path = resolver_ruta_pagina(row, year, cliente, month)

        if not pdf_path.exists():
            with get_cursor(commit=True) as (_, cur):
                cur.execute("""
                    UPDATE documentos_paginas
                    SET qr_procesado = TRUE,
                        qr_error = %s,
                        estado = 'revision_manual_qr'
                    WHERE id = %s
                """, (f"No existe archivo: {pdf_path}", row["id"]))

            print(f"[NO EXISTE] {pdf_path}")
            continue

        print(f"[QR] {row['archivo_fuente']} P{row['pagina']}")

        qr_candidates = decode_qr_from_pdf_pro(
            pdf_path,
            max_pages=1,
            dpi=420,
            debug_dir=debug_dir,
        )

        if not qr_candidates:
            with get_cursor(commit=True) as (_, cur):
                cur.execute("""
                    UPDATE documentos_paginas
                    SET qr_procesado = TRUE,
                        qr_error = 'QR no detectado',
                        estado = 'revision_manual_qr'
                    WHERE id = %s
                """, (row["id"],))

            print("  QR no detectado")
            continue

        aplicado = False

        for raw in qr_candidates:
            parsed = parse_qr_payload(raw)

            if not parsed:
                continue

            tipo_qr = parsed.get("tipo_documental")

            if tipo_qr not in ("factura", "guia_remision"):
                continue

            data = aplicar_qr_a_data(parsed)

            if not data["clave_documental"]:
                continue

            with get_cursor(commit=True) as (_, cur):
                cur.execute("""
                    UPDATE documentos_paginas
                    SET tipo_detectado = %s,
                        serie = %s,
                        numero = %s,
                        ruc_emisor = %s,
                        clave_documental = %s,
                        qr_raw = %s,
                        qr_procesado = TRUE,
                        qr_error = NULL,
                        requiere_qr = FALSE,
                        estado = 'clasificado'
                    WHERE id = %s
                """, (
                    data["tipo"],
                    data["serie"],
                    data["numero"],
                    data["ruc"],
                    data["clave_documental"],
                    raw,
                    row["id"],
                ))

            aplicado = True
            print(f"  OK -> {data['clave_documental']}")
            break

        if not aplicado:
            with get_cursor(commit=True) as (_, cur):
                cur.execute("""
                    UPDATE documentos_paginas
                    SET qr_procesado = TRUE,
                        qr_error = 'QR detectado pero no parseable/usable',
                        estado = 'revision_manual_qr'
                    WHERE id = %s
                """, (row["id"],))

            print("  QR no usable")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)
    args = parser.parse_args()

    procesar(args.year, args.cliente, args.month)