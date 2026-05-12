from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np
from pdf2image import convert_from_path

from core.config import POPPLER_PATH


def _decode_opencv(img: np.ndarray) -> list[str]:
    results = []

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


def _rotate(img: np.ndarray, angle: int) -> np.ndarray:
    if angle == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def _sharpen(gray: np.ndarray) -> np.ndarray:
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    return cv2.filter2D(gray, -1, kernel)


def _variants(img: np.ndarray) -> list[tuple[str, np.ndarray]]:
    variants = []

    gray = img if len(img.shape) == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    variants.append(("gray", gray))

    for scale in (2, 3, 4):
        up = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        variants.append((f"resize_x{scale}", up))

        _, th = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append((f"resize_x{scale}_otsu", th))

        ad = cv2.adaptiveThreshold(
            up,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            5,
        )
        variants.append((f"resize_x{scale}_adaptive", ad))

        sharp = _sharpen(up)
        variants.append((f"resize_x{scale}_sharpen", sharp))

    return variants


def _zones(img: np.ndarray) -> list[tuple[str, np.ndarray]]:
    h, w = img.shape[:2]

    coords = [
        ("full", 0, 0, w, h),
        ("bottom_right", int(w * 0.45), int(h * 0.45), w, h),
        ("bottom_left", 0, int(h * 0.45), int(w * 0.60), h),
        ("bottom", 0, int(h * 0.50), w, h),
        ("right", int(w * 0.50), 0, w, h),
        ("top_right", int(w * 0.45), 0, w, int(h * 0.55)),
        ("center", int(w * 0.20), int(h * 0.20), int(w * 0.80), int(h * 0.80)),
    ]

    output = []

    for name, x1, y1, x2, y2 in coords:
        crop = img[y1:y2, x1:x2]
        if crop.size:
            output.append((name, crop))

    return output


def decode_qr_from_pdf(
    pdf_path: str | Path,
    max_pages: int = 1,
    dpi: int = 420,
    debug_dir: str | Path | None = None,
) -> list[str]:
    path = Path(pdf_path)

    if not path.exists() or path.suffix.lower() != ".pdf":
        return []

    debug_base = Path(debug_dir) if debug_dir else None
    if debug_base:
        debug_base.mkdir(parents=True, exist_ok=True)

    results = []

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

    for page_index, page in enumerate(pages, start=1):
        img_rgb = np.array(page)
        img = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

        for zone_name, zone in _zones(img):
            for angle in (0, 90, 180, 270):
                rotated = _rotate(zone, angle)

                for variant_name, variant in _variants(rotated):
                    decoded = _decode_opencv(variant)

                    if debug_base and not decoded:
                        debug_file = debug_base / f"{path.stem}_p{page_index}_{zone_name}_{angle}_{variant_name}.png"
                        try:
                            cv2.imwrite(str(debug_file), variant)
                        except Exception:
                            pass

                    for item in decoded:
                        if item not in results:
                            results.append(item)

    return results