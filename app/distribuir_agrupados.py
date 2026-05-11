import argparse
import re
import shutil
import unicodedata
from pathlib import Path

from core.db import get_cursor

BASE_SALIDA = Path("data/salida")


def safe_text(value: str | None) -> str:
    value = value or ""
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    return value.strip("_").upper() or "SIN_RAZON_SOCIAL"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    base = path.with_suffix("")
    ext = path.suffix
    i = 2

    while True:
        nuevo = Path(f"{base}_{i}{ext}")
        if not nuevo.exists():
            return nuevo
        i += 1


def mover(origen: Path, destino: Path):
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino = unique_path(destino)
    shutil.move(str(origen), str(destino))
    return destino


def parse_clave(clave: str) -> dict:
    p = clave.split("|")

    if p[0] == "FACTURA":
        return {"tipo": "FACTURA", "ruc": p[1], "serie": p[2], "numero": p[3]}

    if p[0] == "GUIA":
        return {"tipo": "GUIA_REMISION", "ruc": p[1], "serie": p[2], "numero": p[3]}

    if p[0] == "OC":
        return {"tipo": "ORDEN_COMPRA", "numero": p[1]}

    if p[0] == "OS":
        return {"tipo": "ORDEN_SERVICIO", "numero": p[1]}

    if p[0] == "NI":
        return {"tipo": "NOTA_INGRESO", "numero": p[1]}

    if p[0] == "PAGO_TRANSFERENCIA":
        return {
            "tipo": "PAGO_TRANSFERENCIA",
            "banco": p[1] if len(p) > 1 else "SIN_BANCO",
            "codigo": p[2] if len(p) > 2 else "SIN_CODIGO",
        }

    if p[0] == "PAGO_DETRACCION":
        if len(p) >= 4:
            return {"tipo": "PAGO_DETRACCION", "ruc": p[1], "serie": p[2], "numero": p[3]}

        return {
            "tipo": "PAGO_DETRACCION",
            "banco": p[1] if len(p) > 1 else "BN",
            "codigo": p[2] if len(p) > 2 else "SIN_CODIGO",
        }

    return {"tipo": "OTRO"}


def obtener_razones(cliente: str, year: int, month: int):
    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT DISTINCT ruc_emisor, razon_social_emisor
            FROM documentos_paginas
            WHERE ruc_emisor IS NOT NULL
              AND razon_social_emisor IS NOT NULL
              AND razon_social_emisor <> ''
              AND cliente_abreviatura = %s
              AND anio = %s
              AND mes = %s
        """, (cliente, year, month))
        return {row["ruc_emisor"]: row["razon_social_emisor"] for row in cur.fetchall()}


def obtener_control_por_asiento(cliente: str, year: int, month: int):
    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT asiento_contable, orden_compra, orden_servicio, pagina
            FROM documentos_paginas
            WHERE estado = 'clasificado'
              AND cliente_abreviatura = %s
              AND anio = %s
              AND mes = %s
              AND (
                    orden_compra IS NOT NULL
                    OR orden_servicio IS NOT NULL
                  )
            ORDER BY asiento_contable, pagina
        """, (cliente, year, month))

        controles = {}

        for row in cur.fetchall():
            asiento = row["asiento_contable"]

            if asiento in controles:
                continue

            if row["orden_compra"]:
                controles[asiento] = ("OC", str(row["orden_compra"]).zfill(6))

            elif row["orden_servicio"]:
                controles[asiento] = ("OS", str(row["orden_servicio"]).zfill(6))

        return controles


def nombre_con_oc(cliente: str, control_tipo: str, control_num: str, clave: str, razones: dict) -> str:
    data = parse_clave(clave)
    prefix = f"{cliente} {control_tipo} {control_num} -"

    if data["tipo"] == "FACTURA":
        razon = safe_text(razones.get(data["ruc"]))
        return f"{prefix} FACTURA {data['serie']} {data['numero']} {data['ruc']} {razon}.pdf"

    if data["tipo"] == "GUIA_REMISION":
        razon = safe_text(razones.get(data["ruc"]))
        return f"{prefix} GUIA_REMISION {data['serie']} {data['numero']} {data['ruc']} {razon}.pdf"

    if data["tipo"] == "ORDEN_COMPRA":
        return f"{prefix} ORDEN_COMPRA {data['numero']}.pdf"

    if data["tipo"] == "ORDEN_SERVICIO":
        return f"{prefix} ORDEN_SERVICIO {data['numero']}.pdf"

    if data["tipo"] == "NOTA_INGRESO":
        return f"{prefix} NOTA_INGRESO {data['numero']}.pdf"

    if data["tipo"] == "PAGO_TRANSFERENCIA":
        return f"{prefix} PAGO_TRANSFERENCIA {data['banco']} {data['codigo']}.pdf"

    if data["tipo"] == "PAGO_DETRACCION":
        if "serie" in data:
            return f"{prefix} PAGO_DETRACCION {data['serie']} {data['numero']} {data['ruc']}.pdf"
        return f"{prefix} PAGO_DETRACCION {data['banco']} {data['codigo']}.pdf"

    return f"{prefix} SOPORTE.pdf"


