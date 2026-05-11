import re
import unicodedata
from pathlib import Path
from slugify import slugify

from core.text_utils import normalize_text, compact_text


CLIENTES_DESTINO = {
    "BBTEC": {
        "nombre": "BB TECNOLOGIA INDUSTRIAL S.A.C.",
        "ruc": "20299922821",
    },
    "BBTI": {
        "nombre": "BBTI S.A.C.",
        "ruc": "20565747356",
    },
    "CIMA": {
        "nombre": "CONSORCIO CIMA ENERGY",
        "ruc": "20613521004",
    },
    "TARMA": {
        "nombre": "CONSORCIO ILUMINACION TARMA 2025",
        "ruc": "20614307197",
    },
    "HUANCA": {
        "nombre": "CONSORCIO HUANCAVELICA",
        "ruc": "20612122416",
    },
    "KIMBIRI": {
        "nombre": "CONSORCIO KIMBIRI",
        "ruc": "20609856140",
    },
}


BANCOS = {
    "BCP": ["BCP", "BANCO DE CREDITO", "BANCO DE CRÉDITO"],
    "BBVA": ["BBVA", "BANCO BBVA", "BANCO CONTINENTAL"],
    "IBK": ["INTERBANK", "BANCO INTERNACIONAL DEL PERU", "BANCO INTERNACIONAL DEL PERÚ"],
    "SCO": ["SCOTIABANK", "SCOTIABANK PERU", "SCOTIABANK PERÚ"],
    "PIC": ["PICHINCHA", "BANCO PICHINCHA"],
    "BANBIF": ["BANBIF", "BANCO INTERAMERICANO DE FINANZAS"],
    "BN": ["BANCO DE LA NACION", "BANCO DE LA NACIÓN", "NACION"],
    "CITI": ["CITIBANK", "CITIBANK PERU", "CITIBANK PERÚ"],
    "COM": ["BANCO DE COMERCIO"],
}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").upper()).strip()


def clean_name(text: str) -> str:
    return slugify(text or "SIN_RAZON_SOCIAL", separator="_").upper()


def normalize_serie(serie: str | None) -> str | None:
    if not serie:
        return None

    s = serie.upper().strip()
    s = s.replace(" ", "")

    replacements = {
        "TOO": "T00",
        "TO0": "T00",
        "TGO0O": "TG00",
        "TGOO": "TG00",
        "TGO": "TG0",
        "EGO": "EG0",
        "EGOO": "EG00",
    }

    for old, new in replacements.items():
        s = s.replace(old, new)

    return s


def tiene_cliente_destino(text: str, cliente: str) -> bool:
    t = norm(text)
    data = CLIENTES_DESTINO.get((cliente or "").upper())

    if not data:
        return False

    return data["nombre"] in t and data["ruc"] in t


def extract_oc_from_text(text: str) -> str | None:
    t = norm(text)

    patterns = [
        r"\bO\s*/\s*C\.?\s*:?\s*0*(\d{3,8})",
        r"\bO\s*C\s*:?\s*0*(\d{3,8})",
        r"\bOC\s*:?\s*0*(\d{3,8})",
        r"\bO/C\s*:?\s*0*(\d{3,8})",
        r"ORDEN\s+DE\s+COMPRA\s+N?[°º*?:]?\s*0*(\d{3,8})",
    ]

    for pattern in patterns:
        m = re.search(pattern, t, re.I)
        if m:
            return m.group(1).zfill(6)

    return None


def is_pago_detraccion_text(text: str) -> bool:
    t = norm(text)
    c = compact_text(t)

    return bool(
        "SISTEMADEPAGODEOBLIGACIONESTRIBUTARIAS" in c
        or "DLEG940" in c
        or "DETRACCION" in t
        or "DETRACCIONES" in t
        or "MONTO DEPOSITO" in t
        or "MONTO DEL DEPOSITO" in t
        or "NUMERO DE PAGO DE DETRACCIONES" in t
        or "PAGO DE DETRACCIONES" in t
        or "N CUENTA DE DETRACCIONES" in t
        or "CUENTA DE DETRACCIONES" in t
    )


