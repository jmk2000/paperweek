#!/usr/bin/env python3
"""Heuristic pre-publication scan. Not a guarantee that a repository is safe."""
import argparse
import re
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SKIP={'build','.git','dist-preview','dist-lvgl','.venv','node_modules','__pycache__','.pytest_cache'}
PATTERNS={
 'private key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 'Google refresh token':re.compile(r'1//[A-Za-z0-9_-]{30,}'),
 'Google client secret':re.compile(r'GOCSPX-[A-Za-z0-9_-]{20,}'),
 'Google API key':re.compile(r'AIza[0-9A-Za-z_-]{30,}'),
 'concrete OAuth client ID':re.compile(r'\b[0-9]{8,}-[A-Za-z0-9_-]{10,}\.apps\.googleusercontent\.com\b'),
 'email address':re.compile(r'\b[A-Za-z0-9._%+-]+@(?!example\.(?:com|org|net)\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--deny-string',action='append',default=[],help='Additional literal private string; not saved in project.');p.add_argument('--tracked',action='store_true');args=p.parse_args()
 if args.tracked:
  r=subprocess.run(['git','ls-files','-z'],cwd=ROOT,check=True,capture_output=True)
  paths=[ROOT/name for name in r.stdout.decode().split('\0') if name]
 else:paths=[x for x in ROOT.rglob('*') if x.is_file() and not set(x.relative_to(ROOT).parts)&SKIP]
 problems=[]
 for path in paths:
  rel=path.relative_to(ROOT)
  if '.private.' in path.name or path.name.startswith(('credentials','client_secret','token.')) or path.suffix in {'.pem','.key','.ics'}:problems.append((str(rel),'private filename'))
  if path.suffix in {'.png','.wasm','.zip'}:continue
  try:text=path.read_text()
  except (UnicodeError,OSError):continue
  for name,pattern in PATTERNS.items():
   if pattern.search(text):problems.append((str(rel),name))
  for value in args.deny_string:
   if value and re.search(r'(?<![A-Za-z])'+re.escape(value)+r'(?![A-Za-z])',text,re.I):problems.append((str(rel),'supplied private string'))
 if problems:
  for path,reason in problems:print(f'REVIEW {path}: {reason}')
  raise SystemExit(1)
 print(f'Privacy heuristic passed for {len(paths)} files. Review images, artifacts and Git history separately.')
if __name__=='__main__':main()
