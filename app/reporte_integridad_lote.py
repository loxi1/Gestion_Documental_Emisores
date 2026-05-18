import argparse
from pathlib import Path

from core.db import get_cursor

BASE_TRABAJO = Path("data/trabajo")
BASE_SALIDA = Path("data/salida")
BASE_TMP = Path("storage/tmp/pages")


def count_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for p in path.rglob("*") if p.is_file())


def header(title: str):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def scalar(cur, sql: str, params: tuple) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(list(row.values())[0] or 0)


def rows(cur, sql: str, params: tuple):
    cur.execute(sql, params)
    return cur.fetchall()


def process(year: int, cliente: str, month: int):
    cliente = cliente.upper()
    month_str = f"{month:02d}"

    salida_mes = BASE_SALIDA / str(year) / cliente / month_str
    trabajo_mes = BASE_TRABAJO / str(year) / cliente / month_str
    tmp_mes = BASE_TMP / str(year) / cliente / month_str

    con_oc_dir = salida_mes / "con_oc"
    sin_oc_dir = salida_mes / "sin_oc"
    revision_dir = salida_mes / "revision"
    revision_manual_dir = salida_mes / "revision_manual"
    provisional_dir = salida_mes / "provisional"
    pendientes_dir = trabajo_mes / "pendientes"

    with get_cursor() as (_, cur):
        header(f"REPORTE INTEGRIDAD LOTE {year}/{cliente}/{month_str}")

        documentos_extraidos_total = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_extraidos de
            INNER JOIN lotes_procesamiento lp ON lp.id = de.lote_id
            WHERE lp.cliente_abreviatura=%s
              AND lp.anio=%s
              AND lp.mes=%s
        """, (cliente, year, month))

        documentos_extraidos_revision = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_extraidos de
            INNER JOIN lotes_procesamiento lp ON lp.id = de.lote_id
            WHERE lp.cliente_abreviatura=%s
              AND lp.anio=%s
              AND lp.mes=%s
              AND (
                    de.estado = 'revision'
                    OR de.requiere_revision = TRUE
                  )
        """, (cliente, year, month))

        documentos_paginas_total = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_paginas
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
        """, (cliente, year, month))

        paginas_para_agrupar = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_paginas
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
              AND estado='clasificado'
        """, (cliente, year, month))

        paginas_agrupadas = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_paginas
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
              AND estado='agrupado'
        """, (cliente, year, month))

        paginas_pendientes_reales = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_paginas
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
              AND estado IN (
                    'separado',
                    'revision_manual',
                    'revision_manual_qr'
              )
        """, (cliente, year, month))

        paginas_sin_clave = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_paginas
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
              AND estado IN ('clasificado', 'agrupado')
              AND clave_documental IS NULL
        """, (cliente, year, month))

        qr_pendientes = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_paginas
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
              AND requiere_qr = TRUE
              AND qr_procesado = FALSE
        """, (cliente, year, month))

        documentos_agrupados_total = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_agrupados
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
        """, (cliente, year, month))

        agrupados_con_oc = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_agrupados
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
              AND estado='distribuido_con_oc'
        """, (cliente, year, month))

        agrupados_sin_oc = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_agrupados
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
              AND estado='distribuido_sin_oc'
        """, (cliente, year, month))

        agrupados_revision = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_agrupados
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
              AND estado='revision'
        """, (cliente, year, month))

        agrupados_no_distribuidos = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_agrupados
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
              AND estado NOT LIKE 'distribuido%%'
        """, (cliente, year, month))

        distribuidos_sin_ruta = scalar(cur, """
            SELECT COUNT(*)
            FROM documentos_agrupados
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
              AND estado LIKE 'distribuido%%'
              AND (
                    ruta_final IS NULL
                    OR TRIM(ruta_final) = ''
                  )
        """, (cliente, year, month))

        db_distribuido = agrupados_con_oc + agrupados_sin_oc

        fs_con_oc = count_files(con_oc_dir)
        fs_sin_oc = count_files(sin_oc_dir)
        fs_revision = count_files(revision_dir) + count_files(revision_manual_dir)
        fs_provisional = count_files(provisional_dir)
        fs_pendientes = count_files(pendientes_dir)
        fs_tmp_pages = count_files(tmp_mes)
        fs_final = fs_con_oc + fs_sin_oc

        header("RESUMEN DB")
        print(f"documentos_extraidos total      : {documentos_extraidos_total}")
        print(f"documentos_extraidos revision   : {documentos_extraidos_revision}")
        print(f"documentos_paginas total        : {documentos_paginas_total}")
        print(f"paginas agrupadas               : {paginas_agrupadas}")
        print(f"paginas listas para agrupar     : {paginas_para_agrupar}")
        print(f"paginas pendientes reales       : {paginas_pendientes_reales}")
        print(f"paginas sin clave               : {paginas_sin_clave}")
        print(f"QR pendientes                   : {qr_pendientes}")
        print(f"documentos_agrupados total      : {documentos_agrupados_total}")
        print(f"agrupados con OC/OS             : {agrupados_con_oc}")
        print(f"agrupados sin OC/OS             : {agrupados_sin_oc}")
        print(f"agrupados revision              : {agrupados_revision}")
        print(f"agrupados no distribuidos       : {agrupados_no_distribuidos}")

        header("RESUMEN FILESYSTEM")
        print(f"con_oc físicos                  : {fs_con_oc}")
        print(f"sin_oc físicos                  : {fs_sin_oc}")
        print(f"revision físicos                : {fs_revision}")
        print(f"provisional físicos             : {fs_provisional}")
        print(f"pendientes físicos              : {fs_pendientes}")
        print(f"tmp pages físicos               : {fs_tmp_pages}")

        header("VALIDACIÓN PRINCIPAL")
        print(f"DB distribuido                  : {db_distribuido}")
        print(f"FS final con_oc + sin_oc        : {fs_final}")

        observaciones = []

        if db_distribuido == fs_final:
            print("[OK] Conteo DB distribuido coincide con archivos finales.")
        else:
            print("[ERROR] Conteo DB distribuido NO coincide con archivos finales.")
            observaciones.append("DB distribuido no coincide con filesystem final")

        if documentos_extraidos_revision > 0:
            observaciones.append("Hay documentos_extraidos en revisión")

        if paginas_pendientes_reales > 0:
            observaciones.append("Hay páginas en separado/revision_manual/revision_manual_qr")

        if paginas_para_agrupar > 0:
            observaciones.append("Hay páginas clasificadas pendientes de agrupar")

        if paginas_sin_clave > 0:
            observaciones.append("Hay páginas agrupadas/clasificadas sin clave documental")

        if qr_pendientes > 0:
            observaciones.append("Hay QR pendientes")

        if agrupados_no_distribuidos > 0:
            observaciones.append("Hay documentos agrupados no distribuidos")

        if distribuidos_sin_ruta > 0:
            observaciones.append("Hay distribuidos sin ruta_final")

        if fs_revision > 0:
            observaciones.append("Hay archivos físicos en revision/revision_manual")

        if fs_provisional > 0:
            observaciones.append("Hay archivos físicos en provisional")

        header("ESTADOS documentos_agrupados")
        for row in rows(cur, """
            SELECT estado, COUNT(*) AS total
            FROM documentos_agrupados
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
            GROUP BY estado
            ORDER BY estado
        """, (cliente, year, month)):
            print(f"{row['estado']}: {row['total']}")

        header("ESTADOS documentos_paginas")
        for row in rows(cur, """
            SELECT estado, COUNT(*) AS total
            FROM documentos_paginas
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
            GROUP BY estado
            ORDER BY estado
        """, (cliente, year, month)):
            print(f"{row['estado']}: {row['total']}")

        header("TIPOS documentos_agrupados")
        for row in rows(cur, """
            SELECT tipo_documental, COUNT(*) AS total
            FROM documentos_agrupados
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
            GROUP BY tipo_documental
            ORDER BY tipo_documental
        """, (cliente, year, month)):
            print(f"{row['tipo_documental']}: {row['total']}")

        header("DUPLICADOS NO OTRO")
        duplicados = rows(cur, """
            SELECT clave_documental, COUNT(*) AS total
            FROM documentos_agrupados
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
              AND tipo_documental <> 'OTRO'
            GROUP BY clave_documental
            HAVING COUNT(*) > 1
            ORDER BY clave_documental
        """, (cliente, year, month))

        if not duplicados:
            print("[OK] No hay claves duplicadas no-OTRO.")
        else:
            for row in duplicados:
                print(f"[DUP] {row['clave_documental']} -> {row['total']}")
            observaciones.append("Hay claves duplicadas no-OTRO")

        header("DUPLICADOS POR ASIENTO")
        duplicados_asiento = rows(cur, """
            SELECT asiento_contable, clave_documental, COUNT(*) AS total
            FROM documentos_agrupados
            WHERE cliente_abreviatura=%s
              AND anio=%s
              AND mes=%s
              AND tipo_documental <> 'OTRO'
            GROUP BY asiento_contable, clave_documental
            HAVING COUNT(*) > 1
            ORDER BY asiento_contable, clave_documental
        """, (cliente, year, month))

        if not duplicados_asiento:
            print("[OK] No hay duplicados dentro del mismo asiento.")
        else:
            for row in duplicados_asiento:
                print(
                    f"[DUP_ASIENTO] {row['asiento_contable']} "
                    f"{row['clave_documental']} -> {row['total']}"
                )
            observaciones.append("Hay duplicados dentro del mismo asiento")

        header("DISTRIBUIDOS SIN RUTA_FINAL")
        if distribuidos_sin_ruta == 0:
            print("[OK] Todos los distribuidos tienen ruta_final.")
        else:
            for row in rows(cur, """
                SELECT id, asiento_contable, tipo_documental, clave_documental
                FROM documentos_agrupados
                WHERE cliente_abreviatura=%s
                  AND anio=%s
                  AND mes=%s
                  AND estado LIKE 'distribuido%%'
                  AND (
                        ruta_final IS NULL
                        OR TRIM(ruta_final) = ''
                      )
                ORDER BY id
                LIMIT 50
            """, (cliente, year, month)):
                print(
                    f"[SIN_RUTA] id={row['id']} "
                    f"{row['asiento_contable']} "
                    f"{row['tipo_documental']} "
                    f"{row['clave_documental']}"
                )

        header("NO DISTRIBUIDOS")
        if agrupados_no_distribuidos == 0:
            print("[OK] No hay agrupados pendientes de distribución.")
        else:
            for row in rows(cur, """
                SELECT id, asiento_contable, tipo_documental, clave_documental, estado
                FROM documentos_agrupados
                WHERE cliente_abreviatura=%s
                  AND anio=%s
                  AND mes=%s
                  AND estado NOT LIKE 'distribuido%%'
                ORDER BY id
                LIMIT 50
            """, (cliente, year, month)):
                print(
                    f"[NO_DISTRIBUIDO] id={row['id']} "
                    f"{row['asiento_contable']} "
                    f"{row['tipo_documental']} "
                    f"{row['clave_documental']} "
                    f"estado={row['estado']}"
                )

        header("PÁGINAS PENDIENTES REALES")
        if paginas_pendientes_reales == 0:
            print("[OK] No hay páginas en separado/revision_manual/revision_manual_qr.")
        else:
            for row in rows(cur, """
                SELECT id, asiento_contable, pagina, tipo_detectado, clave_documental, estado
                FROM documentos_paginas
                WHERE cliente_abreviatura=%s
                  AND anio=%s
                  AND mes=%s
                  AND estado IN ('separado', 'revision_manual', 'revision_manual_qr')
                ORDER BY asiento_contable, pagina
                LIMIT 50
            """, (cliente, year, month)):
                print(
                    f"[PENDIENTE] id={row['id']} "
                    f"{row['asiento_contable']} P{row['pagina']} "
                    f"{row['tipo_detectado']} "
                    f"{row['clave_documental']} "
                    f"estado={row['estado']}"
                )

        header("PÁGINAS LISTAS PARA AGRUPAR")
        if paginas_para_agrupar == 0:
            print("[OK] No hay páginas clasificadas pendientes de agrupar.")
        else:
            for row in rows(cur, """
                SELECT id, asiento_contable, pagina, tipo_detectado, clave_documental
                FROM documentos_paginas
                WHERE cliente_abreviatura=%s
                  AND anio=%s
                  AND mes=%s
                  AND estado='clasificado'
                ORDER BY asiento_contable, pagina
                LIMIT 50
            """, (cliente, year, month)):
                print(
                    f"[POR_AGRUPAR] id={row['id']} "
                    f"{row['asiento_contable']} P{row['pagina']} "
                    f"{row['tipo_detectado']} "
                    f"{row['clave_documental']}"
                )

        header("RESULTADO")
        bloqueantes = [
            "DB distribuido no coincide con filesystem final",
            "Hay documentos_extraidos en revisión",
            "Hay páginas en separado/revision_manual/revision_manual_qr",
            "Hay páginas clasificadas pendientes de agrupar",
            "Hay páginas agrupadas/clasificadas sin clave documental",
            "Hay QR pendientes",
            "Hay documentos agrupados no distribuidos",
            "Hay distribuidos sin ruta_final",
            "Hay archivos físicos en revision/revision_manual",
        ]

        errores_bloqueantes = [x for x in observaciones if x in bloqueantes]
        solo_observaciones = [x for x in observaciones if x not in bloqueantes]

        if not errores_bloqueantes and not solo_observaciones:
            print("[LOTE CERRADO OK]")
        elif not errores_bloqueantes:
            print("[LOTE CERRADO CON OBSERVACIONES]")
            for obs in solo_observaciones:
                print(f"- {obs}")
        else:
            print("[LOTE CON PENDIENTES]")
            for obs in errores_bloqueantes:
                print(f"- {obs}")
            for obs in solo_observaciones:
                print(f"- Observación: {obs}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)

    args = parser.parse_args()

    process(args.year, args.cliente, args.month)