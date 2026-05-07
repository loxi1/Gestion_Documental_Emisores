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
    src = fitz.open(source_pdf)
    dst = fitz.open()
    dst.insert_pdf(src, from_page=page_index, to_page=page_index)
    dst.save(output_pdf)
    dst.close()
    src.close()


def extract_text(pdf_path: Path) -> str:
    with fitz.open(pdf_path) as doc:
        return "\n".join(page.get_text("text") for page in doc)


def is_reverso_page(text: str) -> bool:
    t = normalize(text)
    return len(t) < 80 or ("USUARIO:" in t and len(t) < 300)


def process(year: int, cliente: str, month: int):
    pendientes = BASE_TRABAJO / str(year) / cliente / f"{month:02d}" / "pendientes"
    pdfs = sorted(pendientes.glob("*.pdf"))

    print(f"Pendientes: {pendientes}")
    print(f"PDF encontrados: {len(pdfs)}")

    for pdf in pdfs:
        asiento = extract_asiento(pdf.name)

        with fitz.open(pdf) as doc:
            total_pages = doc.page_count

        print(f"\n[PDF] {pdf.name} ({total_pages} páginas)")

        for idx in range(total_pages):
            page_pdf = TMP_DIR / f"{pdf.stem}_P{idx + 1}.pdf"
            page_ocr = TMP_DIR / f"{pdf.stem}_P{idx + 1}_OCR.pdf"
            ruta_pagina_pdf = str(page_pdf)

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

            print(f"  Página {idx + 1}: tipo_aprox={tipo_aprox} reverso={reverso} fuente={fuente}")

            with get_cursor(commit=True) as (_, cur):
                cur.execute("""
                    INSERT INTO documentos_paginas (
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
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'separado')
                    ON CONFLICT (archivo_fuente, pagina) DO UPDATE
                    SET tipo_detectado = EXCLUDED.tipo_detectado,
                        texto_extraido = EXCLUDED.texto_extraido,
                        fuente_texto = EXCLUDED.fuente_texto,
                        ruta_pagina_pdf = EXCLUDED.ruta_pagina_pdf,
                        es_reverso = EXCLUDED.es_reverso,
                        estado = 'separado'
                """, (
                    asiento,
                    pdf.name,
                    idx + 1,
                    tipo_aprox,
                    text_clean[:10000],
                    fuente,
                    ruta_pagina_pdf,
                    reverso,
                ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)
    args = parser.parse_args()

    process(args.year, args.cliente, args.month)