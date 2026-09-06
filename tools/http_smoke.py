#!/usr/bin/env python3
"""Real HTTP/WASM smoke test for local use or CI. Requires installed Chromium.
Unlike browser_test.py this checks actual module loading and the page's CSP.
It does not automate Google sign-in or prove PWA installability on Android.
"""
import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--backend',choices=['preview','lvgl'],default='lvgl');p.add_argument('--chromium');p.add_argument('--port',type=int,default=8877);args=p.parse_args()
 server=subprocess.Popen([sys.executable,str(ROOT/'serve.py'),'--directory',f'dist-{args.backend}','--port',str(args.port)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  url=f'http://127.0.0.1:{args.port}/'
  for _ in range(40):
   try:urllib.request.urlopen(url,timeout=.5).close();break
   except Exception:time.sleep(.1)
  else:raise RuntimeError('Local static server did not become available.')
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True,executable_path=args.chromium)
   page=browser.new_page(viewport={'width':1280,'height':900});errors=[]
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(url,wait_until='networkidle');page.wait_for_function("document.documentElement.dataset.ready==='true'",timeout=60000)
   label=page.locator('#engine-label').inner_text()
   assert ('LVGL / WebAssembly' in label) if args.backend=='lvgl' else ('C/WASM preview' in label)
   assert page.locator('#source-badge').inner_text()=='DEMO'
   assert page.locator('#agenda-text li').count()>0
   pixel=page.locator('#calendar').evaluate('(c)=>{const a=c.getContext("2d").getImageData(0,0,c.width,c.height).data;let dark=0;for(let i=0;i<a.length;i+=4)if(a[i]<100&&a[i+1]<100&&a[i+2]<100)++dark;return dark;}')
   assert pixel>1000,'Calendar text did not render'
   page.locator('[data-nav="2"]').click();page.wait_for_timeout(200)
   assert 'Month view' in page.locator('[data-nav="2"] span').inner_text()
   manifest=page.evaluate("fetch('./manifest.webmanifest').then(r=>r.json())")
   assert manifest['display']=='standalone'
   assert any('maskable' in icon.get('purpose','') for icon in manifest['icons'])
   page.evaluate("navigator.serviceWorker.ready.then(()=>true)")
   page.reload(wait_until='networkidle')
   page.wait_for_function("document.documentElement.dataset.ready==='true'")
   page.context.set_offline(True)
   page.reload(wait_until='load')
   page.wait_for_function("document.documentElement.dataset.ready==='true'")
   assert page.locator('#agenda-text li').count()>0,'Cached app shell failed offline'
   assert not errors,errors
   browser.close()
  print(f'{args.backend} real HTTP renderer smoke test passed')
 finally:server.terminate();server.wait(timeout=5)
if __name__=='__main__':main()
