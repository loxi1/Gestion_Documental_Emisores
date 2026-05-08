import re
from pathlib import Path
from slugify import slugify

from core.text_utils import normalize_text


def norm(text: str) -> str:
    return normalize_text(text or "")


def compact_text(value: str | None) -> str:
    if not value:
        return ""
    value = normalize_text(value)
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def clean_name(text: str) -> str:
    return slugify(text or "SIN_RAZON_SOCIAL", separator="_").upper()


# ---------------------------------------------------------
# DETECTORES
# ---------------------------------------------------------

def is_guia_text(text: str, filename: str = "") -> bool:
    text_u = norm(text)
    name_u = norm(filename)
    compact = compact_text(text_u)

    tiene_guia_fuerte = bool(
        "GUIADEREMISIONELECTRONICA" in compact
        or "GUIAREMISIONELECTRONICA" in compact
        or "REPRESENTACIONIMPRESAGUIADEREMISION" in compact
        or "GUIADEREMISIONREMITENTE" in compact
        or re.search(r"GUIA\s+DE\s+REMISION\s+ELECTRONICA", text_u, re.I)
    )

    tiene_serie_guia = bool(
        re.search(r"\bT\d{3,4}\s*[- ]\s*\d{1,10}\b", text_u)
        or re.search(r"\bTG\d{2,4}\s*[- ]\s*\d{1,10}\b", text_u)
        or re.search(r"\bTGO\d{1,4}\s*[- ]\s*\d{1,10}\b", text_u)
        or re.search(r"\bEG\d{2,4}\s*[- ]\s*\d{1,10}\b", text_u)
        or re.search(r"\bEGO\d{1,4}\s*[- ]\s*\d{1,10}\b", text_u)
        or re.search(r"\bGR\d{2,4}\s*[- ]\s*\d{1,10}\b", text_u)
        or re.search(r"\bT\d{3,4}\s*[- ]\s*\d{1,10}\b", name_u)
    )

    return tiene_guia_fuerte or tiene_serie_guia


def is_orden_servicio_text(text: str) -> bool:
    t = norm(text)
    c = compact_text(t)

    return bool(
        "ORDENDESERVICIO" in c
        or re.search(r"ORDEN\s+DE\s+SERVICIO", t, re.I)
    )


def is_orden_compra_text(text: str) -> bool:
    t = norm(text)
    c = compact_text(t)

    return bool(
        "ORDENDECOMPRA" in c
        or re.search(r"ORDEN\s+DE\s+COMPRA", t, re.I)
        or re.search(r"\bO[./-]?C\.?\s*(N[°º*]?)?\s*[:\-]?\s*\d{3,8}\b", t, re.I)
    )


def is_nota_ingreso_text(text: str) -> bool:
    t = norm(text)
    c = compact_text(t)

    return bool(
        "NOTADEINGRESO" in c
        or re.search(r"NOTA\s+DE\s+INGRESO", t, re.I)
    )


def is_proforma_text(text: str, filename: str = "") -> bool:
    t = norm(text)
    name = norm(filename)

    return bool(
        "PROFORMA" in t
        or "PROFORMA INVOICE" in t
        or re.search(r"\bPI\s+\d+", t)
        or re.search(r"\bPI\s+\d+", name)
    )


def is_pago_text(text: str) -> bool:
    t = norm(text)

    return bool(
        "OPERACION" in t
        or "OPERACIÓN" in t
        or "PAGO" in t
        or "BANCO" in t
        or "CONSTANCIA" in t
        or "TRANSFERENCIA" in t
    )


def detect_tipo(text: str, archivo_fuente: str = "") -> str:
    t = norm(text)

    if is_proforma_text(t, archivo_fuente):
        return "proforma"

    if is_nota_ingreso_text(t):
        return "nota_ingreso"

    # NUEVO: factura primero
    if "FACTURA ELECTRONICA" in t or "FACTURA ELECTRÓNICA" in t or re.search(r"\b[A-Z]\d{3,4}\s*[-]\s*\d+\b", t):
        return "factura"

    if is_guia_text(t, archivo_fuente):
        return "guia_remision"

    if is_orden_servicio_text(t):
        return "orden_servicio"

    if is_orden_compra_text(t):
        return "orden_compra"

    if "FACTURA" in t:
        return "factura"

    if is_pago_text(t):
        return "pago"

    return "otro"


# ---------------------------------------------------------
# EXTRACTORES
# ---------------------------------------------------------

def extract_factura_from_filename(filename: str) -> dict:
    stem = Path(filename).stem.strip()

    m = re.search(
        r"^(?P<asiento>04-\d{4})\s+"
        r"(?P<serie>[A-Z0-9]{2,8})\s+"
        r"(?P<numero>\d+)\s+"
        r"(?P<ruc>(10|20)\d{9})\s+"
        r"(?P<razon>.+)$",
        stem,
        re.I,
    )

    if not m:
        return {
            "serie": None,
            "numero": None,
            "ruc": None,
            "razon_social_emisor": None,
            "clave": None,
        }

    serie = m.group("serie").upper()
    numero = m.group("numero")
    ruc = m.group("ruc")
    razon = m.group("razon").strip()

    return {
        "serie": serie,
        "numero": numero,
        "ruc": ruc,
        "razon_social_emisor": razon,
        "clave": f"FACTURA|{ruc}|{serie}|{numero}",
    }


