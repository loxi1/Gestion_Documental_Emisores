import argparse
import shutil
from pathlib import Path

from slugify import slugify

from core.db import get_cursor
from core.proveedor_service import get_or_fetch_proveedor

BASE_SALIDA = Path("data/salida")


def clean(value: str | None) -> str:
    return slugify(value or "SIN_RAZON_SOCIAL", separator="_").upper()


def input_default(label: str, default=None):
    value = input(f"{label} [{default or ''}]: ").strip()
    return value if value else default


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


def nombre_factura(cliente, asiento, serie, numero, ruc, razon):
    return f"{asiento} {cliente} FACTURA {serie} {numero} {ruc} {clean(razon)}.pdf"


def editar(extraido_id: int):
    row = leer_extraido(extraido_id)

    if not row:
        print(f"[NO ENCONTRADO] ID {extraido_id}")
        return

    cliente = row["cliente_abreviatura"]
    year = row["anio"]
    month = row["mes"]

    print("=" * 100)
    print(f"ID        : {row['id']}")
    print(f"Asiento   : {row['asiento_contable']}")
    print(f"Archivo   : {row['nombre_provisional']}")
    print(f"Ruta      : {row['ruta_provisional']}")
    print(f"Tipo      : {row['tipo_documental']}")
    print(f"Motivo    : {row['motivo_revision']}")
    print("=" * 100)

    tipo = input_default("Tipo", row["tipo_documental"] or "factura").lower()

    if tipo != "factura":
        print("[INFO] Para marcar como otro usa marcar_extraido_otro.py")
        return

    asiento = input_default("Asiento", row["asiento_contable"])
    serie = input_default("Serie", row["serie"])
    numero = input_default("Número", row["numero"])
    ruc = input_default("RUC emisor", row["ruc_emisor"])

    proveedor = get_or_fetch_proveedor(ruc) if ruc else None

    razon_api = None

    if proveedor:
        razon_api = (
            proveedor.get("razon_social")
            or proveedor.get("nombre")
            or proveedor.get("nombre_o_razon_social")
        )

    razon_default = (
        row["razon_social_emisor"]
        if row["razon_social_emisor"]
        and row["razon_social_emisor"] != "SIN_RAZON_SOCIAL"
        else razon_api
    )
    
    razon = input_default("Razón social", razon_default)

    origen = Path(row["ruta_provisional"])

    if not origen.exists():
        print(f"[ERROR] No existe archivo origen: {origen}")
        return

    destino_dir = BASE_SALIDA / str(year) / cliente / f"{month:02d}" / "sin_oc"
    destino_dir.mkdir(parents=True, exist_ok=True)

    final_name = nombre_factura(cliente, asiento, serie, numero, ruc, razon)
    destino = unique_path(destino_dir / final_name)

    print("\nResumen:")
    print(f"Origen : {origen}")
    print(f"Destino: {destino}")

    confirmar = input("\n¿Guardar y mover? s/n [s]: ").strip().lower() or "s"

    if confirmar != "s":
        print("[CANCELADO]")
        return

    shutil.move(str(origen), str(destino))

    clave = f"FACTURA|{ruc}|{serie}|{numero}"

    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            UPDATE documentos_extraidos
            SET asiento_contable = %s,
                tipo_documental = 'factura',
                serie = %s,
                numero = %s,
                ruc_emisor = %s,
                razon_social_emisor = %s,
                nombre_final = %s,
                ruta_final = %s,
                estado = 'procesado_sin_oc',
                requiere_revision = FALSE,
                motivo_revision = NULL,
                actualizado_en = NOW()
            WHERE id = %s
        """, (
            asiento,
            serie,
            numero,
            ruc,
            razon,
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
                serie,
                numero,
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
                %s, %s, %s, 'FACTURA', %s, %s, 1, 1, '1',
                %s, %s, %s, 'distribuido_sin_oc',
                %s, %s, %s, 'factura_1_pagina_manual'
            )
            ON CONFLICT DO NOTHING
        """, (
            asiento,
            row["nombre_provisional"],
            clave,
            serie,
            numero,
            destino.name,
            str(destino),
            str(destino),
            cliente,
            year,
            month,
        ))

    print(f"[OK] Extraído actualizado como factura: {destino.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    args = parser.parse_args()

    editar(args.id)