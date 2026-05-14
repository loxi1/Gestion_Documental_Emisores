import os
import re

from dotenv import load_dotenv

from core.db import get_cursor

try:
    import requests
except Exception:
    requests = None

load_dotenv()

APISPERU_TOKEN = os.getenv("APISPERU_TOKEN")


def normalize_text(value: str | None) -> str | None:
    if not value:
        return None

    value = re.sub(r"\s+", " ", value.strip())

    return value.upper()


def valid_ruc(ruc: str | None) -> bool:
    if not ruc:
        return False

    return bool(re.fullmatch(r"\d{11}", str(ruc)))


def get_proveedor_by_ruc(ruc: str) -> dict | None:
    if not valid_ruc(ruc):
        return None

    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT
                ruc,
                razon_social,
                direccion
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
    if not valid_ruc(ruc):
        return None

    if not APISPERU_TOKEN:
        print("[APISPERU] token no configurado")
        return None

    if not requests:
        print("[APISPERU] requests no instalado")
        return None

    url = f"https://dniruc.apisperu.com/api/v1/ruc/{ruc}"

    try:
        resp = requests.get(
            url,
            params={"token": APISPERU_TOKEN},
            timeout=15,
        )

        if resp.status_code != 200:
            print(f"[APISPERU] status={resp.status_code} ruc={ruc}")
            return None

        try:
            data = resp.json()
        except Exception:
            print(f"[APISPERU] respuesta inválida ruc={ruc}")
            return None

        nombre = normalize_text(data.get("razonSocial"))

        if not nombre:
            print(f"[APISPERU] sin razon social ruc={ruc}")
            return None

        proveedor = {
            "ruc": data.get("ruc") or ruc,
            "nombre": nombre,
            "direccion": normalize_text(data.get("direccion")),
        }

        print(f"[APISPERU] OK {ruc} -> {nombre}")

        return proveedor

    except requests.Timeout:
        print(f"[APISPERU] timeout ruc={ruc}")
        return None

    except Exception as exc:
        print(f"[APISPERU ERROR] ruc={ruc} error={exc}")
        return None


def upsert_proveedor(proveedor: dict) -> dict | None:
    if not proveedor:
        return None

    ruc = proveedor.get("ruc")

    if not valid_ruc(ruc):
        return None

    nombre = normalize_text(proveedor.get("nombre"))

    if not nombre:
        return None

    direccion = normalize_text(proveedor.get("direccion"))

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
                direccion = COALESCE(
                    EXCLUDED.direccion,
                    proveedores.direccion
                ),
                actualizado_en = NOW()
            RETURNING
                ruc,
                razon_social,
                direccion
        """, (
            ruc,
            nombre,
            direccion,
        ))

        row = cur.fetchone()

    return {
        "ruc": row["ruc"],
        "nombre": row["razon_social"],
        "direccion": row["direccion"],
    }


def get_or_fetch_proveedor(ruc: str) -> dict | None:
    if not valid_ruc(ruc):
        return None

    proveedor = get_proveedor_by_ruc(ruc)

    if proveedor:
        return proveedor

    proveedor_api = fetch_proveedor_from_api(ruc)

    if not proveedor_api:
        return None

    return upsert_proveedor(proveedor_api)