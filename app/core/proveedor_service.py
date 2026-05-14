import os
import requests
from dotenv import load_dotenv

from core.db import get_cursor

load_dotenv()

APISPERU_TOKEN = os.getenv("APISPERU_TOKEN")


def get_proveedor_by_ruc(ruc: str) -> dict | None:
    if not ruc:
        return None

    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT ruc, razon_social, direccion
            FROM proveedores
            WHERE ruc = %s
            LIMIT 1
        """, (ruc,))
        row = cur.fetchone()

    if not row:
        return None

    return {
        "ruc": row["ruc"],
        "nombre": row["razon_social"],
        "direccion": row["direccion"],
    }


def fetch_proveedor_from_api(ruc: str) -> dict | None:
    if not ruc or not APISPERU_TOKEN:
        return None

    url = f"https://dniruc.apisperu.com/api/v1/ruc/{ruc}?token={APISPERU_TOKEN}"

    try:
        resp = requests.get(url, timeout=15)

        if resp.status_code != 200:
            return None

        data = resp.json()

        nombre = data.get("razonSocial")

        if not nombre:
            return None

        return {
            "ruc": data.get("ruc") or ruc,
            "nombre": nombre,
            "direccion": data.get("direccion"),
        }

    except Exception as exc:
        print(f"[API RUC ERROR] ruc={ruc} error={exc}")
        return None


def upsert_proveedor(proveedor: dict) -> dict | None:
    if not proveedor or not proveedor.get("ruc"):
        return None

    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            INSERT INTO proveedores (
                ruc,
                razon_social,
                direccion
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (ruc)
            DO UPDATE SET
                razon_social = EXCLUDED.razon_social,
                direccion = COALESCE(EXCLUDED.direccion, proveedores.direccion),
                actualizado_en = NOW()
            RETURNING ruc, razon_social, direccion
        """, (
            proveedor["ruc"],
            proveedor.get("nombre"),
            proveedor.get("direccion"),
        ))

        row = cur.fetchone()

    return {
        "ruc": row["ruc"],
        "nombre": row["razon_social"],
        "direccion": row["direccion"],
    }


def get_or_fetch_proveedor(ruc: str) -> dict | None:
    proveedor = get_proveedor_by_ruc(ruc)

    if proveedor:
        return proveedor

    proveedor_api = fetch_proveedor_from_api(ruc)

    if not proveedor_api:
        return None

    return upsert_proveedor(proveedor_api)