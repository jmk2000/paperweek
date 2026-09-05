#!/usr/bin/env python3
"""Package only explicitly allowlisted public assets. Never copy a working tree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ['index.html','styles.css','app.mjs','config.mjs','dates.mjs','events.mjs','google.mjs',
          'renderer.mjs','manifest.webmanifest','icon.svg','icon-192.png','icon-512.png']
def package(backend: str) -> Path:
    out = ROOT / f'dist-{backend}'
    if out.exists(): shutil.rmtree(out)
    out.mkdir()
    for name in ASSETS: shutil.copy2(ROOT / 'web' / name, out / name)
    binaries = ['paperweek-preview.wasm'] if backend=='preview' else ['paperweek-lvgl.wasm','paperweek-lvgl.mjs']
    source = ROOT / 'build' / backend
    for name in binaries:
        if not (source/name).is_file(): raise SystemExit(f'Missing {source/name}; build {backend} first.')
        shutil.copy2(source/name,out/name)
    (out/'build-info.json').write_text(json.dumps({'version':'0.3.0','backend':backend},indent=2)+'\n')
    (out/'.nojekyll').write_text('')
    # Licence text is public metadata, not a household setting. Do not copy any
    # font file or other unreviewed build asset into the distribution.
    shutil.copy2(ROOT/'LICENSE',out/'LICENSE.txt')
    shutil.copy2(ROOT/'docs'/'THIRD_PARTY.md',out/'THIRD_PARTY.md')
    notices = ['LICENSE.txt','THIRD_PARTY.md']
    if backend == 'lvgl':
        lvgl_license = ROOT/'build'/'lvgl'/'_deps'/'lvgl-src'/'LICENCE.txt'
        if not lvgl_license.is_file():
            raise SystemExit('LVGL licence missing: review dependency checkout before publishing.')
        shutil.copy2(lvgl_license,out/'LVGL-LICENSE.txt')
        notices.append('LVGL-LICENSE.txt')
        emcc = shutil.which('emcc')
        runtime_license = Path(emcc).resolve().parent/'LICENSE' if emcc else None
        if runtime_license is None or not runtime_license.is_file():
            raise SystemExit('Emscripten licence missing: activate the SDK before packaging.')
        shutil.copy2(runtime_license,out/'EMSCRIPTEN-LICENSE.txt')
        notices.append('EMSCRIPTEN-LICENSE.txt')
    files = sorted([*ASSETS,*binaries,'build-info.json',*notices])
    digest = hashlib.sha256(b''.join((out/p).read_bytes() for p in files)).hexdigest()[:16]
    # Only the public app shell is cached. Google requests and local settings are
    # never handled by this worker. A changed build waits for old tabs to close.
    worker = """/* Generated public-assets-only cache. */
const SCOPE=new URL(self.registration.scope);
const PREFIX='paperweek:'+SCOPE.pathname+':';
const CACHE=PREFIX+'@HASH@';
const ASSETS=@FILES@.map(p=>new URL(p,SCOPE).href);
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith(PREFIX)&&k!==CACHE).map(k=>caches.delete(k))))));
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(event.request.method!=='GET'||url.origin!==SCOPE.origin)return;
  let target=url.href;
  if(event.request.mode==='navigate'&&(url.pathname===SCOPE.pathname||url.pathname===SCOPE.pathname+'index.html'))target=new URL('index.html',SCOPE).href;
  if(!ASSETS.includes(target))return;
  event.respondWith(caches.open(CACHE).then(c=>c.match(target)).then(hit=>hit||fetch(event.request)));
});
""".replace('@HASH@',digest).replace('@FILES@',json.dumps(files))
    (out/'sw.js').write_text(worker)
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('backend',choices=['preview','lvgl']);args=p.parse_args()
    print(package(args.backend))
