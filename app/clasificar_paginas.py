import argparse

from core.db import get_cursor
from core.document_enricher import enrich_page


def process(year: int, cliente: str, month: int):
    cliente = cliente.upper()

    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT *
            FROM documentos_paginas
            WHERE estado = 'separado'
            AND cliente_abreviatura = %s
            AND anio = %s
            AND mes = %s
            ORDER BY archivo_fuente, pagina
        """, (cliente, year, month))
        rows = cur.fetchall()

    print(f"Páginas a clasificar: {len(rows)}")

    for row in rows:
        data = enrich_page(
            row["texto_extraido"] or "",
            row["archivo_fuente"],
            cliente
        )

        requiere_qr = (
            data["tipo"] == "guia_remision"
            and (
                not data["serie"]
                or not data["numero"]
                or not data["ruc"]
                or not data["clave_documental"]
            )
        )

        print(
            f"[{row['archivo_fuente']} P{row['pagina']}] "
            f"{data['tipo']} clave={data['clave_documental']}"
        )

        nuevo_estado = "clasificado"

        if data["tipo"] == "otro":
            texto = (row["texto_extraido"] or "").strip()
            if len(texto) > 30:
                nuevo_estado = "revision_manual"

        with get_cursor(commit=True) as (_, cur):
            cur.execute("""
                UPDATE documentos_paginas
                SET tipo_detectado = %s,
                    serie = %s,
                    numero = %s,
                    ruc_emisor = %s,
                    razon_social_emisor = %s,
                    orden_servicio = %s,
                    orden_compra = %s,
                    clave_documental = %s,
                    requiere_qr = %s,
                    qr_procesado = FALSE,
                    qr_raw = NULL,
                    qr_error = NULL,
                    banco_abreviatura = %s,
                    codigo_operacion = %s,
                    estado = %s
                WHERE id = %s
            """, (
                data["tipo"],
                data["serie"],
                data["numero"],
                data["ruc"],
                data["razon_social_emisor"],
                data["orden_servicio"],
                data["orden_compra"],
                data["clave_documental"],
                requiere_qr,
                data.get("banco"),
                data.get("codigo_operacion"),
                nuevo_estado,
                row["id"],
            ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)
    args = parser.parse_args()

    process(args.year, args.cliente, args.month)