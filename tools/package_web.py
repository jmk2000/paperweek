#!/usr/bin/env python3
"""Package only explicitly allowlisted public assets. Never copy a working tree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ['index.html','styles.css','app.mjs','config.mjs','dates.mjs','events.mjs','google.mjs',
          'renderer.mjs','server.html','admin.html','backend-app.mjs','admin.mjs','backend-client.mjs','backend.css','manifest.webmanifest','icon.svg','icon-192.png','icon-512.png']
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
    (out/'build-info.json').write_text(json.dumps({'version':'0.5.0','backend':backend},indent=2)+'\n')
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
    # Separate worker for the authenticated server deployment. It caches ONLY
    # static application assets: never /api responses, OAuth callbacks or tokens.
    server_files = [p for p in files if p not in ('index.html','app.mjs','google.mjs')]
    server_worker = """const SCOPE=new URL(self.registration.scope);
const CACHE='paperweek-server:@HASH@';
const ASSETS=@FILES@.map(p=>new URL(p,SCOPE).href);
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>(k.startsWith('paperweek:')||k.startsWith('paperweek-server:'))&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
 const u=new URL(e.request.url);
 if(e.request.method!=='GET'||u.origin!==SCOPE.origin||u.pathname.startsWith('/api/'))return;
 let target=u.href;
 if(e.request.mode==='navigate'&&['/','/index.html'].includes(u.pathname))target=new URL('server.html',SCOPE).href;
 if(e.request.mode==='navigate'&&u.pathname==='/admin')target=new URL('admin.html',SCOPE).href;
 if(!ASSETS.includes(target))return;
 e.respondWith(fetch(e.request).then(response=>response.ok?response:caches.open(CACHE).then(c=>c.match(target)).then(hit=>hit||response)).catch(()=>caches.open(CACHE).then(c=>c.match(target))));
});
""".replace('@HASH@',digest).replace('@FILES@',json.dumps(server_files))
    (out/'server-sw.js').write_text(server_worker)
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('backend',choices=['preview','lvgl']);args=p.parse_args()
    print(package(args.backend))
