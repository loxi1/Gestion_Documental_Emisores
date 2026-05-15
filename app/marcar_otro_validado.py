import argparse
import re
import shutil
from pathlib import Path


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
                    actualizado_en = NOW()
            """, (page_id,))

        if cur.rowcount == 0:
            print(f"[NO ACTUALIZADO] ID {page_id}. Verifica que sea tipo_detectado='otro' y tenga clave_documental.")
            return

    print(f"[OK] Otro validado como clasificado. ID={page_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)

    args = parser.parse_args()

    marcar(args.id)