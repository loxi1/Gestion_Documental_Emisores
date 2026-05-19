import argparse
import re
import shutil
import unicodedata
from pathlib import Path

from core.db import get_cursor

BASE_ENTRADA = Path("data/entrada")
BASE_TRABAJO = Path("data/trabajo")


def clean_name(value: str | None) -> str:
    value = value or "SIN_NOMBRE"
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    return value.strip("_").upper() or "SIN_NOMBRE"


def asiento_to_int(asiento: str | None) -> int | None:
    if not asiento:
        return None

    m = re.search(r"(\d{2})-(\d{4})", asiento)

    if not m:
        return None

    return int(m.group(2))


def format_asiento(prefix: int, numero: int) -> str:
    return f"{prefix:02d}-{numero:04d}"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    base = path.with_suffix("")
    ext = path.suffix
    i = 2

    while True:
        candidate = Path(f"{base}_{i}{ext}")
        if not candidate.exists():
            return candidate
        i += 1


def get_max_asiento(cliente: str, year: int, month: int) -> int:
    """
    Busca el mayor correlativo ya usado en el mes.
    Considera documentos_agrupados, documentos_paginas, documentos_extraidos
    y archivos_preclasificados.
    """
    month_prefix = f"{month:02d}-"

    with get_cursor() as (_, cur):
        cur.execute("""
            WITH asientos AS (
                SELECT asiento_contable AS asiento
                FROM documentos_agrupados
                WHERE cliente_abreviatura = %s
                  AND anio = %s
                  AND mes = %s
                  AND asiento_contable LIKE %s

                UNION ALL

                SELECT asiento_contable AS asiento
                FROM documentos_paginas
                WHERE cliente_abreviatura = %s
                  AND anio = %s
                  AND mes = %s
                  AND asiento_contable LIKE %s

                UNION ALL

                SELECT de.asiento_contable AS asiento
                FROM documentos_extraidos de
                INNER JOIN lotes_procesamiento lp
                    ON lp.id = de.lote_id
                WHERE lp.cliente_abreviatura = %s
                  AND lp.anio = %s
                  AND lp.mes = %s
                  AND de.asiento_contable LIKE %s

                UNION ALL

                SELECT asiento_generado AS asiento
                FROM archivos_preclasificados
                WHERE cliente_abreviatura = %s
                  AND anio = %s
                  AND mes = %s
                  AND asiento_generado LIKE %s
            )
            SELECT COALESCE(
                MAX(
                    CAST(
                        SUBSTRING(asiento FROM '\\d{2}-(\\d{4})')
                        AS INTEGER
                    )
                ),
                0
            ) AS max_num
            FROM asientos
        """, (
            cliente, year, month, f"{month_prefix}%",
            cliente, year, month, f"{month_prefix}%",
            cliente, year, month, f"{month_prefix}%",
            cliente, year, month, f"{month_prefix}%",
        ))

        row = cur.fetchone()

    return int(row["max_num"] or 0)


def registrar_preclasificado(
    cliente: str,
    year: int,
    month: int,
    asiento: str,
    origen: Path,
    destino: Path,
):
    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            INSERT INTO archivos_preclasificados (
                cliente_abreviatura,
                anio,
                mes,
                asiento_generado,
                nombre_original,
                nombre_generado,
                ruta_original,
                ruta_generada,
                estado
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'preclasificado')
            ON CONFLICT (cliente_abreviatura, anio, mes, nombre_original)
            DO UPDATE SET
                asiento_generado = EXCLUDED.asiento_generado,
                nombre_generado = EXCLUDED.nombre_generado,
                ruta_original = EXCLUDED.ruta_original,
                ruta_generada = EXCLUDED.ruta_generada,
                estado = 'preclasificado',
                actualizado_en = NOW()
        """, (
            cliente,
            year,
            month,
            asiento,
            origen.name,
            destino.name,
            str(origen),
            str(destino),
        ))


def preclasificar(year: int, cliente: str, month: int, asiento_prefix: int | None = None, mover: bool = False):
    cliente = cliente.upper()
    month_str = f"{month:02d}"

    entrada = BASE_ENTRADA / str(year) / cliente / month_str / "sin_nombre"
    pendientes = BASE_TRABAJO / str(year) / cliente / month_str / "pendientes"

    pendientes.mkdir(parents=True, exist_ok=True)

    if not entrada.exists():
        print(f"[ERROR] No existe carpeta: {entrada}")
        return

    pdfs = sorted(entrada.glob("*.pdf"))

    print(f"Entrada sin nombre : {entrada}")
    print(f"Destino pendientes : {pendientes}")
    print(f"PDF encontrados    : {len(pdfs)}")

    prefix = asiento_prefix if asiento_prefix is not None else month

    max_num = get_max_asiento(cliente, year, month)
    siguiente = max_num + 1

    print(f"Mayor asiento actual: {format_asiento(prefix, max_num) if max_num else 'NINGUNO'}")
    print(f"Siguiente asiento   : {format_asiento(prefix, siguiente)}")

    procesados = 0
    omitidos = 0

    for pdf in pdfs:
        asiento = format_asiento(prefix, siguiente)
        ref = clean_name(pdf.stem)

        nuevo_nombre = f"{asiento} {cliente} SIN_NOMBRE {ref}.pdf"
        destino = unique_path(pendientes / nuevo_nombre)

        if destino.exists():
            print(f"[OMITIDO] Ya existe destino: {destino.name}")
            omitidos += 1
            continue

        if mover:
            shutil.move(str(pdf), str(destino))
            accion = "MOVIDO"
        else:
            shutil.copy2(str(pdf), str(destino))
            accion = "COPIADO"

        registrar_preclasificado(
            cliente=cliente,
            year=year,
            month=month,
            asiento=asiento,
            origen=pdf,
            destino=destino,
        )

        print(f"[{accion}] {pdf.name} -> {destino.name}")

        procesados += 1
        siguiente += 1

    print("\nPreclasificación finalizada.")
    print(f"Procesados: {procesados}")
    print(f"Omitidos  : {omitidos}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--asiento-prefix", type=int, default=None)

    parser.add_argument(
        "--mover",
        action="store_true",
        help="Mueve los archivos desde sin_nombre. Si no se usa, copia.",
    )

    args = parser.parse_args()

    preclasificar(
        year=args.year,
        cliente=args.cliente,
        month=args.month,
        asiento_prefix=args.asiento_prefix,
        mover=args.mover,
    )