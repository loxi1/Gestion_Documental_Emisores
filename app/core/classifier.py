from __future__ import annotations

import re
from typing import Any

from core.text_utils import normalize_text, compact_text
from core.qr_parser import extract_qr_candidates, parse_qr_payload
from core.dates import normalize_date

FACTURA_SERIE_RE = r"F[A-Z0-9]{3}"
FACTURA_NUMERO_RE = r"\d{1,8}"
GUIA_SERIE_RE = r"(?:T[A-Z0-9]{3}|GR[A-Z0-9]{2,3})"
GUIA_NUMERO_RE = r"\d{1,8}"
CLIENTE_RUCS = {"20299922821", "20565747356", "20613521004", "20614307197", "20612122416"}


def normalize_amount(value: str | None) -> float | None:
    if not value:
        return None
    raw = str(value).strip().replace(" ", "")
    if "," in raw and "." in raw:
        if raw.rfind(".") > raw.rfind(","):
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    raw = re.sub(r"[^0-9.\-]", "", raw)
    try:
        return float(raw)
    except Exception:
        return None


def detect_tipo_documental(text: str, file_name: str) -> str:
    text_u = normalize_text(text)
    name_u = normalize_text(file_name)
    compact = compact_text(text_u + " " + name_u)

    for candidate in extract_qr_candidates(text):
        qr = parse_qr_payload(candidate)
        if qr and qr.get("tipo_documental") in ("factura", "guia_remision"):
            return qr["tipo_documental"]

    if (
        "FACTURAELECTRONICA" in compact
        or re.search(rf"\b{FACTURA_SERIE_RE}\s*[- ]\s*{FACTURA_NUMERO_RE}\b", text_u)
        or re.search(rf"\b{FACTURA_SERIE_RE}\s*[- ]\s*{FACTURA_NUMERO_RE}\b", name_u)
        or re.search(rf"\b\d{{11}}-01-{FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE}\b", name_u)
    ):
        return "factura"

    if (
        "GUIADEREMISION" in compact
        or re.search(rf"\b{GUIA_SERIE_RE}\s*[- ]\s*{GUIA_NUMERO_RE}\b", text_u)
        or re.search(rf"\b{GUIA_SERIE_RE}\s*[- ]\s*{GUIA_NUMERO_RE}\b", name_u)
        or re.search(rf"\b\d{{11}}-09-{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b", name_u)
    ):
        return "guia_remision"

    if (
        re.search(r"ORDEN\s+DE\s+COM\w{0,4}.{0,120}?\d{4,}", text_u, re.I | re.S)
        or re.search(r"OC\s*BBTI.{0,80}?\d{4,}", text_u + " " + name_u, re.I | re.S)
        or re.search(r"\bOC[:\s-]*\d{4,}", text_u + " " + name_u, re.I)
        or re.search(r"\b\d{4,}\.PDF\b", name_u, re.I)
    ):
        return "orden_compra"

    if "NOTAINGRESO" in compact or re.search(r"\bNI[:\s-]*\d{3,}", text_u):
        return "nota_ingreso"

    if "PAGO" in compact and re.search(r"\b(OP|OPERACION|OPERACION N|NRO)\b", text_u):
        return "pago"

    return "otro"


def _extract_factura_fields(text_u: str, name_u: str) -> tuple[str | None, str | None]:
    for fuente in (text_u, name_u):
        m = re.search(rf"\b({FACTURA_SERIE_RE})\s*[- ]\s*({FACTURA_NUMERO_RE})\b", fuente, re.I)
        if m:
            return m.group(1), m.group(2)
    return None, None


def _extract_guia_fields(text_u: str, name_u: str) -> tuple[str | None, str | None]:
    for fuente in (text_u, name_u):
        m = re.search(rf"\b({GUIA_SERIE_RE})\s*[- ]\s*({GUIA_NUMERO_RE})\b", fuente, re.I)
        if m:
            return m.group(1), m.group(2)
    return None, None


