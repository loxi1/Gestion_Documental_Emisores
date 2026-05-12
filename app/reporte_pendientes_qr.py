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
                pagina,
                archivo_fuente,
                tipo_detectado,
                serie,
                numero,
                ruc_emisor,
                clave_documental,
                qr_error,
                texto_extraido
            FROM documentos_paginas
            WHERE cliente_abreviatura = %s
            AND anio = %s
            AND mes = %s
            AND requiere_qr = TRUE
            ORDER BY asiento_contable, pagina
        """, (cliente, year, month))

        rows = cur.fetchall()

    print(f"\nPendientes QR: {len(rows)}\n")

    for row in rows:
        ruta = (
            f"{row['archivo_fuente'].replace('.pdf', '')}_P{row['pagina']}.pdf"
        )

        motivo = []
        sugerencia = []

        texto = (row["texto_extraido"] or "").upper()

        if not row["serie"]:
            motivo.append("sin_serie")

        if not row["numero"]:
            motivo.append("sin_numero")

        if not row["ruc_emisor"]:
            motivo.append("sin_ruc")

        if not row["clave_documental"]:
            motivo.append("sin_clave")

        if row["qr_error"]:
            motivo.append(row["qr_error"])

        # heurísticas
        if "GUIA" in texto or "GUÍA" in texto:
            sugerencia.append("validar_guia")

        if "MOTIVO DEL TRASLADO" in texto:
            sugerencia.append("guia_remision")

        if "DATOS DEL TRANSPORTISTA" in texto:
            sugerencia.append("guia_con_transporte")

        if "REPRESENTACION IMPRESA" in texto:
            sugerencia.append("pdf_sunat")

        if "QR" not in texto:
            sugerencia.append("qr_no_visible")

        if f"_P{row['pagina']}" in ruta and row["pagina"] > 1:
            sugerencia.append("anexo_o_pagina_interna")

        print("=" * 120)

        print(
            f"[ID {row['id']}] "
            f"Asiento={row['asiento_contable']} "
            f"P{row['pagina']} "
            f"Tipo={row['tipo_detectado']}"
        )

        print(f"Archivo : {row['archivo_fuente']}")
        print(f"Página  : {ruta}")

        print(
            f"Datos   : "
            f"serie={row['serie']} "
            f"numero={row['numero']} "
            f"ruc={row['ruc_emisor']}"
        )

        print(f"Clave   : {row['clave_documental']}")
        print(f"Motivo  : {', '.join(motivo) if motivo else '-'}")
        print(f"Sugerir : {', '.join(sugerencia) if sugerencia else '-'}")

    print("\nReporte finalizado.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)

    args = parser.parse_args()

    process(
        year=args.year,
        cliente=args.cliente,
        month=args.month,
    )