# Gestion_Documental_Emisores
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
psql -U postgres -d gestion_documental -f sql/001_init.sql

python src/process_batch.py

copiar a carpeta de trabajo
python app/copiar_trabajo.py --year 2026 --cliente BBTEC --month 1

procesar orden de compra
python app/procesar_oc.py --year 2026 --cliente BBTEC --month 1