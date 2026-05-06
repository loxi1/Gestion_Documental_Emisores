from __future__ import annotations

import argparse
import uuid
import re
from datetime import datetime
from pathlib import Path

from core.config import INPUT_DIR, OUTPUT_DIR, OCR_TMP_DIR
from core.db import get_cursor
from core.pdf_text import extract_text_from_pdf, count_pages
from core.ocr_service import run_ocr
from core.qr_reader import decode_qr_from_pdf
from core.qr_parser import parse_qr_payload
from core.classifier import extract_basic_fields, normalize_amount
from core.dates import parse_iso_date
from core.file_manager import sha256_file, copy_file, build_final_name
from core.pdf_pages import analizar_paginas_pdf
from core.repositories import (
    find_cliente_by_ruc,
    find_cliente_by_text,
    get_or_create_proveedor,
)


def should_use_qr(fields: dict) -> bool:
    return False
    tipo = fields.get("tipo_documental")

    if tipo not in ("factura", "guia_remision"):
        return False

    return (
        not fields.get("serie")
        or not fields.get("numero")
        or not fields.get("ruc")
        or not fields.get("fecha_emision")
        or (tipo == "factura" and not fields.get("importe"))
    )


def enrich_pdf(pdf_path: Path) -> dict:
    text = extract_text_from_pdf(pdf_path)
    fuente_datos = "pdf_text"

    ocr_output = None

    if not text.strip():
        ocr_output = OCR_TMP_DIR / f"ocr_{pdf_path.name}"
        if run_ocr(pdf_path, ocr_output):
            text = extract_text_from_pdf(ocr_output)
            fuente_datos = "ocr"

    fields = extract_basic_fields(text, pdf_path.name)

    if should_use_qr(fields):
        qr_candidates = decode_qr_from_pdf(pdf_path, max_pages=1, dpi=280)

        if not qr_candidates and ocr_output and ocr_output.exists():
            qr_candidates = decode_qr_from_pdf(ocr_output, max_pages=1, dpi=280)

        for candidate in qr_candidates:
            parsed = parse_qr_payload(candidate)

            if not parsed:
                continue

            if parsed.get("tipo_documental") != fields.get("tipo_documental"):
                continue

            fields["qr_data"] = parsed
            fields["serie"] = fields.get("serie") or parsed.get("serie")
            fields["numero"] = fields.get("numero") or parsed.get("numero")
            fields["ruc"] = fields.get("ruc") or parsed.get("ruc_emisor")
            fields["fecha_emision"] = fields.get("fecha_emision") or parsed.get("fecha_emision")
            fields["importe"] = fields.get("importe") or parsed.get("importe")
            fields["igv"] = fields.get("igv") or parsed.get("igv")
            fuente_datos = "qr"
            break

    cliente = None

    qr = fields.get("qr_data")
    if qr and qr.get("num_doc_adquirente"):
        cliente = find_cliente_by_ruc(qr.get("num_doc_adquirente"))

    if not cliente:
        cliente = find_cliente_by_text(text)

    fields["fuente_datos"] = fuente_datos

    return {
        "path": pdf_path,
        "text": text,
        "fields": fields,
        "cliente": cliente,
        "hash": sha256_file(pdf_path),
        "pages": count_pages(pdf_path),
    }


def is_valid_document(fields: dict) -> bool:
    tipo = fields.get("tipo_documental")

    if tipo == "factura":
        return bool(fields.get("serie") and fields.get("numero") and fields.get("ruc"))

    if tipo == "guia_remision":
        return bool(fields.get("serie") and fields.get("numero") and fields.get("ruc"))

    if tipo == "orden_compra":
        return bool(fields.get("numero") or fields.get("oc"))

    if tipo in ("nota_ingreso", "pago"):
        return bool(fields.get("numero"))

    return False


def build_group_key(cliente_abrev, tipo, fields):
    oc = fields.get("oc") or fields.get("orden_compra")

    if oc:
        return {
            "clave": f"{cliente_abrev} OC {oc}",
            "tipo": "CON_OC",
            "orden_compra": oc
        }

    if tipo == "factura" and fields.get("serie") and fields.get("numero") and fields.get("ruc"):
        return {
            "clave": f"{cliente_abrev} FACTURA {fields['serie']} {fields['numero']} {fields['ruc']}",
            "tipo": "SIN_OC",
            "orden_compra": None
        }

    return {
        "clave": f"{cliente_abrev} REVISION",
        "tipo": "REVISION",
        "orden_compra": None
    }


