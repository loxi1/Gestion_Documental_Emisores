import argparse
import shutil
from pathlib import Path

from core.db import get_cursor

BASE_TRABAJO = Path("data/trabajo")
BASE_SALIDA = Path("data/salida")
BASE_TMP = Path("storage/tmp/pages")


def limpiar_lote(year: int, cliente: str, month: int):
    cliente = cliente.upper()
    month_str = f"{month:02d}"

    print(f"Limpiando lote: {year}/{cliente}/{month_str}")

    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            DELETE FROM documentos_agrupados
            WHERE cliente_abreviatura = %s
              AND anio = %s
              AND mes = %s
        """, (cliente, year, month))

        cur.execute("""
            DELETE FROM documentos_paginas
            WHERE cliente_abreviatura = %s
              AND anio = %s
              AND mes = %s
        """, (cliente, year, month))

        cur.execute("""
            DELETE FROM documentos_extraidos
            WHERE lote_id IN (
                SELECT id
                FROM lotes_procesamiento
                WHERE cliente_abreviatura = %s
                  AND anio = %s
                  AND mes = %s
            )
        """, (cliente, year, month))

    rutas = [
        BASE_TRABAJO / str(year) / cliente / month_str,
        BASE_TMP / str(year) / cliente / month_str,
        BASE_SALIDA / str(year) / cliente / month_str / "provisional",
        BASE_SALIDA / str(year) / cliente / month_str / "con_oc",
        BASE_SALIDA / str(year) / cliente / month_str / "sin_oc",
        BASE_SALIDA / str(year) / cliente / month_str / "revision",
    ]

    for ruta in rutas:
        if ruta.exists():
            shutil.rmtree(ruta)
            print(f"[BORRADO] {ruta}")

    print("Limpieza finalizada.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)
    args = parser.parse_args()

    limpiar_lote(args.year, args.cliente, args.month)