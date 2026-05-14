import argparse
from core.db import get_cursor


def process(year: int, cliente: str, month: int):
    cliente = cliente.upper()

    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT
                de.id,
                de.asiento_contable,
                de.tipo_documental,
                de.serie,
                de.numero,
                de.ruc_emisor,
                de.razon_social_emisor,
                de.nombre_provisional,
                de.ruta_provisional,
                de.nombre_final,
                de.ruta_final,
                de.estado,
                de.requiere_revision,
                de.motivo_revision
            FROM documentos_extraidos de
            INNER JOIN lotes_procesamiento lp ON lp.id = de.lote_id
            WHERE lp.cliente_abreviatura = %s
              AND lp.anio = %s
              AND lp.mes = %s
              AND (
                    de.requiere_revision = TRUE
                    OR de.estado = 'revision'
                  )
            ORDER BY de.asiento_contable, de.id
        """, (cliente, year, month))

        rows = cur.fetchall()

    print(f"\nExtraídos en revisión: {len(rows)}\n")

    for row in rows:
        print("=" * 110)
        print(f"ID        : {row['id']}")
        print(f"Asiento   : {row['asiento_contable']}")
        print(f"Tipo      : {row['tipo_documental']}")
        print(f"Serie     : {row['serie']}")
        print(f"Número    : {row['numero']}")
        print(f"RUC       : {row['ruc_emisor']}")
        print(f"Razón     : {row['razon_social_emisor']}")
        print(f"Origen    : {row['nombre_provisional']}")
        print(f"Ruta orig : {row['ruta_provisional']}")
        print(f"Final     : {row['nombre_final']}")
        print(f"Ruta final: {row['ruta_final']}")
        print(f"Estado    : {row['estado']}")
        print(f"Motivo    : {row['motivo_revision']}")
        print()
        print(f"Editar    : python app/editar_extraido_manual.py --id {row['id']}")
        print(f"Otro      : python app/marcar_extraido_otro.py --id {row['id']}")

    print("\nReporte finalizado.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)
    args = parser.parse_args()

    process(args.year, args.cliente, args.month)