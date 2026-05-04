from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np
from pdf2image import convert_from_path

from core.config import POPPLER_PATH


def _decode_qr_from_ndarray(img: np.ndarray) -> list[str]:
    results: list[str] = []
    if img is None or not isinstance(img, np.ndarray) or img.size == 0:
        return results
    try:
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if data and data.strip():
            results.append(data.strip())
        try:
            ok, decoded_info, _, _ = detector.detectAndDecodeMulti(img)
            if ok and decoded_info:
                for item in decoded_info:
                    item = item.strip() if item else ""
                    if item and item not in results:
                        results.append(item)
        except Exception:
            pass
    except Exception:
        return results
    return results


def _prepare_variants(img: np.ndarray) -> list[np.ndarray]:
    if img is None or img.size == 0:
        return []
    gray = img if len(img.shape) == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    variants = [gray]
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(th)
    up = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    variants.append(up)
    _, up_th = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(up_th)
    return variants


def _iter_qr_zones(img_bgr: np.ndarray) -> list[np.ndarray]:
    h, w = img_bgr.shape[:2]
    coords = [
        (0, 0, w, h),
        (0, int(h * 0.55), int(w * 0.55), h),
        (int(w * 0.45), int(h * 0.55), w, h),
        (int(w * 0.55), 0, w, h),
        (0, 0, int(w * 0.45), h),
        (0, int(h * 0.50), w, h),
        (int(w * 0.55), 0, w, int(h * 0.45)),
        (0, 0, int(w * 0.55), int(h * 0.45)),
    ]
    zones: list[np.ndarray] = []
    for x1, y1, x2, y2 in coords:
        crop = img_bgr[y1:y2, x1:x2]
        if crop.size > 0:
            zones.append(crop)
    return zones


def decode_qr_from_pdf(pdf_path: str | Path, max_pages: int = 1, dpi: int = 280) -> list[str]:
    path = Path(pdf_path)
    if not path.exists() or path.suffix.lower() != ".pdf":
        return []
    results: list[str] = []
    try:
        pages = convert_from_path(
            str(path),
            dpi=dpi,
            first_page=1,
            last_page=max_pages,
            poppler_path=POPPLER_PATH,
        )
    except Exception:
        return []
    for page in pages:
        try:
            img_rgb = np.array(page)
            img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
            for zone in _iter_qr_zones(img_bgr):
                for variant in _prepare_variants(zone):
                    for item in _decode_qr_from_ndarray(variant):
                        if item not in results:
                            results.append(item)
        except Exception:
            continue
    return results
