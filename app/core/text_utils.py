from __future__ import annotations

import re
import unicodedata


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("\u00ba", "°").replace("\u00b0", "°")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip().upper()


def compact_text(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalize_text(value))


def sanitize_filename(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r'[<>:"/\\|?*]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_token(value: str | None) -> str:
    if not value:
        return ""
    value = sanitize_filename(str(value))
    value = value.replace(".", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value.replace(" ", "_")
