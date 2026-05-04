from pathlib import Path

# Ejemplo de inicialización
INPUT_DIR = Path(r"C:\D\Proyectos\GestionDocumental\Gestion_Documental_Emisores\data\entrada")
input_dir = INPUT_DIR  # aquí defines la variable

# Validación
print(f"INPUT_DIR: {INPUT_DIR}")
print(f"Ruta final: {input_dir}")
print(f"Existe: {input_dir.exists()}")
