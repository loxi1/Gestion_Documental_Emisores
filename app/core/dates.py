from __future__ import annotations

import re
from datetime import date

MESES = {
    "ENE": "01", "FEB": "02", "MAR": "03", "ABR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AGO": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DIC": "12",
    "ENERO": "01", "FEBRERO": "02", "MARZO": "03", "ABRIL": "04",
    "MAYO": "05", "JUNIO": "06", "JULIO": "07", "AGOSTO": "08",
    "SEPTIEMBRE": "09", "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12",
}


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip().upper()
    raw = raw.replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U")

    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", raw)
    if m:
        d, mth, y = m.groups()
        return f"{y}-{mth}-{d}"

    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if m:
        return raw

    m = re.match(r"^(\d{1,2})/([A-Z]{3})\.?/(\d{4})$", raw)
    if m:
        d, mon, y = m.groups()
        mon_num = MESES.get(mon[:3])
        if mon_num:
            return f"{y}-{mon_num}-{str(d).zfill(2)}"

    m = re.match(r"^(\d{1,2})-([A-Z]{3})-(\d{4})$", raw)
    if m:
        d, mon, y = m.groups()
        mon_num = MESES.get(mon[:3])
        if mon_num:
            return f"{y}-{mon_num}-{str(d).zfill(2)}"

    m = re.search(r"(\d{1,2}) DE ([A-Z]+) DEL (\d{4})", raw)
    if m:
        d, mon, y = m.groups()
        mon_num = MESES.get(mon)
        if mon_num:
            return f"{y}-{mon_num}-{str(d).zfill(2)}"
    return None


def parse_iso_date(value: str | None) -> date | None:
    norm = normalize_date(value)
    if not norm:
        return None
    y, m, d = norm.split("-")
    return date(int(y), int(m), int(d))
