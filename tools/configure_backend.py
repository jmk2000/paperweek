#!/usr/bin/env python3
"""Create private runtime secrets using Python's standard library only.

Run in the repository root. Never upload the resulting .env.private or client JSON.
Existing encryption keys are preserved; changing the key breaks stored credentials.
"""
import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit


def read_env(path):
    result = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.split('=', 1)
                result[k.strip()] = v.strip().strip("'\"")
    return result


def write_private(path, content):
    temp = path.with_name(path.name + '.private.tmp')
    fd = os.open(temp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-url', required=True, help='HTTPS origin, no path')
    parser.add_argument('--google-client', type=Path, help='Downloaded Google Web application client JSON')
    parser.add_argument('--reset-admin', action='store_true', help='Replace admin password without changing the encryption key')
    parser.add_argument('--prompt-password', action='store_true', help='Choose a password instead of generating one')
    args = parser.parse_args()
    url = args.public_url.rstrip('/')
    u = urlsplit(url)
    if not u.hostname or (u.scheme != 'https' and not (u.scheme == 'http' and u.hostname in ('localhost','127.0.0.1','::1'))) or u.path or u.query or u.fragment or u.username:
        parser.error('Use an HTTPS origin, for example https://paperweek.example.net (HTTP only for localhost).')
    root = Path(__file__).resolve().parents[1]
    private = root / '.env.private'
    values = read_env(private)
    password = None
    if 'PAPERWEEK_TOKEN_KEY' not in values:
        values['PAPERWEEK_TOKEN_KEY'] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    if 'PAPERWEEK_ADMIN_HASH' not in values or args.reset_admin:
        password = getpass.getpass('New admin password (at least 14 characters): ') if args.prompt_password else secrets.token_urlsafe(24)
        if len(password) < 14:
            parser.error('Use an administrator password of at least 14 characters.')
        salt = secrets.token_bytes(16)
        derived = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=67108864)
        values['PAPERWEEK_ADMIN_HASH'] = 'scrypt:' + base64.urlsafe_b64encode(salt).decode() + ':' + base64.urlsafe_b64encode(derived).decode()
    if args.google_client:
        try:
            raw = json.loads(args.google_client.read_text())
            client = raw['web']
            if not client.get('client_id', '').endswith('.apps.googleusercontent.com') or not client.get('client_secret'):
                raise ValueError('Missing Web client values.')
        except (ValueError, KeyError, OSError) as e:
            parser.error('Could not read a Google Web application client JSON (not a Desktop client).')
        values['PAPERWEEK_GOOGLE_CLIENT_ID'] = client['client_id']
        values['PAPERWEEK_GOOGLE_CLIENT_SECRET'] = client['client_secret']
    else:
        values.setdefault('PAPERWEEK_GOOGLE_CLIENT_ID', '')
        values.setdefault('PAPERWEEK_GOOGLE_CLIENT_SECRET', '')
    if any(any(c in str(v) for c in "\r\n'$") for v in values.values()):
        parser.error('Private values contain unsupported dotenv characters.')
    write_private(private, '# PRIVATE. Never commit. Back up with the database.\n' + ''.join(f"{k}='{v}'\n" for k,v in values.items()))
    env = root / '.env'
    content = env.read_text() if env.exists() else (root / '.env.example').read_text()
    line = 'PAPERWEEK_PUBLIC_URL=' + url
    if re.search(r'^PAPERWEEK_PUBLIC_URL=', content, re.M):
        content = re.sub(r'^PAPERWEEK_PUBLIC_URL=.*$', line, content, flags=re.M)
    else:
        content += '\n' + line + '\n'
    write_private(env, content)
    print('Private runtime configuration written. Encryption key preserved on subsequent runs.')
    print('Admin page: ' + url + '/admin')
    print('Google authorized redirect URI: ' + url + '/api/oauth/callback')
    if password:
        print('\nSAVE THIS ADMINISTRATOR PASSWORD IN YOUR PASSWORD MANAGER:\n' + password + '\n')
    if not values['PAPERWEEK_GOOGLE_CLIENT_ID']:
        print('Google is not configured yet. Demo and device pairing will work; rerun with --google-client to enable live sync.')
    print('Recreate the container after changes. Keep .env.private and backups out of Git.')


if __name__ == '__main__':
    main()
