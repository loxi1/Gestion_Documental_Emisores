import os
import shutil
from pathlib import Path

BASE_SOURCE = Path("/y/PROCESAR/6 PERIODO 2026")
BASE_TARGET = Path("data")

EMPRESAS_MAP = {
    "BB TECNOLOGIA": "BBTEC",
    "CIMA ENERGY": "CIMA",
    "HUANCAVELICA": "HUANCA",
    "ILUMINACION": "TARMA",
    "KIMBIRI": "KIMBIRI",
}

MESES_MAP = {
    "ENERO": "01",
    "FEBRERO": "02",
    "MARZO": "03",
    "ABRIL": "04",
    "MAYO": "05",
    "JUNIO": "06",
    "JULIO": "07",
    "AGOSTO": "08",
    "SEPTIEMBRE": "09",
    "OCTUBRE": "10",
    "NOVIEMBRE": "11",
    "DICIEMBRE": "12",
}


def detectar_mes(nombre_carpeta):
    for mes, num in MESES_MAP.items():
        if mes in nombre_carpeta.upper():
            return num
    return None


def copiar_estructura():
    for empresa_dir in BASE_SOURCE.iterdir():
        if not empresa_dir.is_dir():
            continue

        empresa_nombre = empresa_dir.name.strip()
        empresa_abrev = EMPRESAS_MAP.get(empresa_nombre)

        if not empresa_abrev:
            print(f"[WARN] Empresa no mapeada: {empresa_nombre}")
            continue

        for mes_dir in empresa_dir.iterdir():
            if not mes_dir.is_dir():
                continue

            mes_num = detectar_mes(mes_dir.name)

            if not mes_num:
                print(f"[WARN] Mes no detectado: {mes_dir.name}")
                continue

            destino = BASE_TARGET / "2026" / empresa_abrev / mes_num
            destino.mkdir(parents=True, exist_ok=True)

            for pdf in mes_dir.glob("*.pdf"):
                destino_file = destino / pdf.name

                if not destino_file.exists():
                    shutil.copy2(pdf, destino_file)
                    print(f"[OK] {pdf.name} -> {destino}")


if __name__ == "__main__":
    copiar_estructura()