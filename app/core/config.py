from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "gestiondocumental_mvp")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

STORAGE_DIR = (ROOT_DIR / os.getenv("STORAGE_DIR", "./storage")).resolve()
INPUT_DIR = (ROOT_DIR / os.getenv("INPUT_DIR", "./storage/input")).resolve()
OUTPUT_DIR = (ROOT_DIR / os.getenv("OUTPUT_DIR", "./storage/output")).resolve()
OCR_TMP_DIR = (ROOT_DIR / os.getenv("OCR_TMP_DIR", "./storage/tmp/ocr")).resolve()

POPPLER_PATH = os.getenv("POPPLER_PATH") or None
USE_OCR = os.getenv("USE_OCR", "0") == "1"
STRICT_FACTURA_CLIENTE = os.getenv("STRICT_FACTURA_CLIENTE", "1") == "1"