def create_lote(total: int, input_dir: Path) -> dict:
    codigo = "LOTE-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + str(uuid.uuid4())[:6]

    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            """
            INSERT INTO lotes_proceso (
                codigo_lote,
                carpeta_origen,
                total_archivos
            )
            VALUES (%s, %s, %s)
            RETURNING *
            """,
            (codigo, str(input_dir), total),
        )
        return cur.fetchone()


def create_or_get_grupo(conn_cur, lote_id: int, cliente_id, group_info: dict) -> dict:
    conn, cur = conn_cur

    cur.execute(
        """
        SELECT *
        FROM grupos_documentales
        WHERE lote_id = %s
          AND grupo_codigo = %s
        LIMIT 1
        """,
        (lote_id, group_info["clave_grupo"]),
    )

    row = cur.fetchone()
    if row:
        return row

    cur.execute(
        """
        INSERT INTO grupos_documentales (
            lote_id,
            grupo_codigo,
            cliente_destino_id,
            estado,
            observacion,
            clave_grupo,
            tipo_grupo,
            orden_compra
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            lote_id,
            group_info["clave_grupo"],
            cliente_id,
            "activo",
            "Grupo generado automáticamente por OC/factura",
            group_info["clave_grupo"],
            group_info["tipo_grupo"],
            group_info["orden_compra"],
        ),
    )

    return cur.fetchone()


def build_nombre_final(cliente_abrev: str, tipo: str, fields: dict, fallback_name: str) -> str:
    oc = normalizar_oc(
        fields.get("oc") or fields.get("orden_compra") or fields.get("oc_numero")
    )

    prefijo = f"{cliente_abrev} OC {oc} -" if oc else cliente_abrev

    return build_final_name(
        prefijo_nombre=prefijo,
        tipo_documental=tipo,
        serie=fields.get("serie"),
        numero=fields.get("numero"),
        ruc_emisor=fields.get("ruc"),
        razon_social_emisor=fields.get("razon_social") or fields.get("razon_social_emisor"),
        fallback_name=fallback_name,
    )


def get_bucket(estado):
    return {
        "clasificado_con_oc": "con_oc",
        "clasificado_sin_oc": "sin_oc",
        "revision_manual": "revision_manual",
        "no_identificado": "no_identificados"
    }.get(estado, "no_identificados")


def resolver_estado(tipo, valido, group_info):
    if tipo == "otro":
        return "no_identificado", True, "No se pudo identificar"

    if not valido:
        return "revision_manual", True, "Datos incompletos"

    if group_info["tipo"] == "CON_OC":
        return "clasificado_con_oc", False, None

    if group_info["tipo"] == "SIN_OC":
        return "clasificado_sin_oc", False, None

    return "revision_manual", True, "Sin OC"


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--year", required=False, type=int)
    parser.add_argument("--month", required=False, type=int)
    parser.add_argument("--cliente", required=False)

    return parser.parse_args()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--cliente", required=True)
    args = parser.parse_args()

    input_dir = INPUT_DIR / str(args.year) / args.cliente / f"{args.month:02d}"
    output_base = OUTPUT_DIR / str(args.year) / args.cliente / f"{args.month:02d}"

    print(f"Carpeta entrada: {input_dir}")

    pdfs = list(input_dir.glob("*.pdf"))
    print(f"PDF encontrados: {len(pdfs)}")

    if not pdfs:
        return

    grupo_cache = {}

    for i, pdf in enumerate(pdfs, start=1):
        print(f"[{i}/{len(pdfs)}] Procesando: {pdf.name}")

        text = extract_text_from_pdf(pdf)
        fields = extract_basic_fields(text, pdf.name)

        pages = count_pages(pdf)

        # -----------------------------
        # ANALISIS MULTIPAGINA
        # -----------------------------
        paginas_info = []

        if pages > 1:
            paginas_info = analizar_paginas_pdf(pdf)

            print(f"  PDF multipágina: {pages} páginas")
            for p in paginas_info:
                print(f"  Página {p['page']} -> tipo={p.get('tipo_documental')} oc={p.get('oc')} fuente={p.get('fuente')}")

            oc_global = next((p["oc"] for p in paginas_info if p.get("oc")), None)

            if oc_global:
                fields["oc"] = normalizar_oc(oc_global)
                fields["orden_compra"] = oc_global

                # 🔥 FORZAR ESTADO
                tipo = fields.get("tipo_documental")

                if tipo == "factura":
                    valido = True

        tipo = fields.get("tipo_documental")

        valido = bool(fields.get("serie") and fields.get("numero") and fields.get("ruc"))

        cliente_abrev = args.cliente

        group_info = build_group_key(cliente_abrev, tipo, fields)
        estado, requiere_revision, motivo = resolver_estado(tipo, valido, group_info)

        bucket = get_bucket(estado)

        proveedor = get_or_create_proveedor(
            fields.get("ruc"),
            fields.get("razon_social")
        )

        nombre_final = build_nombre_final(
            cliente_abrev=cliente_abrev,
            tipo=tipo,
            fields=fields,
            fallback_name=pdf.name,
        )

        destino = output_base / bucket / nombre_final
        copy_file(pdf, destino)

        # -----------------------------
        # DB
        # -----------------------------
        with get_cursor(commit=True) as (_, cur):

            # grupo
            clave = group_info["clave"]

            if clave in grupo_cache:
                grupo_id = grupo_cache[clave]
            else:
                cur.execute("""
                    INSERT INTO grupos_documentales (grupo_codigo)
                    VALUES (%s)
                    RETURNING id
                """, (clave,))
                grupo_id = cur.fetchone()["id"]
                grupo_cache[clave] = grupo_id

            # documento
            cur.execute("""
                INSERT INTO documentos (
                    grupo_id,
                    tipo_documental,
                    serie,
                    numero,
                    ruc_emisor,
                    razon_social_emisor,
                    oc_numero,
                    estado_documento,
                    nombre_original,
                    nombre_final,
                    ruta_destino,
                    hash_sha256,
                    paginas,
                    tiene_oc
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (hash_sha256) DO UPDATE
                SET actualizado_en = NOW()
                RETURNING id
            """, (
                grupo_id,
                tipo,
                fields.get("serie"),
                fields.get("numero"),
                fields.get("ruc"),
                fields.get("razon_social"),
                fields.get("oc"),
                estado,
                pdf.name,
                nombre_final,
                str(destino),
                sha256_file(pdf),
                pages,
                bool(fields.get("oc"))
            ))

            documento_id = cur.fetchone()["id"]

            # -----------------------------
            # PAGINAS
            # -----------------------------
            for page in paginas_info:
                cur.execute("""
                    INSERT INTO documento_paginas (
                        documento_id,
                        numero_pagina,
                        tipo_detectado,
                        orden_compra
                    )
                    VALUES (%s,%s,%s,%s)
                """, (
                    documento_id,
                    page["page"],
                    page.get("tipo_documental"),
                    page.get("oc")
                ))

                # -----------------------------
                # EXPORTAR INTERNOS → con_oc
                # -----------------------------
                tipo_page = page.get("tipo_documental")

                if tipo_page in ("orden_compra", "guia_remision", "nota_ingreso", "pago", "presupuesto"):
                    oc_page = normalizar_oc(page.get("oc") or fields.get("oc"))

                    fields_interno = {
                        **fields,
                        **page["fields"],
                        "oc": oc_page,
                    }

                    nombre_interno = build_nombre_final(
                        cliente_abrev=cliente_abrev,
                        tipo=tipo_page,
                        fields=fields_interno,
                        fallback_name=pdf.name,
                    )

                    bucket_interno = "con_oc" if oc_page else "sin_oc"
                    ruta_interna = output_base / bucket_interno / nombre_interno

                    copy_file(page["temp_pdf"], ruta_interna)

                    cur.execute("""
                        INSERT INTO documentos_internos (
                            documento_id,
                            grupo_id,
                            tipo_documental,
                            paginas,
                            orden_compra,
                            nombre_exportado,
                            ruta_exportada,
                            estado
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        documento_id,
                        grupo_id,
                        tipo_page,
                        str(page["page"]),
                        oc_page,
                        nombre_interno,
                        str(ruta_interna),
                        "exportado",
                    ))

        print(f"[{estado}] {pdf.name} -> {nombre_final}")

    print("Proceso finalizado.")

def normalizar_oc(oc):
    if not oc:
        return None

    oc = str(oc).strip()

    if oc.lower() in ("none", "null", "", "sin_oc"):
        return None

    if not oc.isdigit():
        return None

    # Evita falsos positivos como RUC, cuentas o 6301924
    if len(oc) > 6:
        return None

    return oc.zfill(6)

if __name__ == "__main__":
    main()