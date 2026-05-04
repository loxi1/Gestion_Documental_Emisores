from __future__ import annotations

from core.db import get_cursor


def find_cliente_by_ruc(ruc: str | None) -> dict | None:
    if not ruc:
        return None
    with get_cursor() as (_, cur):
        cur.execute("SELECT * FROM clientes_destino WHERE ruc = %s AND estado = TRUE LIMIT 1", (ruc,))
        return cur.fetchone()


def find_cliente_by_text(text: str | None) -> dict | None:
    if not text:
        return None
    text_u = text.upper().replace(".", "")
    with get_cursor() as (_, cur):
        cur.execute("SELECT * FROM clientes_destino WHERE estado = TRUE ORDER BY id")
        rows = cur.fetchall()
    for row in rows:
        if row["ruc"] and row["ruc"] in text_u:
            return row
        if row["nombre_oficial"] and row["nombre_oficial"].upper().replace(".", "") in text_u:
            return row
        if row["abreviatura"] and row["abreviatura"].upper() in text_u:
            return row
    return None


def get_or_create_proveedor(ruc: str | None, razon_social: str | None) -> dict | None:
    if not ruc:
        return None
    with get_cursor(commit=True) as (_, cur):
        cur.execute("SELECT * FROM proveedores WHERE ruc = %s LIMIT 1", (ruc,))
        row = cur.fetchone()
        if row:
            return row
        cur.execute(
            "INSERT INTO proveedores (ruc, razon_social) VALUES (%s, %s) RETURNING *",
            (ruc, razon_social),
        )
        return cur.fetchone()
