# Gestion_Documental_Emisores
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
psql -U postgres -d gestion_documental -f sql/001_init.sql

python src/process_batch.py