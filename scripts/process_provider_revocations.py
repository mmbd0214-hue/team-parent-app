"""Run periodically only after explicitly configuring Apple provider credentials."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg.rows import dict_row
from apple_identity import drain_revocations

if __name__ == '__main__':
    if not os.getenv('DATABASE_URL'):
        raise SystemExit('Set DATABASE_URL explicitly')
    count = drain_revocations(lambda: psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row))
    print('Processed revocation jobs:', count)
