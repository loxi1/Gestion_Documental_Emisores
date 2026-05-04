from pathlib import Path
import fitz

from core.config import OCR_TMP_DIR, USE_OCR
from core.pdf_text import extract_text_from_pdf
from core.ocr_service import run_ocr
from core.classifier import extract_basic_fields


def extract_single_page_pdf(source_pdf: Path, page_index: int, output_pdf: Path):
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    src = fitz.open(source_pdf)
    dst = fitz.open()

    dst.insert_pdf(src, from_page=page_index, to_page=page_index)
    dst.save(output_pdf)

    dst.close()
    src.close()


def analizar_paginas_pdf(pdf_path: Path) -> list[dict]:
    result = []

    doc = fitz.open(pdf_path)
    total_pages = doc.page_count
    doc.close()

    for index in range(total_pages):
        temp_page = OCR_TMP_DIR / f"{pdf_path.stem}_page_{index + 1}.pdf"
        extract_single_page_pdf(pdf_path, index, temp_page)

        text = extract_text_from_pdf(temp_page)
        fuente = "pdf_text"

        if not text.strip() and USE_OCR:
            ocr_page = OCR_TMP_DIR / f"{pdf_path.stem}_page_{index + 1}_ocr.pdf"
            if run_ocr(temp_page, ocr_page):
                text = extract_text_from_pdf(ocr_page)
                fuente = "ocr"

        fields = extract_basic_fields(text, pdf_path.name)

        result.append({
            "page": index + 1,
            "text": text,
            "fields": fields,
            "tipo_documental": fields.get("tipo_documental"),
            "oc": fields.get("oc") or fields.get("orden_compra") or fields.get("oc_numero"),
            "fuente": fuente,
            "temp_pdf": temp_page,
        })

    return result