def _extract_oc_fields(text_u: str, name_u: str) -> tuple[str | None, str | None]:
    fuentes = f"{text_u}\n{name_u}"
    patrones = [
        r"ORDEN\s+DE\s+COM\w{0,4}.{0,120}?([0-9]{4,})",
        r"OC\s*BBTI.{0,80}?([0-9]{4,})",
        r"\bOC[:\s-]*([0-9]{4,})\b",
        r"\b([0-9]{4,})\.PDF\b",
    ]
    for patron in patrones:
        m = re.search(patron, fuentes, re.I | re.S)
        if m and 4 <= len(m.group(1)) <= 8:
            return "OC", m.group(1)
    return None, None


def _extract_ruc_proveedor(text_u: str, doc_type: str, name_u: str) -> str | None:
    for patron in [
        rf"\b(\d{{11}})-01-{FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE}\b",
        rf"\b(\d{{11}})-09-{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b",
    ]:
        m = re.search(patron, name_u, re.I)
        if m:
            return m.group(1)

    rucs = re.findall(r"\b(20\d{9}|10\d{9})\b", text_u + "\n" + name_u)
    for ruc in rucs:
        if ruc not in CLIENTE_RUCS:
            return ruc
    return rucs[0] if rucs else None


def _extract_fecha(text_u: str) -> str | None:
    patrones = [
        r"FECHA\s+DE\s+EMISION\s*[:\-]?\s*([0-9]{2}/[0-9]{2}/[0-9]{4})",
        r"FECHA\s+DE\s+EMISION\s*[:\-]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        r"FECHA\s+DE\s+EMISION\s*[:\-]?\s*([0-9]{1,2}/[A-Z]{3}\.?/[0-9]{4})",
        r"F\.?\s*EMISION\s*[:\-]?\s*([0-9]{2}/[0-9]{2}/[0-9]{4})",
        r"(\d{1,2}/[A-Z]{3}\.?/\d{4})",
    ]
    for patron in patrones:
        m = re.search(patron, text_u, re.I | re.S)
        if m:
            return normalize_date(m.group(1))
    return None


def _extract_importe(text_u: str) -> str | None:
    patrones = [
        r"IMPORTE\s+TOTAL[:\sA-Z$/.]*([0-9][0-9,.\s]*)",
        r"TOTAL\s+A\s+PAGAR[:\s]*([0-9][0-9,.\s]*)",
        r"\bTOTAL\s*S/?\.?\s*([0-9][0-9,.\s]*)",
        r"\bTOTAL[:\s]*([0-9][0-9,.\s]*)",
    ]
    for patron in patrones:
        m = re.search(patron, text_u, re.I)
        if m:
            return m.group(1).strip()
    return None


def extract_basic_fields(text: str, file_name: str) -> dict[str, Any]:
    text_u = normalize_text(text)
    name_u = normalize_text(file_name)
    doc_type = detect_tipo_documental(text, file_name)

    qr_data = None
    for candidate in extract_qr_candidates(text):
        qr_data = parse_qr_payload(candidate)
        if qr_data:
            break

    if qr_data and qr_data.get("tipo_documental") in ("factura", "guia_remision"):
        return {
            "tipo_documental": qr_data["tipo_documental"],
            "serie": qr_data.get("serie"),
            "numero": qr_data.get("numero"),
            "ruc": qr_data.get("ruc_emisor"),
            "fecha_emision": normalize_date(qr_data.get("fecha_emision")),
            "importe": qr_data.get("importe"),
            "igv": qr_data.get("igv"),
            "oc": None,
            "qr_data": qr_data,
        }

    serie = numero = None
    if doc_type == "factura":
        serie, numero = _extract_factura_fields(text_u, name_u)
    elif doc_type == "guia_remision":
        serie, numero = _extract_guia_fields(text_u, name_u)
    elif doc_type == "orden_compra":
        serie, numero = _extract_oc_fields(text_u, name_u)

    _, oc_num = _extract_oc_fields(text_u, name_u)

    return {
        "tipo_documental": doc_type,
        "serie": serie,
        "numero": numero,
        "ruc": _extract_ruc_proveedor(text_u, doc_type, name_u),
        "fecha_emision": _extract_fecha(text_u),
        "importe": _extract_importe(text_u),
        "igv": None,
        "oc": oc_num,
        "qr_data": qr_data,
    }
