from __future__ import annotations

import cv2
import numpy as np


def to_gray(img: np.ndarray) -> np.ndarray:
    if img is None or img.size == 0:
        return img

    if len(img.shape) == 2:
        return img

    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def resize_image(img: np.ndarray, scale: int = 2) -> np.ndarray:
    return cv2.resize(
        img,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_CUBIC,
    )


def threshold_otsu(img: np.ndarray) -> np.ndarray:
    gray = to_gray(img)
    _, th = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    return th


def adaptive_threshold(img: np.ndarray) -> np.ndarray:
    gray = to_gray(img)
    return cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        5,
    )


def sharpen(img: np.ndarray) -> np.ndarray:
    gray = to_gray(img)
    kernel = np.array([
        [0, -1, 0],
        [-1, 5, -1],
        [0, -1, 0],
    ])
    return cv2.filter2D(gray, -1, kernel)


def rotate_image(img: np.ndarray, angle: int) -> np.ndarray:
    if angle == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

    if angle == 180:
        return cv2.rotate(img, cv2.ROTATE_180)

    if angle == 270:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

    return img


def iter_zones(img: np.ndarray):
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

    for name, x1, y1, x2, y2 in coords:
        crop = img[y1:y2, x1:x2]
        if crop is not None and crop.size > 0:
            yield name, crop


def build_variants(img: np.ndarray):
    gray = to_gray(img)

    yield "gray", gray
    yield "otsu", threshold_otsu(gray)
    yield "adaptive", adaptive_threshold(gray)
    yield "sharpen", sharpen(gray)

    for scale in (2, 3, 4):
        up = resize_image(gray, scale)
        yield f"resize_x{scale}", up
        yield f"resize_x{scale}_otsu", threshold_otsu(up)
        yield f"resize_x{scale}_adaptive", adaptive_threshold(up)
        yield f"resize_x{scale}_sharpen", sharpen(up)