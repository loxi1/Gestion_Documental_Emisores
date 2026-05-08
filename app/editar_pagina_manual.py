import argparse

from core.db import get_cursor


def build_clave(tipo, ruc=None, serie=None, numero=None, oc=None, os=None):
    if tipo == "factura":
        if serie and numero and ruc:
            return f"FACTURA|{ruc}|{serie}|{numero}"

    if tipo == "guia_remision":
        if serie and numero:
            return f"GUIA|{ruc or 'SINRUC'}|{serie}|{numero}"

    if tipo == "orden_compra":
        if oc:
            return f"OC|{str(oc).zfill(6)}"

    if tipo == "orden_servicio":
        if os:
            return f"OS|{str(os).zfill(6)}"

    if tipo == "nota_ingreso":
        if numero:
            return f"NI|{str(numero).zfill(6)}"

    return None


def preguntar(label, actual=None):
    valor = input(f"{label} [{actual or ''}]: ").strip()
    return valor if valor else actual


def editar(id_pagina: int):
    with get_cursor() as (_, cur):
        cur.execute("""
            SELECT *
            FROM documentos_paginas
            WHERE id = %s
        """, (id_pagina,))
        row = cur.fetchone()

    if not row:
        print("No existe ese ID.")
        return

    print("\nDocumento encontrado:")
    print(f"ID: {row['id']}")
    print(f"Archivo: {row['archivo_fuente']}")
    print(f"Página: {row['pagina']}")
    print(f"Tipo actual: {row['tipo_detectado']}")
    print(f"Clave actual: {row['clave_documental']}")
    print(f"Ruta página: {row.get('ruta_pagina_pdf')}")
    print()

    tipo = preguntar("Tipo", row["tipo_detectado"])

    serie = row["serie"]
    numero = row["numero"]
    ruc = row["ruc_emisor"]
    razon = row["razon_social_emisor"]
    oc = row["orden_compra"]
    os = row["orden_servicio"]

    if tipo in ("factura", "guia_remision"):
        serie = preguntar("Serie", serie)
        numero = preguntar("Número", numero)
        ruc = preguntar("RUC emisor", ruc)

        if tipo == "factura":
            razon = preguntar("Razón social emisor", razon)

    elif tipo == "orden_compra":
        oc = preguntar("Número OC", oc)

    elif tipo == "orden_servicio":
        os = preguntar("Número OS", os)

    elif tipo == "nota_ingreso":
        numero = preguntar("Número Nota Ingreso", numero)

    clave = build_clave(
        tipo=tipo,
        ruc=ruc,
        serie=serie,
        numero=numero,
        oc=oc,
        os=os,
    )

    print(f"\nNueva clave: {clave}")
    confirmar = input("¿Guardar cambios? (s/n): ").strip().lower()

    if confirmar != "s":
        print("Cancelado.")
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
            oc,
            os,
            clave,
            id_pagina,
        ))

    print("Actualizado correctamente.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    args = parser.parse_args()

    editar(args.id)