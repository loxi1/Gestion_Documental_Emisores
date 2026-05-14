import argparse
from core.db import get_cursor


def process(year: int, cliente: str, month: int):
    cliente = cliente.upper()

    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            UPDATE documentos_paginas dp
            SET tipo_detectado = r.tipo_detectado,
                clave_documental = r.clave_documental,
                serie = r.serie,
                numero = r.numero,
                ruc_emisor = r.ruc_emisor,
                razon_social_emisor = r.razon_social_emisor,
                orden_compra = r.orden_compra,
                orden_servicio = r.orden_servicio,
                banco_abreviatura = r.banco_abreviatura,
                codigo_operacion = r.codigo_operacion,
                requiere_qr = FALSE,
                qr_procesado = TRUE,
                qr_error = NULL,
                estado = 'clasificado'
            FROM reglas_clasificacion_manual r
            WHERE r.cliente_abreviatura = dp.cliente_abreviatura
              AND r.archivo_fuente = dp.archivo_fuente
              AND r.pagina = dp.pagina
              AND dp.cliente_abreviatura = %s
              AND dp.anio = %s
              AND dp.mes = %s
        """, (cliente, year, month))

        print(f"[OK] Reglas manuales aplicadas: {cur.rowcount}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)

    args = parser.parse_args()

    process(args.year, args.cliente, args.month)