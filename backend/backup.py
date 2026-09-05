"""Write a consistent SQLite backup to stdout; private encryption key is separate.

    docker compose ... exec -T paperweek python -m backend.backup > backup.private.sqlite3
"""
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile


def main():
    source = Path(os.environ.get('PAPERWEEK_DATA_DIR', '/data')) / 'paperweek.sqlite3'
    if not source.is_file():
        raise SystemExit('Database does not exist.')
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / 'backup.sqlite3'
        with sqlite3.connect(f'file:{source}?mode=ro', uri=True) as original, sqlite3.connect(dest) as backup:
            original.backup(backup)
        with dest.open('rb') as stream:
            shutil.copyfileobj(stream, sys.stdout.buffer)


if __name__ == '__main__':
    main()
