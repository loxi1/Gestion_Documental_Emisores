import argparse
from pathlib import Path

from core.db import get_cursor


def process(year: int, cliente: str, month: int):
    cliente = cliente.upper()

    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT
                id,
                asiento_contable,
                archivo_fuente,
                pagina,
                tipo_detectado,
                clave_documental,
                orden_compra,
                orden_servicio,
                ruc_emisor,
                serie,
                numero,
                ruta_pagina_pdf
            FROM documentos_paginas
            WHERE cliente_abreviatura = %s
              AND anio = %s
              AND mes = %s
              AND (
                    estado = 'revision_manual'
                    OR tipo_detectado = 'otro'
                  )
            ORDER BY asiento_contable, pagina
        """, (cliente, year, month))

        rows = cur.fetchall()

    print(f"\nRegistros para revisar: {len(rows)}\n")

    for row in rows:
        ruta = Path(row["ruta_pagina_pdf"]).name if row["ruta_pagina_pdf"] else ""

        print("=" * 120)
        print(f"ID       : {row['id']}")
        print(f"Asiento  : {row['asiento_contable']}")
        print(f"Archivo  : {row['archivo_fuente']}")
        print(f"Página   : {row['pagina']}")
        print(f"Ruta     : {ruta}")
        print(f"Tipo     : {row['tipo_detectado']}")
        print(f"Clave    : {row['clave_documental']}")
        print(f"OC       : {row['orden_compra']}")
        print(f"OS       : {row['orden_servicio']}")
        print(f"RUC      : {row['ruc_emisor']}")
        print(f"Serie    : {row['serie']}")
        print(f"Número   : {row['numero']}")
        print()
        print(f"Editar   : python app/editar_pagina_manual.py --id {row['id']}")
        print(f"Validar  : python app/marcar_otro_validado.py --id {row['id']}")

    print("\nReporte finalizado.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)

    args = parser.parse_args()

    process(args.year, args.cliente, args.month)