def extract_guia_fields(text: str, filename: str = "") -> tuple[str | None, str | None]:
    text_u = norm(text)
    name_u = norm(filename)

    fuentes = [text_u, name_u]

    patrones = [

        # EGO07-1043
        r"\b((?:EGO|EG|TG|T|GR)[A-Z0-9]{1,3}\d{1,4})\s*[- ]\s*0*(\d{1,10})\b",

        # T001-12345
        r"\b(T\d{3,4})\s*[- ]\s*0*(\d{1,10})\b",

        # TG01-999
        r"\b(TG\d{2,4})\s*[- ]\s*0*(\d{1,10})\b",

        # EG07-555
        r"\b(EG\d{2,4})\s*[- ]\s*0*(\d{1,10})\b",

        # EGO07-444
        r"\b(EGO\d{2,4})\s*[- ]\s*0*(\d{1,10})\b",

        # GR01-222
        r"\b(GR\d{2,4})\s*[- ]\s*0*(\d{1,10})\b",
    ]

    for fuente in fuentes:

        fuente = fuente.upper()

        for patron in patrones:

            for m in re.finditer(patron, fuente, re.I):

                serie = m.group(1).upper()
                numero = m.group(2)

                # filtros basura OCR
                basura = {
                    "TOTAL",
                    "TELEF",
                    "TOOLS",
                    "GRAMSA",
                    "TORRES",
                    "TYPE",
                    "TECN",
                    "TASA",
                    "TB",
                }

                if serie in basura:
                    continue

                # serie debe contener números
                if not re.search(r"\d", serie):
                    continue

                return serie, numero

    return None, None


def extract_guia(text: str, filename: str = "") -> dict:
    t = norm(text)

    if not is_guia_text(t, filename):
        return {
            "serie": None,
            "numero": None,
            "ruc": None,
            "clave": None,
        }

    serie, numero = extract_guia_fields(t, filename)

    ruc = re.search(r"\b(10|20)\d{9}\b", t)
    ruc_val = ruc.group(0) if ruc else None

    return {
        "serie": serie,
        "numero": numero,
        "ruc": ruc_val,
        "clave": (
            f"GUIA|{ruc_val or 'SINRUC'}|{serie}|{numero}"
            if serie and numero else None
        ),
    }


def extract_os(text: str) -> dict:
    t = norm(text)

    if not is_orden_servicio_text(t):
        return {"numero": None, "clave": None}

    patrones = [
        r"\bN[°º*?]?\s*:?\s*(\d{3,8})\b",
        r"ORDEN\s+DE\s+SERVICIO\s*(?:N[°º*?])?\s*:?\s*(\d{3,8})\b",
        r"\bOS\s*:?\s*(\d{3,8})\b",
    ]

    for patron in patrones:
        m = re.search(patron, t, re.I)
        if m:
            numero = m.group(1).zfill(6)
            return {
                "numero": numero,
                "clave": f"OS|{numero}",
            }

    return {"numero": None, "clave": None}


def extract_oc(text: str) -> dict:
    t = norm(text)

    if not is_orden_compra_text(t):
        return {"numero": None, "clave": None}

    patrones = [
        r"ORDEN\s+DE\s+COMPRA\s*(?:N[°º*?])?\s*:?\s*(\d{3,8})\b",
        r"\bO[./-]?C\.?\s*(?:N[°º*?])?\s*:?\s*(\d{3,8})\b",
        r"OBSERVACIONES\s*:?.*?ORDEN\s+DE\s+COMPRA\s*N[°º*?]?\s*(\d{3,8})\b",
    ]

    for patron in patrones:
        m = re.search(patron, t, re.I | re.S)
        if m:
            numero = m.group(1).zfill(6)
            return {
                "numero": numero,
                "clave": f"OC|{numero}",
            }

    return {"numero": None, "clave": None}


def extract_ni(text: str) -> dict:
    t = norm(text)

    if not is_nota_ingreso_text(t):
        return {"numero": None, "clave": None}

    patrones = [
        r"NOTA\s+DE\s+INGRESO\s*(?:N[°º*?])?\s*:?\s*(\d{3,10})\b",
        r"\bNI\s*:?\s*(\d{3,10})\b",
        r"\b(\d{3,10})\b",
    ]

    for patron in patrones:
        m = re.search(patron, t, re.I)
        if m:
            numero = m.group(1).zfill(6)
            return {
                "numero": numero,
                "clave": f"NI|{numero}",
            }

    return {"numero": None, "clave": None}


# ---------------------------------------------------------
# ENRICH PRINCIPAL
# ---------------------------------------------------------

def enrich_page(text: str, archivo_fuente: str = "") -> dict:
    tipo = detect_tipo(text, archivo_fuente)

    data = {
        "tipo": tipo,
        "serie": None,
        "numero": None,
        "ruc": None,
        "razon_social_emisor": None,
        "orden_servicio": None,
        "orden_compra": None,
        "clave_documental": None,
    }

    if tipo == "factura":
        f = extract_factura_from_filename(archivo_fuente)
        data.update({
            "serie": f["serie"],
            "numero": f["numero"],
            "ruc": f["ruc"],
            "razon_social_emisor": f["razon_social_emisor"],
            "clave_documental": f["clave"],
        })

    elif tipo == "guia_remision":
        g = extract_guia(text, archivo_fuente)
        data.update({
            "serie": g["serie"],
            "numero": g["numero"],
            "ruc": g["ruc"],
            "clave_documental": g["clave"],
        })

    elif tipo == "orden_servicio":
        os_data = extract_os(text)
        data.update({
            "orden_servicio": os_data["numero"],
            "clave_documental": os_data["clave"],
        })

    elif tipo == "orden_compra":
        oc_data = extract_oc(text)
        data.update({
            "orden_compra": oc_data["numero"],
            "clave_documental": oc_data["clave"],
        })

    elif tipo == "nota_ingreso":
        ni = extract_ni(text)
        data.update({
            "numero": ni["numero"],
            "clave_documental": ni["clave"],
        })

    return data