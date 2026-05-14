import re
from pathlib import Path
from slugify import slugify

from core.text_utils import compact_text
from core.sunat_text_parser import parse_sunat_guia_from_text


CLIENTES_DESTINO = {
    "BBTEC": {"nombre": "BB TECNOLOGIA INDUSTRIAL S.A.C.", "ruc": "20299922821"},
    "BBTI": {"nombre": "BBTI S.A.C.", "ruc": "20565747356"},
    "CIMA": {"nombre": "CONSORCIO CIMA ENERGY", "ruc": "20613521004"},
    "TARMA": {"nombre": "CONSORCIO ILUMINACION TARMA 2025", "ruc": "20614307197"},
    "HUANCA": {"nombre": "CONSORCIO HUANCAVELICA", "ruc": "20612122416"},
    "KIMBIRI": {"nombre": "CONSORCIO KIMBIRI", "ruc": "20609856140"},
}

BANCOS = {
    "BCP": ["BCP", "BANCO DE CREDITO", "BANCO DE CRÉDITO"],
    "BBVA": ["BBVA", "BANCO BBVA", "BANCO CONTINENTAL"],
    "IBK": ["INTERBANK", "BANCO INTERNACIONAL DEL PERU", "BANCO INTERNACIONAL DEL PERÚ"],
    "SCO": ["SCOTIABANK", "SCOTIABANK PERU", "SCOTIABANK PERÚ"],
    "PIC": ["PICHINCHA", "BANCO PICHINCHA"],
    "BANBIF": ["BANBIF", "BANCO INTERAMERICANO DE FINANZAS"],
    "BN": ["BANCO DE LA NACION", "BANCO DE LA NACIÓN"],
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

    s = serie.upper().strip().replace(" ", "")

    # OCR comunes
    s = s.replace("FO", "F0")
    s = s.replace("TOO", "T00")
    s = s.replace("TO0", "T00")
    s = s.replace("T0O", "T00")
    s = s.replace("TGO0O", "TG00")
    s = s.replace("TGOO", "TG00")
    s = s.replace("TGO", "TG0")
    s = s.replace("EGO", "EG0")

    return s


def es_serie_guia_valida(serie: str | None) -> bool:
    if not serie:
        return False

    s = normalize_serie(serie)

    invalidas = {
        "TOTAL", "TASA", "TALM", "TICINO", "GARCIA", "ENE",
        "CTA", "CARGO", "BANCO", "SOLES", "DOLARES"
    }

    if s in invalidas:
        return False

    return bool(
        re.match(r"^T\d{3,5}$", s)
        or re.match(r"^TG\d{2,5}$", s)
        or re.match(r"^EG\d{2,5}$", s)
        or re.match(r"^T[A-Z]\d{2,5}$", s)
    )


def tiene_cliente_destino(text: str, cliente: str) -> bool:
    t = norm(text)
    data = CLIENTES_DESTINO.get((cliente or "").upper())

    if not data:
        return False

    return data["nombre"] in t and data["ruc"] in t


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
        "clave": f"FACTURA|{ruc}|{serie}|{numero}",
    }


def extract_oc_from_text(text: str) -> str | None:
    t = norm(text)

    patterns = [
        r"ORDEN\s+DE\s+COMPRA\s+N[^0-9]{0,12}0*(\d{3,8})",
        r"ORDEN\s+DE\s+COMPRA[^0-9]{0,25}0*(\d{3,8})",
        r"\bO\/C[^0-9]{0,12}0*(\d{3,8})",
        r"\bOC[^0-9]{0,12}0*(\d{3,8})",
    ]

    for pattern in patterns:
        m = re.search(pattern, t, re.I)
        if m:
            return m.group(1).zfill(6)

    return None


def extract_os_from_text(text: str) -> str | None:
    t = norm(text)

    patterns = [
        r"ORDEN\s+DE\s+SERVICIO\s*[:.\-]?\s*N[°º*.:;\-]*\s*0*(\d{3,8})",
        r"ORDEN\s+DE\s+SERVICIO\s+N[°º*.:;\-]*\s*0*(\d{3,8})",
        r"\bO\/S\s*[:.\-]*\s*0*(\d{3,8})",
        r"\bOS\s*[:.\-]*\s*0*(\d{3,8})",
    ]

    for pattern in patterns:
        m = re.search(pattern, t, re.I)
        if m:
            return m.group(1).zfill(6)

    return None


