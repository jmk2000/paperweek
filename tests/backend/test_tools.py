"""Configuration and backup checks in temporary folders, never the working tree."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from cryptography.fernet import Fernet
import pytest
from backend.storage import Store

ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'isolated'
    (root / 'tools').mkdir(parents=True)
    shutil.copy(ROOT / 'tools/configure_backend.py', root / 'tools/')
    shutil.copy(ROOT / '.env.example', root)
    return root


def configure(root, *args):
    return subprocess.run([sys.executable, str(root/'tools/configure_backend.py'),
        '--public-url', 'https://paperweek.example.net', *map(str,args)], capture_output=True, text=True)


def env(root):
    return dict(line.split('=',1) for line in (root/'.env.private').read_text().splitlines() if '=' in line and not line.startswith('#'))


def test_generator_creates_private_files(project):
    r = configure(project)
    assert r.returncode == 0, r.stderr
    assert 'SAVE THIS ADMINISTRATOR PASSWORD' in r.stdout
    assert '/api/oauth/callback' in r.stdout
    values = env(project)
    assert values['PAPERWEEK_ADMIN_HASH'].startswith("'scrypt:")
    Fernet(values['PAPERWEEK_TOKEN_KEY'].strip("'").encode())
    assert (project/'.env.private').stat().st_mode & 0o777 == 0o600
    assert (project/'.env').stat().st_mode & 0o777 == 0o600


def test_generator_preserves_key_and_password_on_rerun(project):
    assert configure(project).returncode == 0
    before = env(project)
    with (project/'.env').open('a') as f:
        f.write('\nNPM_NETWORK=existing-private-network\n')
    r = configure(project)
    assert r.returncode == 0
    assert env(project) == before
    assert 'SAVE THIS ADMINISTRATOR PASSWORD' not in r.stdout
    assert 'NPM_NETWORK=existing-private-network' in (project/'.env').read_text()


def test_reset_admin_preserves_encryption_key(project):
    assert configure(project).returncode == 0
    before = env(project)
    assert configure(project, '--reset-admin').returncode == 0
    after = env(project)
    assert before['PAPERWEEK_TOKEN_KEY'] == after['PAPERWEEK_TOKEN_KEY']
    assert before['PAPERWEEK_ADMIN_HASH'] != after['PAPERWEEK_ADMIN_HASH']


def test_web_client_import_and_unsafe_desktop_rejected(project, tmp_path):
    client = tmp_path/'synthetic.private.json'
    client.write_text(json.dumps({'web': {'client_id':'synthetic.apps.googleusercontent.com','client_secret':'fixture-only-not-a-real-secret'}}))
    r = configure(project, '--google-client', client)
    assert r.returncode == 0
    assert env(project)['PAPERWEEK_GOOGLE_CLIENT_ID'] == "'synthetic.apps.googleusercontent.com'"
    assert 'fixture-only-not-a-real-secret' not in r.stdout
    before = env(project)
    client.write_text(json.dumps({'installed': {'client_id':'desktop.apps.googleusercontent.com'}}))
    assert configure(project, '--google-client', client).returncode != 0
    assert before == env(project)


@pytest.mark.parametrize('url', ['http://192.168.1.2:8080','https://paperweek.example.net/subpath','https://user:password@example.net'])
def test_bad_origin_no_configuration_written(project,url):
    r = subprocess.run([sys.executable,str(project/'tools/configure_backend.py'),'--public-url',url], capture_output=True,text=True)
    assert r.returncode != 0
    assert not (project/'.env.private').exists()


def test_consistent_backup_includes_uncheckpointed_wal(tmp_path):
    store = Store(tmp_path/'live', Fernet.generate_key().decode())
    try:
        store.set('backup_test', {'fixture':True})
        output = subprocess.run([sys.executable,'-m','backend.backup'], cwd=ROOT,
            env={**os.environ,'PAPERWEEK_DATA_DIR':str(tmp_path/'live')}, capture_output=True,check=True)
        dest = tmp_path/'snapshot.private.sqlite3'
        dest.write_bytes(output.stdout)
        with sqlite3.connect(dest) as conn:
            assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert json.loads(conn.execute("SELECT value FROM kv WHERE key='backup_test'").fetchone()[0]) == {'fixture':True}
    finally:
        store.close()
