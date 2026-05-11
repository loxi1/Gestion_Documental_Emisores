from __future__ import annotations

import re
import unicodedata


def strip_accents(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFD", str(value))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def collapse_spaces(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_text(text: str) -> str:
    text = text or ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.upper()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_filename_part(value: str | None, fallback: str = "SIN_DATO") -> str:
    if not value:
        return fallback

    text = strip_accents(value)
    text = text.upper()
    text = re.sub(r"[^\w\s-]", " ", text, flags=re.UNICODE)
    text = collapse_spaces(text)
    text = text.replace(" ", "_")
    text = text.strip("_-")
    return text or fallback

def compact_text(text: str) -> str:
    text = normalize_text(text)
    return re.sub(r"[^A-Z0-9]", "", text)