def is_pago_detraccion_text(text: str) -> bool:
    t = norm(text)
    c = compact_text(t)

    if is_factura_text(t):
        return False

    return bool(
        "SISTEMADEPAGODEOBLIGACIONESTRIBUTARIAS" in c
        or "NUMERO DE PAGO DE DETRACCIONES" in t
        or "PAGO DE DETRACCIONES" in t
        or (
            "NUMERO DE OPERACION" in t
            and "NUMERO DE COMPROBANTE" in t
            and "MONTO" in t
        )
    )


def is_pago_transferencia_text(text: str) -> bool:
    t = norm(text)
    c = compact_text(t)

    return bool(
        "CONSTANCIADEOPERACION" in c
        or "CONSTANCIA DE OPERACION" in t
        or "IMPORTE TRANSFERIDO" in t
        or "IMPORTE CARGADO" in t
        or "CUENTA DE CARGO" in t and "CUENTA DE ABONO" in t
        or "CODIGO DE SOLICITUD" in t
        or "NUMERO DE OPERACION" in t and ("TRANSFERENCIA" in t or "ABONADA" in t)
    )


def is_nota_ingreso_text(text: str) -> bool:
    t = norm(text)
    c = compact_text(t)

    return bool(
        "NOTADEINGRESO" in c
        or re.search(r"NOTA\s+DE\s+INGRESO\D{0,25}(\d{3,10})", t, re.I)
    )


def is_orden_compra_text(text: str, cliente: str = "BBTEC") -> bool:
    t = norm(text)

    if not tiene_cliente_destino(t, cliente):
        return False

    return bool(
        re.search(
            r"ORDEN\s+DE\s+COMPRA\s+N[°º*?:]?\s*:?\s*0*(\d{3,10})",
            t,
            re.I,
        )
    )


def is_orden_servicio_text(text: str, cliente: str = "BBTEC") -> bool:
    t = norm(text)

    if not tiene_cliente_destino(t, cliente):
        return False

    return extract_os_from_text(t) is not None


def is_factura_text(text: str, filename: str = "") -> bool:
    t = norm(text)
    c = compact_text(t)

    if is_documento_extranjero_o_proforma(t):
        return False

    return bool(
        "FACTURAELECTRONICA" in c
        or "FACTURA ELECTRONICA" in t
        or "FACTURA ELECTRÓNICA" in t
        or "REPRESENTACION IMPRESA DE LA FACTURA" in t
        or "REPRESENTACIÓN IMPRESA DE LA FACTURA" in t
        or "TIPO DE COMPROBANTE : FACTURA" in t
        or "TIPO DE COMPROBANTE: FACTURA" in t
    )


def is_guia_text(text: str, filename: str = "") -> bool:
    t = norm(text)
    c = compact_text(t)

    return bool(
        "GUIADEREMISIONELECTRONICA" in c
        or "GUIA DE REMISION ELECTRONICA" in t
        or "GUÍA DE REMISIÓN ELECTRÓNICA" in t
        or "GUIA DE REMISION REMITENTE" in t
        or "DATOS DEL TRANSPORTISTA" in t
        or "MOTIVO DE TRASLADO" in t
        or "DATOS DEL TRASLADO" in t
        or "INFORMACION DE BIENES TRASLADADOS" in t
        or "BIENES POR TRANSPORTAR" in t
        or "PESO BRUTO TOTAL DE LA CARGA" in t
    )


def detect_tipo(text: str, archivo_fuente: str = "", cliente: str = "BBTEC") -> str:
    t = norm(text)

    if is_documento_extranjero_o_proforma(t):
        return "otro"

    if is_guia_text(t, archivo_fuente) or is_guia_visual_text(t):
        return "guia_remision"

    if is_factura_text(t, archivo_fuente):
        return "factura"

    if is_orden_servicio_text(t, cliente):
        return "orden_servicio"

    if is_orden_compra_text(t, cliente):
        return "orden_compra"

    if is_nota_ingreso_text(t):
        return "nota_ingreso"

    if is_pago_detraccion_text(t):
        return "pago_detraccion"

    if is_pago_transferencia_text(t):
        return "pago_transferencia"

    return "otro"


def extract_factura_from_text(text: str) -> dict:
    t = norm(text)

    patterns = [
        r"\b(F[A-Z0-9]{2,5})\s*[- ]\s*0*(\d{1,10})\b",
        r"\b(FO\d{2})\s*[- ]\s*0*(\d{1,10})\b",
    ]

    serie = None
    numero = None

    for p in patterns:
        m = re.search(p, t, re.I)
        if m:
            serie = normalize_serie(m.group(1))
            numero = m.group(2).lstrip("0") or "0"
            break

    ruc = re.search(r"\b(10|20)\d{9}\b", t)
    ruc_val = ruc.group(0) if ruc else None

    return {
        "serie": serie,
        "numero": numero,
        "ruc": ruc_val,
        "clave": f"FACTURA|{ruc_val or 'SINRUC'}|{serie}|{numero}" if serie and numero else None,
    }


