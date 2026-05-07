import argparse
import re
import shutil
from pathlib import Path

import fitz

from core.ocr_runner import run_ocr


BASE_TRABAJO = Path("data/trabajo")
BASE_SALIDA = Path("data/salida")
TMP_DIR = Path("storage/tmp/oc")


def normalizar_texto(texto: str) -> str:
    texto = texto.upper()
    texto = texto.replace("Nº", "N°")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def extraer_asiento(nombre_archivo: str) -> str:
    match = re.search(r"^(04-\d{4})", nombre_archivo)
    return match.group(1) if match else "SIN_ASIENTO"


def detectar_oc(texto: str) -> tuple[str | None, str | None]:
    texto = normalizar_texto(texto)

    if "ORDEN DE SERVICIO" in texto:
        match = re.search(r"N[°º]?\s*:?\s*(\d{3,6})", texto)
        if match:
            return "ORDEN_SERVICIO", match.group(1).zfill(6)

    if "ORDEN DE COMPRA" in texto:
        match = re.search(r"ORDEN\s+DE\s+COMPRA\s*:?\s*(\d{3,6})", texto)
        if match:
            return "ORDEN_COMPRA", match.group(1).zfill(6)

    match = re.search(r"\bO[./-]?C\.?\s*:?\s*(\d{3,6})\b", texto)
    if match:
        return "ORDEN_COMPRA", match.group(1).zfill(6)

    return None, None


def extraer_pagina_pdf(pdf_path: Path, page_index: int, output_pdf: Path) -> None:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    src = fitz.open(pdf_path)
    dst = fitz.open()

    dst.insert_pdf(src, from_page=page_index, to_page=page_index)
    dst.save(output_pdf)

    dst.close()
    src.close()


def leer_texto_pdf(pdf_path: Path) -> str:
    texto = []

    with fitz.open(pdf_path) as doc:
        for page in doc:
            texto.append(page.get_text("text"))

    return "\n".join(texto)


def leer_texto_pagina_con_ocr(pdf_path: Path, page_index: int, asiento: str) -> tuple[str, Path]:
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    pagina_pdf = TMP_DIR / f"{asiento}_page_{page_index + 1}.pdf"
    pagina_ocr = TMP_DIR / f"{asiento}_page_{page_index + 1}_ocr.pdf"

    extraer_pagina_pdf(pdf_path, page_index, pagina_pdf)

    texto = leer_texto_pdf(pagina_pdf)

    if texto.strip():
        return texto, pagina_pdf

    ok = run_ocr(pagina_pdf, pagina_ocr)

    if not ok:
        return "", pagina_pdf

    texto_ocr = leer_texto_pdf(pagina_ocr)

    return texto_ocr, pagina_ocr


def guardar_paginas(pdf_path: Path, paginas: list[int], destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)

    src = fitz.open(pdf_path)
    dst = fitz.open()

    for page_index in paginas:
        dst.insert_pdf(src, from_page=page_index, to_page=page_index)

    dst.save(destino)

    dst.close()
    src.close()


def guardar_pdf_sin_paginas(pdf_path: Path, paginas_a_quitar: set[int], destino: Path) -> bool:
    destino.parent.mkdir(parents=True, exist_ok=True)

    src = fitz.open(pdf_path)
    dst = fitz.open()

    for i in range(src.page_count):
        if i not in paginas_a_quitar:
            dst.insert_pdf(src, from_page=i, to_page=i)

    if dst.page_count == 0:
        dst.close()
        src.close()
        return False

    dst.save(destino)

    dst.close()
    src.close()

    return True


def procesar_oc(year: int, cliente: str, month: int) -> None:
    pendientes = BASE_TRABAJO / str(year) / cliente / f"{month:02d}" / "pendientes"
    salida = BASE_SALIDA / str(year) / cliente / f"{month:02d}" / "provisional" / "orden_compra"

    pdfs = sorted(pendientes.glob("*.pdf"))

    print(f"Carpeta pendientes: {pendientes}")
    print(f"PDF encontrados: {len(pdfs)}")

    for idx, pdf in enumerate(pdfs, start=1):
        asiento = extraer_asiento(pdf.name)

        print(f"[{idx}/{len(pdfs)}] Revisando OC: {pdf.name}")

        paginas_detectadas: list[int] = []
        tipo_detectado = None
        oc_detectada = None

        with fitz.open(pdf) as doc:
            total_paginas = doc.page_count

        for page_index in range(total_paginas):
            texto, _ = leer_texto_pagina_con_ocr(pdf, page_index, asiento)
            tipo, oc = detectar_oc(texto)

            if tipo and oc:
                paginas_detectadas.append(page_index)
                tipo_detectado = tipo
                oc_detectada = oc
                print(f"  [OK] Página {page_index + 1}: {tipo_detectado} {oc_detectada}")

        if not paginas_detectadas:
            continue

        nombre_salida = f"{asiento} {tipo_detectado} {oc_detectada}.pdf"
        destino_oc = salida / nombre_salida

        guardar_paginas(pdf, paginas_detectadas, destino_oc)

        temp_pdf = pdf.with_suffix(".tmp.pdf")
        quedan_paginas = guardar_pdf_sin_paginas(pdf, set(paginas_detectadas), temp_pdf)

        if quedan_paginas:
            shutil.move(temp_pdf, pdf)
        else:
            pdf.unlink()

        print(f"[EXTRAIDO] {pdf.name} -> {nombre_salida}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)

    args = parser.parse_args()

    procesar_oc(args.year, args.cliente, args.month)


if __name__ == "__main__":
    main()