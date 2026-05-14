import argparse
from pathlib import Path

import fitz

from core.db import get_cursor

BASE_SALIDA = Path("data/salida")


def parse_clave(clave: str) -> dict:
    parts = (clave or "OTRO|SIN_ASIENTO|SIN_CODIGO").split("|")
    tipo = parts[0]

    if tipo == "FACTURA" and len(parts) >= 4:
        return {"tipo": "FACTURA", "ruc": parts[1], "serie": parts[2], "numero": parts[3], "banco": None, "codigo": None}

    if tipo == "GUIA" and len(parts) >= 4:
        return {"tipo": "GUIA_REMISION", "ruc": parts[1], "serie": parts[2], "numero": parts[3], "banco": None, "codigo": None}

    if tipo == "OC":
        return {"tipo": "OC", "ruc": None, "serie": None, "numero": parts[1] if len(parts) > 1 else "SIN_OC", "banco": None, "codigo": None}

    if tipo == "OS":
        return {"tipo": "OS", "ruc": None, "serie": None, "numero": parts[1] if len(parts) > 1 else "SIN_OS", "banco": None, "codigo": None}

    if tipo == "NI":
        return {"tipo": "NOTA_INGRESO", "ruc": None, "serie": None, "numero": parts[1] if len(parts) > 1 else "SIN_NI", "banco": None, "codigo": None}

    if tipo == "PAGO_TRANSFERENCIA":
        return {"tipo": "PAGO_TRANSFERENCIA", "ruc": None, "serie": None, "numero": None, "banco": parts[1] if len(parts) > 1 else "SIN_BANCO", "codigo": parts[2] if len(parts) > 2 else "SIN_CODIGO"}

    if tipo == "PAGO_DETRACCION":
        if len(parts) >= 4:
            return {"tipo": "PAGO_DETRACCION", "ruc": parts[1], "serie": parts[2], "numero": parts[3], "banco": "BN", "codigo": None}
        return {"tipo": "PAGO_DETRACCION", "ruc": None, "serie": None, "numero": None, "banco": parts[1] if len(parts) > 1 else "BN", "codigo": parts[2] if len(parts) > 2 else "SIN_CODIGO"}

    if tipo == "OTRO":
        return {"tipo": "OTRO", "ruc": None, "serie": None, "numero": parts[1] if len(parts) > 1 else "SIN_ASIENTO", "banco": None, "codigo": parts[2] if len(parts) > 2 else "SIN_CODIGO"}

    return {"tipo": "OTRO", "ruc": None, "serie": None, "numero": "SIN_ASIENTO", "banco": None, "codigo": "SIN_CODIGO"}


def build_filename(asiento: str, clave: str, paginas: list[int], bloque: int) -> str:
    data = parse_clave(clave)

    p_ini = min(paginas)
    p_fin = max(paginas)
    rango = f"P{p_ini:03d}-P{p_fin:03d}"
    sufijo_bloque = f" B{bloque:02d}" if bloque > 1 else ""

    tipo = data["tipo"]

    if tipo in ("FACTURA", "GUIA_REMISION"):
        return (
            f"{asiento} {tipo} {data['serie']} {data['numero']} "
            f"{data['ruc']} {rango}{sufijo_bloque}.pdf"
        )

    if tipo in ("OC", "OS", "NOTA_INGRESO"):
        return f"{asiento} {tipo} {data['numero']} {rango}{sufijo_bloque}.pdf"

    if tipo == "PAGO_TRANSFERENCIA":
        return (
            f"{asiento} PAGO_TRANSFERENCIA {data['banco']} "
            f"{data['codigo']} {rango}{sufijo_bloque}.pdf"
        )

    if tipo == "PAGO_DETRACCION":
        if data.get("serie") and data.get("numero") and data.get("ruc"):
            return (
                f"{asiento} PAGO_DETRACCION {data['serie']} "
                f"{data['numero']} {data['ruc']} {rango}{sufijo_bloque}.pdf"
            )

        return (
            f"{asiento} PAGO_DETRACCION {data['banco']} "
            f"{data['codigo']} {rango}{sufijo_bloque}.pdf"
        )

    return f"{asiento} OTRO {rango}{sufijo_bloque}.pdf"