def extract_guia_fields(text: str) -> tuple[str | None, str | None]:
    t = norm(text)

    patterns = [
        r"GUIA\s+DE\s+REMISION\s+(?:REMITENTE)?\s*[:\-]?\s*([A-Z0-9]{3,6})\s*[- ]\s*0*(\d{1,10})",
        r"GUÍA\s+DE\s+REMISIÓN\s+(?:REMITENTE)?\s*[:\-]?\s*([A-Z0-9]{3,6})\s*[- ]\s*0*(\d{1,10})",
        r"GUIA\s*[:\-]\s*([A-Z0-9]{3,6})\s*[- ]\s*0*(\d{1,10})",
        r"\b(T\d{3,5}|T[A-Z]\d{2,5}|TG\d{2,5}|EG\d{2,5})\s*[- ]\s*0*(\d{1,10})\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, t, re.I)
        if not m:
            continue

        serie = normalize_serie(m.group(1))
        numero = m.group(2).lstrip("0") or "0"

        if es_serie_guia_valida(serie):
            return serie, numero

    return None, None


def extract_guia(text: str, filename: str = "") -> dict:
    t = norm(text)

    serie, numero = extract_guia_fields(t)

    f = extract_factura_from_filename(filename)
    ruc_val = f.get("ruc")

    if not ruc_val:
        ruc = re.search(r"\b(10|20)\d{9}\b", t)
        ruc_val = ruc.group(0) if ruc else None

    return {
        "serie": serie,
        "numero": numero,
        "ruc": ruc_val,
        "clave": f"GUIA|{ruc_val or 'SINRUC'}|{serie}|{numero}" if serie and numero else None,
    }


def extract_oc(text: str, cliente: str = "BBTEC") -> dict:
    numero = extract_oc_from_text(text)
    return {
        "numero": numero,
        "clave": f"OC|{numero}" if numero else None,
    }


def extract_os(text: str, cliente: str = "BBTEC") -> dict:
    numero = extract_os_from_text(text)
    return {
        "numero": numero,
        "clave": f"OS|{numero}" if numero else None,
    }


def extract_ni(text: str) -> dict:
    t = norm(text)

    patterns = [
        r"NOTA\s+DE\s+INGRESO\D{0,25}(\d{3,10})",
        r"\bNI\s*[:\-]\s*(\d{3,10})\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, t, re.I)
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

    patterns = [
        r"NUMERO\s+DE\s+OPERACION\s*:?\s*([0-9,\-\s]{3,30})",
        r"N[°º]\s*DE\s*OPERACION\s*:?\s*([0-9,\-\s]{3,30})",
        r"CODIGO\s+DE\s+SOLICITUD\s*:?\s*(\d{5,30})",
        r"CODIGO\s+OPERACION\s*:?\s*(\d{3,30})",
        r"NUMERO\s+DE\s+CONSTANCIA\s*:?\s*(\d{5,30})",
    ]

    for pattern in patterns:
        m = re.search(pattern, t, re.I)
        if m:
            return re.sub(r"\s+", "", m.group(1).replace(",", ""))

    return None


def extract_pago_transferencia(text: str) -> dict:
    banco = detect_banco(text)
    codigo = extract_codigo_operacion(text, banco)

    return {
        "banco": banco,
        "codigo_operacion": codigo,
        "clave": f"PAGO_TRANSFERENCIA|{banco}|{codigo}" if banco and codigo else None,
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

    comp = re.search(
        r"NUMERO\s+DE\s+COMPROBANTE\s*:?\s*([A-Z0-9]{3,6})\s*[- ]?\s*0*(\d{1,10})",
        t,
        re.I,
    )

    if comp:
        serie = normalize_serie(comp.group(1))
        numero = comp.group(2).lstrip("0") or "0"

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


def enrich_page(text: str, archivo_fuente: str = "", cliente: str = "BBTEC", pagina: int | None = None) -> dict:
    tipo = detect_tipo(text, archivo_fuente, cliente)

    oc_num = extract_oc_from_text(text)
    os_num = extract_os_from_text(text)

    # Evitar que una factura/guía que menciona OC se convierta en OC
    es_factura = is_factura_text(text, archivo_fuente)
    es_guia = is_guia_text(text, archivo_fuente)
    es_ni = is_nota_ingreso_text(text)
    es_pago_transf = is_pago_transferencia_text(text)
    es_pago_det = is_pago_detraccion_text(text)

    # Regla nueva: si no es documento principal y tiene OC/OS, clasificarlo como OC/OS
    if (
        oc_num
        and not es_factura
        and not es_guia
        and not es_ni
        and not es_pago_transf
        and not es_pago_det
    ):
        tipo = "orden_compra"

    elif (
        os_num
        and not es_factura
        and not es_guia
        and not es_ni
        and not es_pago_transf
        and not es_pago_det
    ):
        tipo = "orden_servicio"

    data = {
        "tipo": tipo,
        "serie": None,
        "numero": None,
        "ruc": None,
        "razon_social_emisor": None,
        "orden_servicio": os_num,
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
            "razon_social_emisor": f.get("razon_social_emisor"),
            "clave_documental": f["clave"],
        })

    elif tipo == "guia_remision":
        sunat_guia = parse_sunat_guia_from_text(text)

        if sunat_guia:
            data.update({
                "serie": sunat_guia["serie"],
                "numero": sunat_guia["numero"],
                "ruc": sunat_guia["ruc_emisor"],
                "clave_documental": sunat_guia["clave_documental"],
            })
        else:
            g = extract_guia(text, archivo_fuente)
            data.update({
                "serie": g["serie"],
                "numero": g["numero"],
                "ruc": g["ruc"],
                "clave_documental": g["clave"],
            })

    elif tipo == "orden_compra":
        numero = oc_num

        if not numero:
            oc = extract_oc(text, cliente)
            numero = oc["numero"]

        data.update({
            "orden_compra": numero,
            "numero": numero,
            "clave_documental": f"OC|{numero}" if numero else None,
        })

    elif tipo == "orden_servicio":
        numero = os_num

        if not numero:
            os_data = extract_os(text, cliente)
            numero = os_data["numero"]

        data.update({
            "orden_servicio": numero,
            "numero": numero,
            "clave_documental": f"OS|{numero}" if numero else None,
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
    
    if not data["clave_documental"]:
        asiento = None

        m = re.search(r"(04-\d{4})", archivo_fuente or "")
        if m:
            asiento = m.group(1)

        data["clave_documental"] = f"OTRO|{asiento or 'SIN_ASIENTO'}|P{pagina or 0:03d}"

    return data



def is_documento_extranjero_o_proforma(text: str) -> bool:
    t = norm(text)

    return bool(
        "PROFORMA" in t
        or "PROFORMA INVOICE" in t
        or "QUOTATION" in t
        or "COMMERCIAL INVOICE" in t
        or "PAYMENT TERM" in t
        or "BANK DETAILS" in t
        or "SHENZHEN" in t
        or "INDUSTRIAL AND COMMERCIAL BANK OF CHINA" in t
    )


def is_documento_extranjero_o_proforma(text: str) -> bool:
    t = norm(text)

    return bool(
        "PROFORMA" in t
        or "PROFORMA INVOICE" in t
        or "QUOTATION" in t
        or "COMMERCIAL INVOICE" in t
        or "PAYMENT TERM" in t
        or "BANK DETAILS" in t
        or "SHENZHEN" in t
    )


def is_guia_visual_text(text: str) -> bool:
    t = norm(text)
    c = compact_text(t)

    señales = [
        "DATOS DEL TRASLADO",
        "DATOS DEL TRANSPORTE",
        "DATOS DEL TRANSPORTISTA",
        "BIENES POR TRANSPORTAR",
        "BIENES TRASLADADOS",
        "MOTIVO DEL TRASLADO",
        "PUNTO DE PARTIDA",
        "PUNTO DE LLEGADA",
        "GUIA REMITENTE ELECTRONICA",
        "GUÍA REMITENTE ELECTRÓNICA",
        "GUIA DE REMISION",
        "GUÍA DE REMISIÓN",
        "REPRESENTACION IMPRESA DE LA GUIA",
        "REPRESENTACIÓN IMPRESA DE LA GUÍA",
    ]

    score = sum(1 for s in señales if s in t or compact_text(s) in c)

    return score >= 2


def normalize_text(text: str) -> str:
    text = text or ""

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    text = text.upper()

    text = re.sub(r"\s+", " ", text)

    text = text.replace("0RDEN", "ORDEN")
    text = text.replace("C0MPRA", "COMPRA")
    text = text.replace("SERVICI0", "SERVICIO")

    return text.strip()


