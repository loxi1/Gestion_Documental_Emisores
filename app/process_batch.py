from __future__ import annotations

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
from core.file_manager import sha256_file, build_final_name, copy_file
from core.repositories import find_cliente_by_ruc, find_cliente_by_text, get_or_create_proveedor


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
    ocr_output = None

    if not text.strip():
        ocr_output = OCR_TMP_DIR / f"ocr_{pdf_path.name}"
        if run_ocr(pdf_path, ocr_output):
            text = extract_text_from_pdf(ocr_output)

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
            break

    cliente = None
    qr = fields.get("qr_data")
    if qr and qr.get("num_doc_adquirente"):
        cliente = find_cliente_by_ruc(qr.get("num_doc_adquirente"))
    if not cliente:
        cliente = find_cliente_by_text(text)

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
        return bool(fields.get("numero"))
    if tipo in ("nota_ingreso", "pago"):
        return bool(fields.get("numero"))
    return False


def create_lote(total: int) -> dict:
    codigo = "LOTE-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + str(uuid.uuid4())[:6]
    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            """
            INSERT INTO lotes_proceso (codigo_lote, carpeta_origen, total_archivos)
            VALUES (%s, %s, %s)
            RETURNING *
            """,
            (codigo, str(INPUT_DIR), total),
        )
        return cur.fetchone()


def next_grupo_codigo() -> str:
    # MVP temporal. Luego debe salir de una secuencia mensual en BD.
    return "04-" + datetime.now().strftime("%H%M")


def main() -> None:
    pdfs = sorted(INPUT_DIR.glob("*.pdf"))
    print(f"PDF encontrados: {len(pdfs)}")

    lote = create_lote(len(pdfs))
    docs = [enrich_pdf(pdf) for pdf in pdfs]

    factura_principal = next((d for d in docs if d["fields"].get("tipo_documental") == "factura"), None)
    cliente_global = factura_principal["cliente"] if factura_principal else None

    if not cliente_global:
        cliente_global = next((d["cliente"] for d in docs if d.get("cliente")), None)

    factura_sin_cliente = factura_principal is not None and cliente_global is None

    fecha_base = None
    if factura_principal:
        fecha_base = parse_iso_date(factura_principal["fields"].get("fecha_emision"))
    fecha_base = fecha_base or datetime.now().date()

    grupo_codigo = next_grupo_codigo()
    total_clasificados = total_revision = total_no_id = 0

    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            """
            INSERT INTO grupos_documentales (lote_id, grupo_codigo, cliente_destino_id, estado, observacion)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                lote["id"],
                grupo_codigo,
                cliente_global["id"] if cliente_global else None,
                "revision_manual" if factura_sin_cliente else "clasificado",
                "Factura sin cliente destino" if factura_sin_cliente else None,
            ),
        )
        grupo = cur.fetchone()

    for doc in docs:
        fields = doc["fields"]
        tipo = fields.get("tipo_documental")
        valido = is_valid_document(fields)

        if tipo == "otro":
            estado = "no_identificado"
            bucket = "no_identificados"
            total_no_id += 1
        elif factura_sin_cliente:
            estado = "revision_manual"
            bucket = "revision"
            total_revision += 1
        elif valido:
            estado = "clasificado"
            bucket = "clasificados"
            total_clasificados += 1
        else:
            estado = "revision_manual"
            bucket = "revision"
            total_revision += 1

        prefijo = cliente_global["abreviatura"] if cliente_global and not factura_sin_cliente else grupo_codigo
        proveedor = get_or_create_proveedor(fields.get("ruc"), None)

        nombre_final = build_final_name(
            prefijo_nombre=prefijo,
            tipo_documental=tipo,
            serie=fields.get("serie"),
            numero=fields.get("numero"),
            ruc_emisor=fields.get("ruc"),
            razon_social_emisor=None,
            fallback_name=doc["path"].name,
        )

        destino = OUTPUT_DIR / bucket / f"{fecha_base.year}" / f"{fecha_base.month:02d}" / nombre_final
        copy_file(doc["path"], destino)

        with get_cursor(commit=True) as (_, cur):
            cur.execute(
                """
                INSERT INTO documentos (
                    lote_id, grupo_id, cliente_destino_id, proveedor_id,
                    tipo_documental, serie, numero, ruc_emisor, razon_social_emisor,
                    fecha_emision, importe, igv, oc_numero, estado_documento,
                    observacion, nombre_original, nombre_final, ruta_origen, ruta_destino,
                    hash_sha256, paginas, es_principal, qr_raw
                )
                VALUES (
                    %(lote_id)s, %(grupo_id)s, %(cliente_destino_id)s, %(proveedor_id)s,
                    %(tipo_documental)s, %(serie)s, %(numero)s, %(ruc_emisor)s, %(razon_social_emisor)s,
                    %(fecha_emision)s, %(importe)s, %(igv)s, %(oc_numero)s, %(estado_documento)s,
                    %(observacion)s, %(nombre_original)s, %(nombre_final)s, %(ruta_origen)s, %(ruta_destino)s,
                    %(hash_sha256)s, %(paginas)s, %(es_principal)s, %(qr_raw)s
                )
                """,
                {
                    "lote_id": lote["id"],
                    "grupo_id": grupo["id"],
                    "cliente_destino_id": cliente_global["id"] if cliente_global else None,
                    "proveedor_id": proveedor["id"] if proveedor else None,
                    "tipo_documental": tipo,
                    "serie": fields.get("serie"),
                    "numero": fields.get("numero"),
                    "ruc_emisor": fields.get("ruc"),
                    "razon_social_emisor": None,
                    "fecha_emision": fields.get("fecha_emision"),
                    "importe": normalize_amount(fields.get("importe")),
                    "igv": normalize_amount(fields.get("igv")),
                    "oc_numero": fields.get("oc"),
                    "estado_documento": estado,
                    "observacion": "MVP local",
                    "nombre_original": doc["path"].name,
                    "nombre_final": nombre_final,
                    "ruta_origen": str(doc["path"]),
                    "ruta_destino": str(destino),
                    "hash_sha256": doc["hash"],
                    "paginas": doc["pages"],
                    "es_principal": doc is factura_principal,
                    "qr_raw": fields.get("qr_data", {}).get("qr_raw") if fields.get("qr_data") else None,
                },
            )

        print(f"[{estado}] {doc['path'].name} -> {nombre_final}")

    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            """
            UPDATE lotes_proceso
            SET estado=%s, total_clasificados=%s, total_revision=%s,
                total_no_identificados=%s, actualizado_en=NOW()
            WHERE id=%s
            """,
            ("procesado", total_clasificados, total_revision, total_no_id, lote["id"]),
        )

    print("Proceso finalizado.")


if __name__ == "__main__":
    main()
