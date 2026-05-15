import argparse
import re
import shutil
from pathlib import Path

from core.db import get_cursor


print("USANDO ARCHIVO CORRECTO")

def clean(value: str | None) -> str:
    return slugify(value or "SIN_DATO", separator="_").upper()


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    base = path.with_suffix("")
    ext = path.suffix
    i = 2

    while True:
        new_path = Path(f"{base}_{i}{ext}")
        if not new_path.exists():
            return new_path
        i += 1


def leer_extraido(extraido_id: int):
    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT
                de.*,
                lp.cliente_abreviatura,
                lp.anio,
                lp.mes
            FROM documentos_extraidos de
            INNER JOIN lotes_procesamiento lp ON lp.id = de.lote_id
            WHERE de.id = %s
        """, (extraido_id,))
        return cur.fetchone()


def marcar(extraido_id: int):
    row = leer_extraido(extraido_id)

    if not row:
        print(f"[NO ENCONTRADO] ID {extraido_id}")
        return

    cliente = row["cliente_abreviatura"]
    year = row["anio"]
    month = row["mes"]

    origen = Path(row["ruta_provisional"])

    if row["ruta_final"]:
        origen = Path(row["ruta_final"])

    if not origen.exists():
        print(f"[ERROR] No existe archivo: {origen}")
        return

    asiento = row["asiento_contable"] or extraer_asiento(row["nombre_provisional"])
    ref = clean(Path(row["nombre_provisional"] or origen.name).stem)

    destino_dir = BASE_SALIDA / str(year) / cliente / f"{month:02d}" / "sin_oc"
    destino_dir.mkdir(parents=True, exist_ok=True)

    destino = unique_path(destino_dir / f"{asiento} {cliente} OTRO {ref}.pdf")

    confirmar = input(f"¿Mover como OTRO?\n{origen}\n-> {destino}\ns/n [s]: ").strip().lower() or "s"

    if confirmar != "s":
        print("[CANCELADO]")
        return

    if origen.resolve() != destino.resolve():
        shutil.move(str(origen), str(destino))

    revision_copy = (
        BASE_SALIDA
        / str(year)
        / cliente
        / f"{month:02d}"
        / "revision"
        / Path(row["nombre_provisional"]).name
    )

    if revision_copy.exists():
        revision_copy.unlink()
        print(f"[REVISION LIMPIADA] {revision_copy}")

    clave = f"OTRO|{asiento}|{row['id']}"

    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            UPDATE documentos_extraidos
            SET tipo_documental = 'otro',
                nombre_final = %s,
                ruta_final = %s,
                estado = 'procesado_sin_oc',
                requiere_revision = FALSE,
                motivo_revision = NULL,
                actualizado_en = NOW()
            WHERE id = %s
        """, (
            destino.name,
            str(destino),
            extraido_id,
        ))

        cur.execute("""
            INSERT INTO documentos_agrupados (
                asiento_contable,
                archivo_fuente,
                clave_documental,
                tipo_documental,
                pagina_inicio,
                pagina_fin,
                paginas,
                nombre_archivo,
                ruta_archivo,
                ruta_final,
                estado,
                cliente_abreviatura,
                anio,
                mes,
                origen
            )
            VALUES (
                %s, %s, %s, 'OTRO', 1, 1, '1',
                %s, %s, %s, 'distribuido_sin_oc',
                %s, %s, %s, 'extraido_1_pagina_manual'
            )
            ON CONFLICT DO NOTHING
        """, (
            asiento,
            row["nombre_provisional"],
            clave,
            destino.name,
            str(destino),
            str(destino),
            cliente,
            year,
            month,
        ))

    print(f"[OK] Extraído marcado como OTRO: {destino.name}")


def extraer_asiento(nombre: str) -> str:
    m = re.search(r"\b(04-\d{4})\b", nombre or "")

    if m:
        return m.group(1)

    return "SIN_ASIENTO"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    args = parser.parse_args()

    marcar(args.id)