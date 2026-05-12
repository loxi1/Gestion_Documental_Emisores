from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from pdf2image import convert_from_path

from core.config import POPPLER_PATH
from core.image_utils import build_variants, iter_zones, rotate_image


def decode_qr_from_image(img: np.ndarray) -> list[str]:
    results: list[str] = []

    if img is None or img.size == 0:
        return results

    detector = cv2.QRCodeDetector()

    try:
        data, _, _ = detector.detectAndDecode(img)
        if data and data.strip():
            results.append(data.strip())
    except Exception:
        pass

    try:
        ok, decoded_info, _, _ = detector.detectAndDecodeMulti(img)
        if ok and decoded_info:
            for item in decoded_info:
                item = (item or "").strip()
                if item and item not in results:
                    results.append(item)
    except Exception:
        pass

    return results


def decode_qr_from_pdf_pro(
    pdf_path: str | Path,
    max_pages: int = 1,
    dpi: int = 420,
    debug_dir: str | Path | None = None,
) -> list[str]:
    path = Path(pdf_path)

    if not path.exists() or path.suffix.lower() != ".pdf":
        return []

    debug_path = Path(debug_dir) if debug_dir else None
    if debug_path:
        debug_path.mkdir(parents=True, exist_ok=True)

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

    results: list[str] = []

    for page_index, page in enumerate(pages, start=1):
        img_rgb = np.array(page)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

        for zone_name, zone in iter_zones(img_bgr):
            for angle in (0, 90, 180, 270):
                rotated = rotate_image(zone, angle)

                for variant_name, variant in build_variants(rotated):
                    decoded = decode_qr_from_image(variant)

                    if debug_path and not decoded:
                        filename = (
                            f"{path.stem}_p{page_index}_"
                            f"{zone_name}_{angle}_{variant_name}.png"
                        )
                        cv2.imwrite(str(debug_path / filename), variant)

                    for item in decoded:
                        if item not in results:
                            results.append(item)

    return results