def crear_pdf(paginas: list[dict], output_pdf: Path):
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    doc_out = fitz.open()

    for row in paginas:
        ruta = row.get("ruta_pagina_pdf")

        if not ruta:
            print(f"[SIN RUTA] ID {row['id']} {row['archivo_fuente']} P{row['pagina']}")
            continue

        page_pdf = Path(ruta)

        if not page_pdf.exists():
            print(f"[NO EXISTE] {page_pdf}")
            continue

        with fitz.open(page_pdf) as doc_in:
            doc_out.insert_pdf(doc_in)

    if doc_out.page_count > 0:
        doc_out.save(output_pdf)

    doc_out.close()


def construir_bloques(rows: list[dict]):
    grupos = {}

    for row in rows:
        key = (
            row["asiento_contable"],
            row["archivo_fuente"],
            row["clave_documental"],
        )

        grupos.setdefault(key, []).append(row)

    resultado = []

    for key, paginas in grupos.items():
        paginas_ordenadas = sorted(paginas, key=lambda x: x["pagina"])
        resultado.append((1, paginas_ordenadas))

    resultado.sort(
        key=lambda item: (
            item[1][0]["asiento_contable"],
            item[1][0]["archivo_fuente"],
            min(p["pagina"] for p in item[1]),
        )
    )

    return resultado


def procesar(year: int, cliente: str, month: int):
    cliente = cliente.upper()

    salida = BASE_SALIDA / str(year) / cliente / f"{month:02d}" / "provisional"
    salida.mkdir(parents=True, exist_ok=True)

    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT *
            FROM documentos_paginas
            WHERE estado = 'clasificado'
              AND clave_documental IS NOT NULL
              AND cliente_abreviatura = %s
              AND anio = %s
              AND mes = %s
            ORDER BY asiento_contable, archivo_fuente, pagina
        """, (cliente, year, month))

        rows = cur.fetchall()

    bloques = construir_bloques(rows)

    total = 0

    for bloque_num, paginas in bloques:
        paginas_ordenadas = sorted(paginas, key=lambda x: x["pagina"])

        asiento = paginas_ordenadas[0]["asiento_contable"]
        archivo_fuente = paginas_ordenadas[0]["archivo_fuente"]
        clave = paginas_ordenadas[0]["clave_documental"]

        nums_paginas = [p["pagina"] for p in paginas_ordenadas]
        filename = build_filename(asiento, clave, nums_paginas, bloque_num)
        output_pdf = salida / filename

        crear_pdf(paginas_ordenadas, output_pdf)

        if not output_pdf.exists():
            print(f"[NO AGRUPADO] {filename}")
            continue

        data = parse_clave(clave)

        orden_servicio = next(
            (p.get("orden_servicio") for p in paginas_ordenadas if p.get("orden_servicio")),
            None,
        )

        orden_compra = next(
            (p.get("orden_compra") for p in paginas_ordenadas if p.get("orden_compra")),
            None,
        )

        with get_cursor(commit=True) as (_, cur):
            cur.execute("""
                INSERT INTO documentos_agrupados (
                    asiento_contable,
                    archivo_fuente,
                    clave_documental,
                    tipo_documental,
                    serie,
                    numero,
                    orden_servicio,
                    orden_compra,
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
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, NULL, 'agrupado', %s, %s, %s, 'fragmentos'
                )
            """, (
                asiento,
                archivo_fuente,
                clave,
                data["tipo"],
                data.get("serie"),
                data.get("numero"),
                orden_servicio,
                orden_compra,
                min(nums_paginas),
                max(nums_paginas),
                ",".join(str(p) for p in nums_paginas),
                filename,
                str(output_pdf),
                cliente,
                year,
                month,
            ))

        total += 1
        print(f"[AGRUPADO] {filename}")

    print(f"Total agrupados: {total}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--month", type=int, required=True)

    args = parser.parse_args()

    procesar(args.year, args.cliente, args.month)