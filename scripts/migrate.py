"""Explicit migration entrypoint. Never defaults to or discovers production credentials."""
import argparse
import os
from pathlib import Path
import psycopg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bootstrap', action='store_true', help='Only for a brand new empty database')
    args = parser.parse_args()
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise SystemExit('Set DATABASE_URL explicitly before running migrations')
    if args.bootstrap:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import app
        with psycopg.connect(url) as conn:
            if conn.execute("SELECT to_regclass('public.parents')").fetchone()[0]:
                raise SystemExit('--bootstrap is only allowed for an empty database')
        app.init_db()
    with psycopg.connect(url) as conn:
        conn.execute((Path(__file__).resolve().parents[1]/'migrations'/'001_mobile.sql').read_text(encoding='utf-8'))
    print('Applied 001_mobile')


if __name__ == '__main__':
    main()
