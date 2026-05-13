import argparse
import shutil
from pathlib import Path

from core.db import get_cursor

BASE_TRABAJO = Path("data/trabajo")
BASE_SALIDA = Path("data/salida")
BASE_TMP = Path("storage/tmp/pages")
BASE_QR_DEBUG = Path("storage/tmp/qr_debug")


def borrar_si_existe(path: Path):
    if path.exists():
        shutil.rmtree(path)
        print(f"[BORRADO] {path}")


def limpiar_lote(year: int, cliente: str, month: int):
    cliente = cliente.upper()
    month_str = f"{month:02d}"

    print("=" * 80)
    print(f"LIMPIANDO LOTE {year}/{cliente}/{month_str}")
    print("=" * 80)

    with get_cursor(commit=True) as (_, cur):

        # documentos agrupados
        cur.execute("""
            DELETE FROM documentos_agrupados
            WHERE cliente_abreviatura = %s
              AND anio = %s
              AND mes = %s
        """, (cliente, year, month))

        print(f"[DB] documentos_agrupados eliminados: {cur.rowcount}")

        # documentos extraidos
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

        print(f"[DB] documentos_extraidos eliminados: {cur.rowcount}")

        # reset paginas
        cur.execute("""
            UPDATE documentos_paginas
            SET estado = 'separado',
                tipo_detectado = NULL,
                serie = NULL,
                numero = NULL,
                ruc_emisor = NULL,
                razon_social_emisor = NULL,
                orden_servicio = NULL,
                orden_compra = NULL,
                clave_documental = NULL,
                requiere_qr = FALSE,
                qr_procesado = FALSE,
                qr_raw = NULL,
                qr_error = NULL,
                banco_abreviatura = NULL,
                codigo_operacion = NULL
            WHERE cliente_abreviatura = %s
              AND anio = %s
              AND mes = %s
        """, (cliente, year, month))

        print(f"[DB] documentos_paginas reseteados: {cur.rowcount}")

    rutas = [
        BASE_TRABAJO / str(year) / cliente / month_str,
        BASE_TMP / str(year) / cliente / month_str,
        BASE_QR_DEBUG / str(year) / cliente / month_str,

        BASE_SALIDA / str(year) / cliente / month_str / "provisional",
        BASE_SALIDA / str(year) / cliente / month_str / "con_oc",
        BASE_SALIDA / str(year) / cliente / month_str / "sin_oc",
        BASE_SALIDA / str(year) / cliente / month_str / "revision",
    ]

    for ruta in rutas:
        borrar_si_existe(ruta)

    print("=" * 80)
    print("LIMPIEZA FINALIZADA")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)

    args = parser.parse_args()

    limpiar_lote(
        year=args.year,
        cliente=args.cliente,
        month=args.month,
    )