import argparse
import re
from pathlib import Path

import fitz

from core.db import get_cursor
from core.ocr_runner import run_ocr
from core.classifier import detect_tipo_documental

BASE_TRABAJO = Path("data/trabajo")
TMP_DIR = Path("storage/tmp/pages")


def limpiar(txt: str) -> str:
    return (txt or "").replace("\x00", "").replace("\u0000", "")


def normalize(txt: str) -> str:
    return re.sub(r"\s+", " ", limpiar(txt).upper()).strip()


def extract_asiento(filename: str) -> str:
    m = re.search(r"^(04-\d{4})", filename)
    return m.group(1) if m else "SIN_ASIENTO"


def split_page(source_pdf: Path, page_index: int, output_pdf: Path):
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    with fitz.open(source_pdf) as src:
        dst = fitz.open()
        dst.insert_pdf(src, from_page=page_index, to_page=page_index)
        dst.save(output_pdf)
        dst.close()


def extract_text(pdf_path: Path) -> str:
    with fitz.open(pdf_path) as doc:
        return "\n".join(page.get_text("text") for page in doc)


def is_reverso_page(text: str) -> bool:
    t = normalize(text)
    return len(t) < 80 or ("USUARIO:" in t and len(t) < 300)


def ya_procesado_como_extraido(cliente: str, year: int, month: int, nombre_archivo: str) -> bool:
    """
    Evita doble pipeline:
    Si un PDF ya fue procesado como factura/otro de 1 página en documentos_extraidos,
    no debe volver a separarse por páginas.
    """
    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT 1
            FROM documentos_extraidos de
            INNER JOIN lotes_procesamiento lp
                ON lp.id = de.lote_id
            WHERE lp.cliente_abreviatura = %s
              AND lp.anio = %s
              AND lp.mes = %s
              AND de.nombre_provisional = %s
              AND de.estado <> 'revision'
            LIMIT 1
        """, (cliente, year, month, nombre_archivo))

        return cur.fetchone() is not None


def process(year: int, cliente: str, month: int):
    cliente = cliente.upper()
    month_str = f"{month:02d}"

    pendientes = BASE_TRABAJO / str(year) / cliente / month_str / "pendientes"
    pdfs = sorted(pendientes.glob("*.pdf"))
    tmp_dir = TMP_DIR / str(year) / cliente / month_str

    print(f"Pendientes: {pendientes}")
    print(f"PDF encontrados: {len(pdfs)}")

    omitidos = 0
    procesados = 0

    for pdf in pdfs:
        if ya_procesado_como_extraido(cliente, year, month, pdf.name):
            print(f"[OMITIDO EXTRAIDO] {pdf.name}")
            omitidos += 1
            continue

        asiento = extract_asiento(pdf.name)

        try:
            with fitz.open(pdf) as doc:
                total_pages = doc.page_count
        except Exception as exc:
            print(f"[ERROR PDF] {pdf.name}: {exc}")
            continue

        print(f"\n[PDF] {pdf.name} ({total_pages} páginas)")

        for idx in range(total_pages):
            page_num = idx + 1

            page_pdf = tmp_dir / f"{pdf.stem}_P{page_num}.pdf"
            page_ocr = tmp_dir / f"{pdf.stem}_P{page_num}_OCR.pdf"

            split_page(pdf, idx, page_pdf)

            text = extract_text(page_pdf)
            fuente = "pdf_text"

            if not text.strip():
                if run_ocr(page_pdf, page_ocr):
                    text = extract_text(page_ocr)
                    fuente = "ocr"

            text_clean = limpiar(text)
            tipo_aprox = detect_tipo_documental(normalize(text_clean), pdf.name)
            reverso = is_reverso_page(text_clean)

            print(
                f"  Página {page_num}: "
                f"tipo_aprox={tipo_aprox} reverso={reverso} fuente={fuente}"
            )

            with get_cursor(commit=True) as (_, cur):
                cur.execute("""
                    INSERT INTO documentos_paginas (
                        cliente_abreviatura,
                        anio,
                        mes,
                        asiento_contable,
                        archivo_fuente,
                        pagina,
                        tipo_detectado,
                        texto_extraido,
                        fuente_texto,
                        ruta_pagina_pdf,
                        es_reverso,
                        estado
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'separado')
                    ON CONFLICT (cliente_abreviatura, anio, mes, archivo_fuente, pagina)
                    DO UPDATE SET
                        tipo_detectado = EXCLUDED.tipo_detectado,
                        texto_extraido = EXCLUDED.texto_extraido,
                        fuente_texto = EXCLUDED.fuente_texto,
                        ruta_pagina_pdf = EXCLUDED.ruta_pagina_pdf,
                        es_reverso = EXCLUDED.es_reverso,
                        estado = 'separado'
                """, (
                    cliente,
                    year,
                    month,
                    asiento,
                    pdf.name,
                    page_num,
                    tipo_aprox,
                    text_clean[:10000],
                    fuente,
                    str(page_pdf),
                    reverso,
                ))

        procesados += 1

    print("\nSeparación finalizada.")
    print(f"Procesados: {procesados}")
    print(f"Omitidos ya extraídos: {omitidos}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)

    args = parser.parse_args()

    process(args.year, args.cliente, args.month)