from __future__ import annotations

import re


VALID_SERIES_PREFIXES = (
    "T",
    "TG",
    "EG",
)


INVALID_SERIES_WORDS = {
    "TIDAD",
    "TREGA",
    "TAL",
    "TARIO",
    "DON",
    "MARCA",
    "PESO",
    "DATOS",
    "RUC",
    "DESTINO",
    "TRANSPORTE",
}


def norm_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").upper()).strip()


def is_valid_guia_serie(serie: str | None) -> bool:
    if not serie:
        return False

    s = serie.upper().strip()

    if s in INVALID_SERIES_WORDS:
        return False

    if len(s) < 3:
        return False

    if not any(s.startswith(p) for p in VALID_SERIES_PREFIXES):
        return False

    if not re.match(r"^[A-Z0-9]+$", s):
        return False

    if len(re.findall(r"[A-Z]", s)) > 2 and not re.search(r"\d", s):
        return False

    return True


def normalize_serie_guia(serie: str | None) -> str | None:
    if not serie:
        return None

    s = serie.upper().strip()

    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^A-Z0-9]", "", s)

    replacements = {
        "TGO0O": "TG00",
        "TGOO": "TG00",
        "TGO": "TG0",
        "TOO": "T00",
        "TO0": "T00",
        "T0O": "T00",
        "EGO": "EG0",
        "EGOO": "EG00",
    }

    for old, new in replacements.items():
        s = s.replace(old, new)

    s = re.sub(r"^EG0+([1-9][0-9]*)$", r"EG\1", s)
    s = re.sub(r"^TG0+([1-9][0-9]*)$", r"TG\1", s)
    s = re.sub(r"^T0+([1-9][0-9]*)$", r"T\1", s)

    if len(s) > 6:
        return None

    if not any(s.startswith(p) for p in VALID_SERIES_PREFIXES):
        return None

    if not re.match(r"^[A-Z]{1,3}[0-9]{1,4}$", s):
        return None

    if not is_valid_guia_serie(s):
        return None

    return s


def is_sunat_guia_text(text: str | None) -> bool:
    t = norm_text(text)

    return bool(
        "GUIA DE REMISION ELECTRONICA" in t
        or "GUÍA DE REMISIÓN ELECTRÓNICA" in t
        or "GUIA DE REMISION REMITENTE" in t
        or "GUÍA DE REMISIÓN REMITENTE" in t
        or "GUIA REMITENTE ELECTRONICA" in t
        or "GUÍA REMITENTE ELECTRÓNICA" in t
    )


def extract_ruc_emisor(text: str | None) -> str | None:
    t = norm_text(text)

    patterns = [
        r"RUC\s*N?[°º*]?\s*:?\s*((10|20)\d{9})",
        r"R\.?U\.?C\.?\s*:?\s*((10|20)\d{9})",
        r"\b((10|20)\d{9})\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, t, re.I)

        if m:
            return m.group(1)

    return None


def extract_guia_serie_numero(
    text: str | None,
) -> tuple[str | None, str | None]:
    t = norm_text(text)

    patterns = [
        r"N[°º*]?\s*:?\s*([A-Z0-9]{3,6})\s*[- ]\s*0*(\d{1,10})",
        r"\b(TG\d{2,5}|EG\d{2,5}|T\d{3,5})\s*[- ]\s*0*(\d{1,10})\b",
        r"\b(TGO0O\d?|TGOO\d?|TGO\d?|EGO\d?|TOO\d?|TO0\d?)\s*[- ]?\s*0*(\d{1,10})\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, t, re.I)

        if not m:
            continue

        serie = normalize_serie_guia(m.group(1))
        numero = m.group(2).lstrip("0") or "0"

        if (
            serie
            and numero
            and is_valid_guia_serie(serie)
        ):
            return serie, numero

    return None, None


def parse_sunat_guia_from_text(text: str | None) -> dict | None:
    if not is_sunat_guia_text(text):
        return None

    serie, numero = extract_guia_serie_numero(text)
    ruc = extract_ruc_emisor(text)

    if not serie or not numero:
        return None

    return {
        "tipo_documental": "guia_remision",
        "serie": serie,
        "numero": numero,
        "ruc_emisor": ruc,
        "clave_documental": f"GUIA|{ruc or 'SINRUC'}|{serie}|{numero}",
    }