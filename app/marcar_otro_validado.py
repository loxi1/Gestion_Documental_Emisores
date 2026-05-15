import argparse

from core.db import get_cursor


def marcar(page_id: int):
    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            UPDATE documentos_paginas
            SET estado = 'clasificado',
                requiere_qr = FALSE,
                qr_procesado = TRUE,
                qr_error = NULL
            WHERE id = %s
              AND tipo_detectado = 'otro'
              AND clave_documental IS NOT NULL
        """, (page_id,))

        if cur.rowcount == 0:
            print(
                f"[NO ACTUALIZADO] ID {page_id}. "
                "Verifica que sea tipo_detectado='otro' y tenga clave_documental."
            )
            return

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
            SELECT
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
            FROM documentos_paginas
            WHERE id = %s
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
        """, (page_id,))

    print(f"[OK] Otro validado como clasificado. ID={page_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    args = parser.parse_args()

    marcar(args.id)