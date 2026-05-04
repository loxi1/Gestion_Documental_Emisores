from __future__ import annotations

from pathlib import Path
from pypdf import PdfReader


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    path = Path(pdf_path)
    if not path.exists() or path.suffix.lower() != ".pdf":
        return ""
    try:
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception:
        return ""


def count_pages(pdf_path: str | Path) -> int:
    try:
        return len(PdfReader(str(pdf_path)).pages)
    except Exception:
        return 0