def is_pago_transferencia_text(text: str) -> bool:
    t = norm(text)
    c = compact_text(t)

    return bool(
        "TRANSFERENCIAS" in t
        or "TRANSFERENCIA INTERBANCARIA" in t
        or "TRANSFERENCIA A CUENTAS DE TERCEROS" in t
        or "CONSTANCIA DE OPERACION" in t
        or "CONSTANCIADEOPERACION" in c
        or "IMPORTE TRANSFERIDO" in t
        or "IMPORTE CARGADO" in t
        or "CUENTA DE CARGO" in t
        or "CUENTA DE ABONO" in t
        or "NUMERO DE OPERACION" in t
        or "CODIGO DE SOLICITUD" in t
    )


def is_nota_ingreso_text(text: str) -> bool:
    t = norm(text)
    c = compact_text(t)

    return bool(
        "NOTADEINGRESO" in c
        or re.search(r"NOTA\s+DE\s+INGRESO\s*(?:N[°º*?])?\s*:?\s*\d{3,10}", t, re.I)
    )


def is_orden_compra_text(text: str, cliente: str = "BBTEC") -> bool:
    t = norm(text)

    if not tiene_cliente_destino(t, cliente):
        return False

    return bool(
        re.search(
            r"ORDEN\s+DE\s+COMPRA\s+N[°º*?]?\s*:?\s*\d{3,8}",
            t,
            re.I,
        )
    )


def is_orden_servicio_text(text: str, cliente: str = "BBTEC") -> bool:
    t = norm(text)

    if not tiene_cliente_destino(t, cliente):
        return False

    return bool(
        re.search(
            r"ORDEN\s+DE\s+SERVICIO\s+N[°º*?]?\s*:?\s*\d{3,8}",
            t,
            re.I,
        )
    )


def is_guia_text(text: str, filename: str = "") -> bool:
    t = norm(text)
    c = compact_text(t)

    return bool(
        "GUIADEREMISION" in c
        or "GUIA DE REMISION" in t
        or "GUÍA DE REMISIÓN" in t
        or "MOTIVO DEL TRASLADO" in t
        or "DATOS DEL TRANSPORTISTA" in t
        or "INFORMACION DE BIENES TRASLADADOS" in t
        or "INFORMACIÓN DE BIENES TRASLADADOS" in t
        or "DIRECCION DE PARTIDA" in t
        or "DIRECCIÓN DE PARTIDA" in t
    )


def is_factura_text(text: str, filename: str = "") -> bool:
    t = norm(text)
    c = compact_text(t)
    name = norm(filename)

    return bool(
        "FACTURAELECTRONICA" in c
        or "FACTURA ELECTRONICA" in t
        or "FACTURA ELECTRÓNICA" in t
        or "REPRESENTACION IMPRESA DE LA FACTURA" in t
        or "REPRESENTACIÓN IMPRESA DE LA FACTURA" in t
        or re.search(r"\b(F[A-Z0-9]{2,4})\s*[- ]\s*\d{1,10}\b", t)
        or re.search(r"\b(F[A-Z0-9]{2,4})\s+\d{1,10}\b", name)
    )


def detect_tipo(text: str, archivo_fuente: str = "", cliente: str = "BBTEC") -> str:
    t = norm(text)

    if is_pago_detraccion_text(t):
        return "pago_detraccion"

    if is_pago_transferencia_text(t):
        return "pago_transferencia"

    if is_nota_ingreso_text(t):
        return "nota_ingreso"

    if is_orden_servicio_text(t, cliente):
        return "orden_servicio"

    if is_orden_compra_text(t, cliente):
        return "orden_compra"

    if is_guia_text(t, archivo_fuente):
        return "guia_remision"

    if is_factura_text(t, archivo_fuente):
        return "factura"

    return "otro"


