from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from core.text_utils import normalize_token


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_final_name(
    prefijo_nombre: str,
    tipo_documental: str,
    serie: str | None,
    numero: str | None,
    ruc_emisor: str | None,
    razon_social_emisor: str | None,
    fallback_name: str,
) -> str:
    ext = Path(fallback_name).suffix.lower() or ".pdf"
    tipo_map = {
        "factura": "FACTURA",
        "guia_remision": "GUIA_REMISION",
        "orden_compra": "ORDEN_COMPRA",
        "nota_ingreso": "NI",
        "pago": "PAGO",
        "otro": "OTRO",
    }
    parts = [normalize_token(prefijo_nombre), tipo_map.get(tipo_documental, "OTRO")]
    if serie:
        parts.append(normalize_token(serie))
    if numero:
        parts.append(normalize_token(numero))
    if ruc_emisor:
        parts.append(normalize_token(ruc_emisor))
    parts.append(normalize_token(razon_social_emisor) if razon_social_emisor else "SIN_RAZON_SOCIAL")
    return " ".join([p for p in parts if p]) + ext


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source), str(destination))
