import argparse
import shutil
from pathlib import Path

from core.db import get_cursor

BASE_SALIDA = Path("data/salida")


def limpiar_destino(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def mover_seguro(origen: Path, destino: Path):
    destino.parent.mkdir(parents=True, exist_ok=True)

    if destino.exists():
        destino.unlink()

    shutil.move(str(origen), str(destino))


def obtener_asientos_con_oc_os():
    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT DISTINCT asiento_contable
            FROM documentos_paginas
            WHERE estado = 'clasificado'
              AND clave_documental IS NOT NULL
              AND tipo_detectado IN ('orden_compra', 'orden_servicio')
            ORDER BY asiento_contable
        """)
        return {row["asiento_contable"] for row in cur.fetchall()}


def obtener_archivos_provisionales(year: int, cliente: str, month: int):
    base = BASE_SALIDA / str(year) / cliente / f"{month:02d}" / "provisional"
    return base, sorted(base.glob("*.pdf"))


def extraer_asiento_desde_nombre(nombre: str) -> str | None:
    partes = nombre.split(" ", 1)
    if not partes:
        return None

    asiento = partes[0].strip()

    if asiento.startswith("04-"):
        return asiento

    return None


def procesar(year: int, cliente: str, month: int):
    base_mes = BASE_SALIDA / str(year) / cliente / f"{month:02d}"

    dir_con_oc = base_mes / "con_oc"
    dir_sin_oc = base_mes / "sin_oc"
    dir_revision = base_mes / "revision"

    limpiar_destino(dir_con_oc)
    limpiar_destino(dir_sin_oc)
    limpiar_destino(dir_revision)

    asientos_con_oc_os = obtener_asientos_con_oc_os()

    provisional, archivos = obtener_archivos_provisionales(year, cliente, month)

    print(f"Provisional: {provisional}")
    print(f"Archivos encontrados: {len(archivos)}")
    print(f"Asientos con OC/OS: {len(asientos_con_oc_os)}")

    movidos_con_oc = 0
    movidos_sin_oc = 0
    movidos_revision = 0

    for archivo in archivos:
        asiento = extraer_asiento_desde_nombre(archivo.name)

        if not asiento:
            destino = dir_revision / archivo.name
            mover_seguro(archivo, destino)
            movidos_revision += 1
            print(f"[REVISION] {archivo.name}")
            continue

        if asiento in asientos_con_oc_os:
            destino = dir_con_oc / archivo.name
            mover_seguro(archivo, destino)
            movidos_con_oc += 1
            print(f"[CON_OC] {archivo.name}")
        else:
            destino = dir_sin_oc / archivo.name
            mover_seguro(archivo, destino)
            movidos_sin_oc += 1
            print(f"[SIN_OC] {archivo.name}")

    print("\nDistribución finalizada.")
    print(f"Con OC/OS: {movidos_con_oc}")
    print(f"Sin OC/OS: {movidos_sin_oc}")
    print(f"Revisión: {movidos_revision}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)

    args = parser.parse_args()

    procesar(args.year, args.cliente, args.month)