def extract_factura_from_filename(filename: str) -> dict:
    stem = Path(filename).stem.strip()

    m = re.search(
        r"^(?P<asiento>04-\d{4})\s+"
        r"(?P<serie>[A-Z0-9]{2,6})\s+"
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

    serie = normalize_serie(m.group("serie"))
    numero = m.group("numero").lstrip("0") or "0"
    ruc = m.group("ruc")
    razon = m.group("razon").strip()

    return {
        "serie": serie,
        "numero": numero,
        "ruc": ruc,
        "razon_social_emisor": razon,
        "clave": f"FACTURA|{ruc}|{serie}|{numero}" if serie and numero and ruc else None,
    }


def extract_factura_from_text(text: str) -> dict:
    t = norm(text)

    serie_num = re.search(r"\b(F[A-Z0-9]{2,4})\s*[- ]\s*0*(\d{1,10})\b", t)
    ruc = re.search(r"\b(10|20)\d{9}\b", t)

    serie = normalize_serie(serie_num.group(1)) if serie_num else None
    numero = serie_num.group(2).lstrip("0") if serie_num else None
    ruc_val = ruc.group(0) if ruc else None

    return {
        "serie": serie,
        "numero": numero,
        "ruc": ruc_val,
        "clave": f"FACTURA|{ruc_val or 'SINRUC'}|{serie}|{numero}" if serie and numero else None,
    }


def extract_guia_fields(text: str, filename: str = "") -> tuple[str | None, str | None]:
    t = norm(text)

    patterns = [
        r"GUIA\s*(?:DE\s*REMISION)?\s*[:\-]?\s*([A-Z0-9]{3,6})\s*[- ]\s*0*(\d{1,10})",
        r"GUÍA\s*(?:DE\s*REMISIÓN)?\s*[:\-]?\s*([A-Z0-9]{3,6})\s*[- ]\s*0*(\d{1,10})",
        r"\b([TEG][A-Z0-9]{2,5})\s*[- ]\s*0*(\d{1,10})\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, t, re.I)
        if m:
            return normalize_serie(m.group(1)), m.group(2).lstrip("0") or "0"

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
        "clave": f"GUIA|{ruc_val or 'SINRUC'}|{serie}|{numero}" if serie and numero else None,
    }


def extract_os(text: str, cliente: str = "BBTEC") -> dict:
    t = norm(text)

    if not is_orden_servicio_text(t, cliente):
        return {"numero": None, "clave": None}

    m = re.search(
        r"ORDEN\s+DE\s+SERVICIO\s+N[°º*?]?\s*:?\s*0*(\d{3,8})",
        t,
        re.I,
    )

    if not m:
        return {"numero": None, "clave": None}

    numero = m.group(1).zfill(6)
    return {"numero": numero, "clave": f"OS|{numero}"}


def extract_oc(text: str, cliente: str = "BBTEC") -> dict:
    t = norm(text)

    if not is_orden_compra_text(t, cliente):
        return {"numero": None, "clave": None}

    numero = extract_oc_from_text(t)

    return {
        "numero": numero,
        "clave": f"OC|{numero}" if numero else None,
    }


def extract_ni(text: str) -> dict:
    t = norm(text)

    if not is_nota_ingreso_text(t):
        return {"numero": None, "clave": None}

    patrones = [
        r"NOTA\s+DE\s+INGRESO\s*(?:N[°º*?])?\s*:?\s*(\d{3,10})\b",
        r"\bNI\s*[:\-]\s*(\d{3,10})\b",
    ]

    for patron in patrones:
        m = re.search(patron, t, re.I)
        if m:
            numero = m.group(1).zfill(6)
            return {"numero": numero, "clave": f"NI|{numero}"}

    return {"numero": None, "clave": None}


def detect_banco(text: str) -> str | None:
    t = norm(text)

    for abrev, aliases in BANCOS.items():
        for alias in aliases:
            if norm(alias) in t:
                return abrev

    return None


def extract_codigo_operacion(text: str, banco: str | None = None) -> str | None:
    t = norm(text)

    patrones = [
        r"NUMERO\s+DE\s+OPERACION\s*:?\s*([0-9,\-\s]{3,30})",
        r"N[°º]\s*DE\s*OPERACION\s*:?\s*([0-9,\-\s]{3,30})",
        r"CODIGO\s+DE\s+SOLICITUD\s*:?\s*(\d{5,30})",
        r"CODIGO\s+OPERACION\s*:?\s*(\d{3,30})",
        r"NUMERO\s+DE\s+CONSTANCIA\s*:?\s*(\d{5,30})",
    ]

    for patron in patrones:
        m = re.search(patron, t, re.I)
        if m:
            return re.sub(r"\s+", "", m.group(1).replace(",", ""))

    return None


def extract_pago_transferencia(text: str) -> dict:
    banco = detect_banco(text)
    codigo = extract_codigo_operacion(text, banco)

    clave = None
    if banco and codigo:
        clave = f"PAGO_TRANSFERENCIA|{banco}|{codigo}"

    return {
        "banco": banco,
        "codigo_operacion": codigo,
        "clave": clave,
    }


def extract_pago_detraccion(text: str, archivo_fuente: str = "") -> dict:
    t = norm(text)

    f = extract_factura_from_filename(archivo_fuente)

    ruc = f.get("ruc")
    serie = f.get("serie")
    numero = f.get("numero")

    ruc_patterns = [
        r"RUC\s+DEL\s+PROVEEDOR\s*:?\s*((10|20)\d{9})",
        r"NUMERO\s+DE\s+DOCUMENTO\s+DEL\s+PROVEEDOR\s*:?\s*((10|20)\d{9})",
        r"RUC\s*:?\s*((10|20)\d{9})",
    ]

    for pattern in ruc_patterns:
        m = re.search(pattern, t, re.I)
        if m:
            ruc = m.group(1)
            break

    comp_m = re.search(
        r"NUMERO\s+DE\s+COMPROBANTE\s*:?\s*([A-Z0-9]{3,6})\s*[- ]?\s*0*(\d{1,10})",
        t,
        re.I,
    )

    if comp_m:
        serie = normalize_serie(comp_m.group(1))
        numero = comp_m.group(2).lstrip("0") or "0"

    codigo = extract_codigo_operacion(text, "BN")

    clave = None
    if ruc and serie and numero:
        clave = f"PAGO_DETRACCION|{ruc}|{serie}|{numero}"
    elif codigo:
        clave = f"PAGO_DETRACCION|BN|{codigo}"

    return {
        "banco": "BN",
        "codigo_operacion": codigo,
        "serie": serie,
        "numero": numero,
        "ruc": ruc,
        "clave": clave,
    }


def enrich_page(text: str, archivo_fuente: str = "", cliente: str = "BBTEC") -> dict:
    tipo = detect_tipo(text, archivo_fuente, cliente)
    oc_num = extract_oc_from_text(text)

    data = {
        "tipo": tipo,
        "serie": None,
        "numero": None,
        "ruc": None,
        "razon_social_emisor": None,
        "orden_servicio": None,
        "orden_compra": oc_num,
        "clave_documental": None,
        "banco": None,
        "codigo_operacion": None,
    }

    if tipo == "factura":
        f = extract_factura_from_filename(archivo_fuente)

        if not f["clave"]:
            f_text = extract_factura_from_text(text)
            f.update({
                "serie": f_text["serie"],
                "numero": f_text["numero"],
                "ruc": f_text["ruc"],
                "clave": f_text["clave"],
            })

        data.update({
            "serie": f["serie"],
            "numero": f["numero"],
            "ruc": f["ruc"],
            "razon_social_emisor": f["razon_social_emisor"],
            "orden_compra": oc_num,
            "clave_documental": f["clave"],
        })

    elif tipo == "guia_remision":
        g = extract_guia(text, archivo_fuente)
        data.update({
            "serie": g["serie"],
            "numero": g["numero"],
            "ruc": g["ruc"],
            "orden_compra": oc_num,
            "clave_documental": g["clave"],
        })

    elif tipo == "orden_servicio":
        os_data = extract_os(text, cliente)
        data.update({
            "orden_servicio": os_data["numero"],
            "clave_documental": os_data["clave"],
        })

    elif tipo == "orden_compra":
        oc_data = extract_oc(text, cliente)
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

    elif tipo == "pago_transferencia":
        p = extract_pago_transferencia(text)
        data.update({
            "banco": p["banco"],
            "codigo_operacion": p["codigo_operacion"],
            "clave_documental": p["clave"],
        })

    elif tipo == "pago_detraccion":
        p = extract_pago_detraccion(text, archivo_fuente)
        data.update({
            "banco": p["banco"],
            "codigo_operacion": p["codigo_operacion"],
            "serie": p["serie"],
            "numero": p["numero"],
            "ruc": p["ruc"],
            "clave_documental": p["clave"],
        })

    return data