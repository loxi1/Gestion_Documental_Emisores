from __future__ import annotations

import argparse
import uuid
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
from core.repositories import (
    find_cliente_by_ruc,
    find_cliente_by_text,
    get_or_create_proveedor,
)


def should_use_qr(fields: dict) -> bool:
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


def build_group_key(cliente_abrev: str, tipo: str, fields: dict) -> dict:
    oc = fields.get("oc") or fields.get("orden_compra") or fields.get("oc_numero")

    if oc:
        return {
            "clave_grupo": f"{cliente_abrev} OC {oc}",
            "tipo_grupo": "CON_OC",
            "orden_compra": oc,
        }

    if tipo == "factura" and fields.get("serie") and fields.get("numero") and fields.get("ruc"):
        return {
            "clave_grupo": f"{cliente_abrev} FACTURA {fields['serie']} {fields['numero']} {fields['ruc']}",
            "tipo_grupo": "SIN_OC",
            "orden_compra": None,
        }

    return {
        "clave_grupo": f"{cliente_abrev} REVISION",
        "tipo_grupo": "REVISION",
        "orden_compra": None,
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
    oc = fields.get("oc") or fields.get("orden_compra") or fields.get("oc_numero")

    if oc:
        prefijo = f"{cliente_abrev} OC {oc} -"
    else:
        prefijo = cliente_abrev

    nombre = build_final_name(
        prefijo_nombre=prefijo,
        tipo_documental=tipo,
        serie=fields.get("serie"),
        numero=fields.get("numero"),
        ruc_emisor=fields.get("ruc"),
        razon_social_emisor=fields.get("razon_social") or fields.get("razon_social_emisor"),
        fallback_name=fallback_name,
    )

    return nombre


def get_bucket(estado: str) -> str:
    if estado == "clasificado_con_oc":
        return "con_oc"

    if estado == "clasificado_sin_oc":
        return "sin_oc"

    if estado == "revision_manual":
        return "revision_manual"

    return "no_identificados"


def resolver_estado(tipo: str, valido: bool, group_info: dict) -> tuple[str, bool, str | None]:
    if tipo == "otro":
        return "no_identificado", True, "No se pudo identificar el tipo documental"

    if not valido:
        return "revision_manual", True, "Faltan datos mínimos del documento"

    if group_info["tipo_grupo"] == "CON_OC":
        return "clasificado_con_oc", False, None

    if group_info["tipo_grupo"] == "SIN_OC":
        return "clasificado_sin_oc", False, None

    return "revision_manual", True, "No tiene OC ni datos suficientes para agrupar"


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--year", required=False, type=int)
    parser.add_argument("--month", required=False, type=int)
    parser.add_argument("--cliente", required=False)

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.year and args.month and args.cliente:
        input_dir = INPUT_DIR / str(args.year) / args.cliente / f"{args.month:02d}"
        output_base = OUTPUT_DIR / str(args.year) / args.cliente / f"{args.month:02d}"
    else:
        input_dir = INPUT_DIR
        output_base = OUTPUT_DIR

    pdfs = sorted(input_dir.glob("*.pdf"))

    print(f"Carpeta entrada: {input_dir}")
    print(f"PDF encontrados: {len(pdfs)}")

    if not pdfs:
        print("No hay PDFs para procesar.")
        return

    lote = create_lote(len(pdfs), input_dir)

    docs = [enrich_pdf(pdf) for pdf in pdfs]

    factura_principal = next(
        (d for d in docs if d["fields"].get("tipo_documental") == "factura"),
        None,
    )

    cliente_global = factura_principal["cliente"] if factura_principal else None

    if not cliente_global:
        cliente_global = next((d["cliente"] for d in docs if d.get("cliente")), None)

    if not cliente_global and args.cliente:
        cliente_global = {
            "id": None,
            "abreviatura": args.cliente,
        }

    cliente_abrev = cliente_global["abreviatura"] if cliente_global else "SIN_CLIENTE"
    cliente_id = cliente_global["id"] if cliente_global else None

    fecha_base = None

    if factura_principal:
        fecha_base = parse_iso_date(factura_principal["fields"].get("fecha_emision"))

    fecha_base = fecha_base or datetime.now().date()

    total_con_oc = 0
    total_sin_oc = 0
    total_revision = 0
    total_no_id = 0

    grupo_cache = {}

    for doc in docs:
        fields = doc["fields"]
        tipo = fields.get("tipo_documental")
        valido = is_valid_document(fields)

        group_info = build_group_key(cliente_abrev, tipo, fields)
        grupo_cache_key = group_info["clave_grupo"]

        estado, requiere_revision, motivo_revision = resolver_estado(tipo, valido, group_info)

        if estado == "clasificado_con_oc":
            total_con_oc += 1
        elif estado == "clasificado_sin_oc":
            total_sin_oc += 1
        elif estado == "revision_manual":
            total_revision += 1
        else:
            total_no_id += 1

        bucket = get_bucket(estado)

        proveedor = get_or_create_proveedor(
            fields.get("ruc"),
            fields.get("razon_social") or fields.get("razon_social_emisor"),
        )

        nombre_final = build_nombre_final(
            cliente_abrev=cliente_abrev,
            tipo=tipo,
            fields=fields,
            fallback_name=doc["path"].name,
        )

        destino = output_base / bucket / nombre_final
        copy_file(doc["path"], destino)

        with get_cursor(commit=True) as conn_cur:
            if grupo_cache_key in grupo_cache:
                grupo = grupo_cache[grupo_cache_key]
            else:
                grupo = create_or_get_grupo(
                    conn_cur=conn_cur,
                    lote_id=lote["id"],
                    cliente_id=cliente_id,
                    group_info=group_info,
                )
                grupo_cache[grupo_cache_key] = grupo

            _, cur = conn_cur

            cur.execute(
                """
                INSERT INTO documentos (
                    lote_id,
                    grupo_id,
                    cliente_destino_id,
                    proveedor_id,
                    tipo_documental,
                    serie,
                    numero,
                    ruc_emisor,
                    razon_social_emisor,
                    fecha_emision,
                    importe,
                    igv,
                    oc_numero,
                    estado_documento,
                    observacion,
                    nombre_original,
                    nombre_final,
                    ruta_origen,
                    ruta_destino,
                    hash_sha256,
                    paginas,
                    es_principal,
                    qr_raw,
                    tiene_oc,
                    fuente_datos,
                    requiere_revision,
                    motivo_revision
                )
                VALUES (
                    %(lote_id)s,
                    %(grupo_id)s,
                    %(cliente_destino_id)s,
                    %(proveedor_id)s,
                    %(tipo_documental)s,
                    %(serie)s,
                    %(numero)s,
                    %(ruc_emisor)s,
                    %(razon_social_emisor)s,
                    %(fecha_emision)s,
                    %(importe)s,
                    %(igv)s,
                    %(oc_numero)s,
                    %(estado_documento)s,
                    %(observacion)s,
                    %(nombre_original)s,
                    %(nombre_final)s,
                    %(ruta_origen)s,
                    %(ruta_destino)s,
                    %(hash_sha256)s,
                    %(paginas)s,
                    %(es_principal)s,
                    %(qr_raw)s,
                    %(tiene_oc)s,
                    %(fuente_datos)s,
                    %(requiere_revision)s,
                    %(motivo_revision)s
                )
                ON CONFLICT (hash_sha256) DO NOTHING
                """,
                {
                    "lote_id": lote["id"],
                    "grupo_id": grupo["id"],
                    "cliente_destino_id": cliente_id,
                    "proveedor_id": proveedor["id"] if proveedor else None,
                    "tipo_documental": tipo,
                    "serie": fields.get("serie"),
                    "numero": fields.get("numero"),
                    "ruc_emisor": fields.get("ruc"),
                    "razon_social_emisor": fields.get("razon_social") or fields.get("razon_social_emisor"),
                    "fecha_emision": fields.get("fecha_emision"),
                    "importe": normalize_amount(fields.get("importe")),
                    "igv": normalize_amount(fields.get("igv")),
                    "oc_numero": group_info["orden_compra"],
                    "estado_documento": estado,
                    "observacion": "MVP local con agrupación automática",
                    "nombre_original": doc["path"].name,
                    "nombre_final": nombre_final,
                    "ruta_origen": str(doc["path"]),
                    "ruta_destino": str(destino),
                    "hash_sha256": doc["hash"],
                    "paginas": doc["pages"],
                    "es_principal": doc is factura_principal,
                    "qr_raw": fields.get("qr_data", {}).get("qr_raw") if fields.get("qr_data") else None,
                    "tiene_oc": bool(group_info["orden_compra"]),
                    "fuente_datos": fields.get("fuente_datos"),
                    "requiere_revision": requiere_revision,
                    "motivo_revision": motivo_revision,
                },
            )

        print(f"[{estado}] {doc['path'].name} -> {nombre_final}")

    total_clasificados = total_con_oc + total_sin_oc

    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            """
            UPDATE lotes_proceso
            SET estado=%s,
                total_clasificados=%s,
                total_revision=%s,
                total_no_identificados=%s,
                actualizado_en=NOW()
            WHERE id=%s
            """,
            (
                "procesado",
                total_clasificados,
                total_revision,
                total_no_id,
                lote["id"],
            ),
        )

    print("Proceso finalizado.")
    print(f"Clasificados con OC: {total_con_oc}")
    print(f"Clasificados sin OC: {total_sin_oc}")
    print(f"Revisión manual: {total_revision}")
    print(f"No identificados: {total_no_id}")


if __name__ == "__main__":
    main()