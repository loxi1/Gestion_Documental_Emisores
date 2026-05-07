import argparse
import shutil
from pathlib import Path

BASE_ENTRADA = Path("data/entrada")
BASE_TRABAJO = Path("data/trabajo")


def limpiar_carpeta(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copiar_a_trabajo(year: int, cliente: str, month: int, limpiar: bool = True):
    origen = BASE_ENTRADA / str(year) / cliente / f"{month:02d}"
    base_destino = BASE_TRABAJO / str(year) / cliente / f"{month:02d}"

    destino_originales = base_destino / "originales"
    destino_pendientes = base_destino / "pendientes"

    if limpiar:
        limpiar_carpeta(destino_originales)
        limpiar_carpeta(destino_pendientes)
    else:
        destino_originales.mkdir(parents=True, exist_ok=True)
        destino_pendientes.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(origen.glob("*.pdf"))

    print(f"Origen: {origen}")
    print(f"Destino originales: {destino_originales}")
    print(f"Destino pendientes: {destino_pendientes}")
    print(f"PDF encontrados: {len(pdfs)}")

    for pdf in pdfs:
        shutil.copy2(pdf, destino_originales / pdf.name)
        shutil.copy2(pdf, destino_pendientes / pdf.name)
        print(f"[OK] {pdf.name}")

    print("Copia finalizada.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--no-clean", action="store_true")

    args = parser.parse_args()

    copiar_a_trabajo(
        year=args.year,
        cliente=args.cliente,
        month=args.month,
        limpiar=not args.no_clean,
    )