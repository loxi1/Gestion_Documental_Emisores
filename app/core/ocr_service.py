from __future__ import annotations

from pathlib import Path
import subprocess

from core.config import USE_OCR


def run_ocr(input_pdf: str | Path, output_pdf: str | Path) -> bool:
    if not USE_OCR:
        return False
    input_pdf = Path(input_pdf)
    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    try:
        cmd = ["ocrmypdf", "--force-ocr", "--skip-text", "--deskew", "--rotate-pages", str(input_pdf), str(output_pdf)]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return proc.returncode == 0 and output_pdf.exists()
    except Exception:
        return False
