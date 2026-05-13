import argparse
from pathlib import Path
import fitz

from core.db import get_cursor

BASE_SALIDA = Path("data/salida")


def parse_clave(clave: str) -> dict:
    parts = clave.split("|")

    if parts[0] == "FACTURA":
        return {"tipo": "FACTURA", "ruc": parts[1], "serie": parts[2], "numero": parts[3]}

    if parts[0] == "GUIA":
        return {"tipo": "GUIA_REMISION", "ruc": parts[1], "serie": parts[2], "numero": parts[3]}

    if parts[0] == "OC":
        return {"tipo": "OC", "numero": parts[1]}

    if parts[0] == "OS":
        return {"tipo": "OS", "numero": parts[1]}

    if parts[0] == "NI":
        return {"tipo": "NOTA_INGRESO", "numero": parts[1]}

    if parts[0] == "PAGO_TRANSFERENCIA":
        return {
            "tipo": "PAGO_TRANSFERENCIA",
            "banco": parts[1] if len(parts) > 1 else "SIN_BANCO",
            "codigo": parts[2] if len(parts) > 2 else "SIN_CODIGO",
        }

    if parts[0] == "PAGO_DETRACCION":
        if len(parts) >= 4:
            return {
                "tipo": "PAGO_DETRACCION",
                "ruc": parts[1],
                "serie": parts[2],
                "numero": parts[3],
            }

        return {
            "tipo": "PAGO_DETRACCION",
            "banco": parts[1] if len(parts) > 1 else "BN",
            "codigo": parts[2] if len(parts) > 2 else "SIN_CODIGO",
        }

    return {"tipo": "OTRO"}


def build_filename(asiento: str, clave: str, paginas: list[int], bloque: int) -> str:
    data = parse_clave(clave)
    p_ini = min(paginas)
    p_fin = max(paginas)
    rango = f"P{p_ini:03d}-P{p_fin:03d}"
    sufijo_bloque = f" B{bloque:02d}" if bloque > 1 else ""
    tipo = data["tipo"]

    if tipo in ("FACTURA", "GUIA_REMISION"):
        return f"{asiento} {tipo} {data['serie']} {data['numero']} {data['ruc']} {rango}{sufijo_bloque}.pdf"

    if tipo in ("OC", "OS", "NOTA_INGRESO"):
        return f"{asiento} {tipo} {data['numero']} {rango}{sufijo_bloque}.pdf"

    if tipo == "PAGO_TRANSFERENCIA":
        return f"{asiento} PAGO_TRANSFERENCIA {data['banco']} {data['codigo']} {rango}{sufijo_bloque}.pdf"

    if tipo == "PAGO_DETRACCION":
        if "serie" in data:
            return f"{asiento} PAGO_DETRACCION {data['serie']} {data['numero']} {data['ruc']} {rango}{sufijo_bloque}.pdf"
        return f"{asiento} PAGO_DETRACCION {data['banco']} {data['codigo']} {rango}{sufijo_bloque}.pdf"

    return f"{asiento} OTRO {rango}{sufijo_bloque}.pdf"


def crear_pdf(paginas: list[dict], output_pdf: Path):
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc_out = fitz.open()

    for row in paginas:
        ruta = row["ruta_pagina_pdf"]
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
    bloques = []
    bloque_actual = []
    clave_actual = None
    asiento_actual = None
    contador_bloques = {}

    for row in rows:
        asiento = row["asiento_contable"]
        clave = row["clave_documental"]

        cambio = asiento != asiento_actual or clave != clave_actual

        if cambio and bloque_actual:
            bloques.append(bloque_actual)
            bloque_actual = []

        bloque_actual.append(row)
        asiento_actual = asiento
        clave_actual = clave

    if bloque_actual:
        bloques.append(bloque_actual)

    resultado = []

    for bloque in bloques:
        asiento = bloque[0]["asiento_contable"]
        clave = bloque[0]["clave_documental"]
        k = (asiento, clave)
        contador_bloques[k] = contador_bloques.get(k, 0) + 1
        resultado.append((contador_bloques[k], bloque))

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
            ORDER BY asiento_contable, pagina
        """, (cliente, year, month))
        rows = cur.fetchall()

    bloques = construir_bloques(rows)
    total = 0

    for bloque_num, paginas in bloques:
        paginas_ordenadas = sorted(paginas, key=lambda x: x["pagina"])
        asiento = paginas_ordenadas[0]["asiento_contable"]
        clave = paginas_ordenadas[0]["clave_documental"]
        nums_paginas = [p["pagina"] for p in paginas_ordenadas]

        filename = build_filename(asiento, clave, nums_paginas, bloque_num)
        output_pdf = salida / filename

        crear_pdf(paginas_ordenadas, output_pdf)

        if output_pdf.exists():
            data = parse_clave(clave)

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
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,
                        'agrupado',%s,%s,%s,'fragmentos'
                    )
                """, (
                    asiento,
                    paginas_ordenadas[0]["archivo_fuente"],
                    clave,
                    data["tipo"],
                    data.get("serie"),
                    data.get("numero"),
                    paginas_ordenadas[0].get("orden_servicio"),
                    paginas_ordenadas[0].get("orden_compra"),
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