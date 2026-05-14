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

        with get_cursor(commit=True) as (_, cur):
            cur.execute("""
                INSERT INTO reglas_clasificacion_manual (
                    cliente_abreviatura,
                    archivo_fuente,
                    pagina,
                    tipo_detectado,
                    clave_documental,
                    serie,
                    numero,
                    ruc_emisor,
                    razon_social_emisor,
                    orden_compra,
                    orden_servicio,
                    banco_abreviatura,
                    codigo_operacion
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cliente_abreviatura, archivo_fuente, pagina)
                DO UPDATE SET
                    tipo_detectado = EXCLUDED.tipo_detectado,
                    clave_documental = EXCLUDED.clave_documental,
                    serie = EXCLUDED.serie,
                    numero = EXCLUDED.numero,
                    ruc_emisor = EXCLUDED.ruc_emisor,
                    razon_social_emisor = EXCLUDED.razon_social_emisor,
                    orden_compra = EXCLUDED.orden_compra,
                    orden_servicio = EXCLUDED.orden_servicio,
                    banco_abreviatura = EXCLUDED.banco_abreviatura,
                    codigo_operacion = EXCLUDED.codigo_operacion,
                    actualizado_en = NOW()
            """, (
                row["cliente_abreviatura"],
                row["archivo_fuente"],
                row["pagina"],
                tipo,
                clave,
                serie,
                numero,
                ruc,
                razon,
                orden_compra,
                orden_servicio,
                banco,
                codigo,
            ))

        print(f"[OK] Reglas manuales aplicadas a páginas: {cur.rowcount}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)
    args = parser.parse_args()

    process(args.year, args.cliente, args.month)