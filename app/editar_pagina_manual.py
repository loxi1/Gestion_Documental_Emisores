import argparse

from core.db import get_cursor
from core.proveedor_service import get_or_fetch_proveedor


TIPOS_VALIDOS = {
    "factura",
    "guia_remision",
    "orden_compra",
    "orden_servicio",
    "nota_ingreso",
    "pago_transferencia",
    "pago_detraccion",
    "otro",
}


def input_default(label: str, default=None) -> str | None:
    texto = input(f"{label} [{default or ''}]: ").strip()
    return texto if texto else default


def build_clave(tipo, ruc=None, serie=None, numero=None, banco=None, codigo=None):
    tipo = tipo.lower()

    if tipo == "factura":
        return f"FACTURA|{ruc}|{serie}|{numero}"

    if tipo == "guia_remision":
        return f"GUIA|{ruc}|{serie}|{numero}"

    if tipo == "orden_compra":
        return f"OC|{numero}"

    if tipo == "orden_servicio":
        return f"OS|{numero}"

    if tipo == "nota_ingreso":
        return f"NI|{numero}"

    if tipo == "pago_transferencia":
        return f"PAGO_TRANSFERENCIA|{banco or 'SIN_BANCO'}|{codigo or 'SIN_CODIGO'}"

    if tipo == "pago_detraccion":
        if ruc and serie and numero:
            return f"PAGO_DETRACCION|{ruc}|{serie}|{numero}"
        return f"PAGO_DETRACCION|{banco or 'BN'}|{codigo or 'SIN_CODIGO'}"

    if tipo == "otro":
        return f"OTRO|{codigo or 'SIN_CODIGO'}"

    raise ValueError(f"Tipo no soportado: {tipo}")


def leer_pagina(page_id: int):
    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT *
            FROM documentos_paginas
            WHERE id = %s
        """, (page_id,))
        return cur.fetchone()


def resolver_proveedor(ruc: str | None, razon_actual: str | None) -> str | None:
    if not ruc:
        return razon_actual

    if razon_actual and razon_actual.strip():
        return razon_actual.strip()

    proveedor = get_or_fetch_proveedor(ruc)

    if proveedor and proveedor.get("nombre"):
        print(f"[PROVEEDOR] {ruc} -> {proveedor['nombre']}")
        return proveedor["nombre"]

    print(f"[PROVEEDOR] No encontrado para RUC {ruc}")
    return razon_actual


def editar_interactivo(page_id: int):
    row = leer_pagina(page_id)

    if not row:
        print(f"[NO ENCONTRADO] Página ID {page_id}")
        return

    print("=" * 100)
    print(f"ID              : {row['id']}")
    print(f"Asiento         : {row['asiento_contable']}")
    print(f"Archivo fuente  : {row['archivo_fuente']}")
    print(f"Página          : {row['pagina']}")
    print(f"Tipo actual     : {row['tipo_detectado']}")
    print(f"Serie actual    : {row['serie']}")
    print(f"Número actual   : {row['numero']}")
    print(f"RUC actual      : {row['ruc_emisor']}")
    print(f"Razón actual    : {row['razon_social_emisor']}")
    print(f"Clave actual    : {row['clave_documental']}")
    print("=" * 100)

    tipo = input_default("Tipo", row["tipo_detectado"] or "factura")
    tipo = tipo.lower()

    if tipo not in TIPOS_VALIDOS:
        print(f"[ERROR] Tipo inválido: {tipo}")
        print(f"Tipos válidos: {', '.join(sorted(TIPOS_VALIDOS))}")
        return

    serie = row["serie"]
    numero = row["numero"]
    ruc = row["ruc_emisor"]
    razon = row["razon_social_emisor"]
    orden_compra = row["orden_compra"]
    orden_servicio = row["orden_servicio"]
    banco = row["banco_abreviatura"]
    codigo = row["codigo_operacion"]

    if tipo in ("factura", "guia_remision"):
        serie = input_default("Serie", serie)
        numero = input_default("Número", numero)
        ruc = input_default("RUC emisor", ruc)

        razon_default = resolver_proveedor(ruc, razon)
        razon = input_default("Razón social emisor", razon_default)

    elif tipo == "orden_compra":
        numero = input_default("Número OC", orden_compra or numero)
        orden_compra = numero
        serie = None
        ruc = None
        razon = None

    elif tipo == "orden_servicio":
        numero = input_default("Número OS", orden_servicio or numero)
        orden_servicio = numero
        serie = None
        ruc = None
        razon = None

    elif tipo == "nota_ingreso":
        numero = input_default("Número NI", numero)
        serie = None
        ruc = None
        razon = None

    elif tipo == "pago_transferencia":
        banco = input_default("Banco", banco or "SIN_BANCO")
        codigo = input_default("Código operación", codigo or "SIN_CODIGO")
        serie = None
        numero = None
        ruc = None
        razon = None

    elif tipo == "pago_detraccion":
        usar_factura = input_default("¿Asociar a factura? s/n", "s")

        if usar_factura.lower() == "s":
            serie = input_default("Serie factura", serie)
            numero = input_default("Número factura", numero)
            ruc = input_default("RUC emisor", ruc)

            razon_default = resolver_proveedor(ruc, razon)
            razon = input_default("Razón social emisor", razon_default)

            banco = "BN"
            codigo = None
        else:
            banco = input_default("Banco", banco or "BN")
            codigo = input_default("Código operación", codigo or "SIN_CODIGO")
            serie = None
            numero = None
            ruc = None
            razon = None

    elif tipo == "otro":
        codigo = input_default("Código/referencia", codigo or f"ID{page_id}")
        serie = None
        numero = None
        ruc = None
        razon = None

    clave = build_clave(
        tipo=tipo,
        ruc=ruc,
        serie=serie,
        numero=numero,
        banco=banco,
        codigo=codigo,
    )

    print("\nResumen:")
    print(f"Tipo  : {tipo}")
    print(f"Serie : {serie}")
    print(f"Número: {numero}")
    print(f"RUC   : {ruc}")
    print(f"Razón : {razon}")
    print(f"Banco : {banco}")
    print(f"Código: {codigo}")
    print(f"Clave : {clave}")

    confirmar = input("\n¿Guardar cambios? s/n [s]: ").strip().lower() or "s"

    if confirmar != "s":
        print("[CANCELADO]")
        return

    with get_cursor(commit=True) as (_, cur):
        cur.execute("""
            UPDATE documentos_paginas
            SET tipo_detectado = %s,
                serie = %s,
                numero = %s,
                ruc_emisor = %s,
                razon_social_emisor = %s,
                orden_compra = %s,
                orden_servicio = %s,
                banco_abreviatura = %s,
                codigo_operacion = %s,
                clave_documental = %s,
                requiere_qr = FALSE,
                qr_procesado = TRUE,
                qr_error = NULL,
                estado = 'clasificado'
            WHERE id = %s
        """, (
            tipo,
            serie,
            numero,
            ruc,
            razon,
            orden_compra,
            orden_servicio,
            banco,
            codigo,
            clave,
            page_id,
        ))

    print("\n[OK] Página actualizada correctamente.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)

    args = parser.parse_args()

    editar_interactivo(args.id)