def nombre_sin_oc(cliente: str, asiento: str, clave: str, razones: dict) -> str:
    data = parse_clave(clave)

    if data["tipo"] == "FACTURA":
        razon = safe_text(razones.get(data["ruc"]))
        return f"{asiento} {cliente} FACTURA {data['serie']} {data['numero']} {data['ruc']} {razon}.pdf"

    if data["tipo"] == "GUIA_REMISION":
        razon = safe_text(razones.get(data["ruc"]))
        return f"{asiento} {cliente} GUIA_REMISION {data['serie']} {data['numero']} {data['ruc']} {razon}.pdf"

    if data["tipo"] == "NOTA_INGRESO":
        return f"{asiento} {cliente} NOTA_INGRESO {data['numero']}.pdf"

    if data["tipo"] == "PAGO_TRANSFERENCIA":
        return f"{asiento} {cliente} PAGO_TRANSFERENCIA {data['banco']} {data['codigo']}.pdf"

    if data["tipo"] == "PAGO_DETRACCION":
        if "serie" in data:
            return f"{asiento} {cliente} PAGO_DETRACCION {data['serie']} {data['numero']} {data['ruc']}.pdf"
        return f"{asiento} {cliente} PAGO_DETRACCION {data['banco']} {data['codigo']}.pdf"

    return f"{asiento} {cliente} SOPORTE.pdf"


def procesar(year: int, cliente: str, month: int):
    cliente = cliente.upper()
    base_mes = BASE_SALIDA / str(year) / cliente / f"{month:02d}"
    dir_con_oc = base_mes / "con_oc"
    dir_sin_oc = base_mes / "sin_oc"
    dir_revision = base_mes / "revision"

    dir_con_oc.mkdir(parents=True, exist_ok=True)
    dir_sin_oc.mkdir(parents=True, exist_ok=True)
    dir_revision.mkdir(parents=True, exist_ok=True)

    controles = obtener_control_por_asiento(cliente, year, month)
    razones = obtener_razones(cliente, year, month)

    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT *
            FROM documentos_agrupados
            WHERE estado = 'agrupado'
              AND cliente_abreviatura = %s
              AND anio = %s
              AND mes = %s
            ORDER BY asiento_contable, nombre_archivo
        """, (cliente, year, month))
        rows = cur.fetchall()

    con_oc = sin_oc = revision = 0

    for row in rows:
        origen = Path(row["ruta_archivo"])

        if not origen.exists():
            print(f"[NO EXISTE] {origen}")
            revision += 1
            continue

        asiento = row["asiento_contable"]
        clave = row["clave_documental"]

        if asiento in controles:
            control_tipo, control_num = controles[asiento]
            nuevo_nombre = nombre_con_oc(cliente, control_tipo, control_num, clave, razones)
            destino = mover(origen, dir_con_oc / nuevo_nombre)
            estado = "distribuido_con_oc"
            con_oc += 1
            print(f"[CON_OC] {destino.name}")
        else:
            nuevo_nombre = nombre_sin_oc(cliente, asiento, clave, razones)
            destino = mover(origen, dir_sin_oc / nuevo_nombre)
            estado = "distribuido_sin_oc"
            sin_oc += 1
            print(f"[SIN_OC] {destino.name}")

        with get_cursor(commit=True) as (_, cur):
            cur.execute("""
                UPDATE documentos_agrupados
                SET nombre_archivo = %s,
                    ruta_final = %s,
                    estado = %s
                WHERE id = %s
            """, (
                destino.name,
                str(destino),
                estado,
                row["id"],
            ))

    print("\nDistribución finalizada.")
    print(f"Con OC/OS: {con_oc}")
    print(f"Sin OC/OS: {sin_oc}")
    print(f"Revisión: {revision}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)

    args = parser.parse_args()
    procesar(args.year, args.cliente, args.month)