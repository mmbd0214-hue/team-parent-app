"""Export the API contract without running startup or connecting to a database."""
import json
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
# app.py requires a URL at import; this export never runs startup or DB calls.
os.environ.setdefault('DATABASE_URL', 'postgresql://invalid/contract_export_only')
from app import app

if __name__ == '__main__':
    output = root / 'mobile' / 'api' / 'openapi.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Exported {output}')
