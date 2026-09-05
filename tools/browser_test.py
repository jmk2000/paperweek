#!/usr/bin/env python3
"""Offline Chromium component tests: exact JS sources and compiled C/WASM.

Uses an in-memory asset fixture, not a network server. This deliberately does
NOT validate HTTPS hosting, CSP enforcement, service-worker installation, real
Google popups, or an Android device. No external request is made.
"""
import argparse
import base64
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
MODULES=['config','dates','events','google','renderer','app']
def bundle():
    scripts=['globalThis.__modules = {};']
    for name in MODULES:
        text=(ROOT/'web'/f'{name}.mjs').read_text()
        exports=re.findall(r'export\s+(?:async\s+)?(?:function|class|const|let|var)\s+(\w+)',text)
        text=re.sub(r"import\s+\{([^}]+)\}\s+from\s+['\"]\./([^'\"]+)\.mjs['\"];?",lambda m:f"const {{{m.group(1)}}}=__modules[{json.dumps(m.group(2))}];",text)
        text=re.sub(r'\bexport\s+','',text)
        if name=='app':scripts.append(f'globalThis.__app=(async()=>{{{text}\n}})();')
        else:scripts.append(f'__modules[{json.dumps(name)}]=(()=>{{{text}\nreturn {{{",".join(exports)}}};}})();')
    return '\n'.join(scripts)
def mount(page):
    html=(ROOT/'web/index.html').read_text()
    html=re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]+>','',html)
    html=re.sub(r'<link[^>]+>','',html)
    html=re.sub(r'<script type="module"[^>]+></script>','',html)
    html=html.replace('</head>','<style>'+(ROOT/'web/styles.css').read_text()+'</style></head>')
    page.set_content(html)
    wasm=base64.b64encode((ROOT/'dist-preview/paperweek-preview.wasm').read_bytes()).decode()
    fixture="""
      globalThis.__settings=new Map();
      Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{
        getItem:k=>__settings.get(k)||null,setItem:(k,v)=>__settings.set(k,v),removeItem:k=>__settings.delete(k)
      }});
      globalThis.fetch=async path=>{
        if(String(path).endsWith('build-info.json'))return Response.json({backend:'preview',version:'0.3.0'});
        if(String(path).endsWith('paperweek-preview.wasm'))return new Response(Uint8Array.from(atob('@WASM@'),c=>c.charCodeAt(0)),{headers:{'Content-Type':'application/wasm'}});
        throw new Error('Network access is not part of this offline test fixture.');
      };
    """.replace('@WASM@',wasm)
    page.add_script_tag(content=fixture)
    page.add_script_tag(content=bundle())
    page.wait_for_function("document.documentElement.dataset.ready==='true'")

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--chromium');ap.add_argument('--screenshots',type=Path);args=ap.parse_args()
    checks=0
    def check(condition,message):
        nonlocal checks
        checks+=1
        if not condition:raise AssertionError(message)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path=args.chromium)
        page=browser.new_page(viewport={'width':1365,'height':1050},device_scale_factor=1)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        mount(page)
        check('Invented' in page.locator('#message').inner_text(),'Demo loaded')
        check('C/WASM' in page.locator('#engine-label').inner_text(),'Renderer is accurately labelled')
        check(page.locator('#source-badge').inner_text()=='DEMO','Demo not labelled live')
        check(page.locator('#agenda-text li').count()>0,'Accessible agenda populated')
        if args.screenshots:
            args.screenshots.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(args.screenshots/'month.png'),full_page=True)
        page.locator('[data-nav="2"]').click();page.wait_for_timeout(50)
        check(page.locator('[data-nav="2"] span').inner_text()=='Month view','Switched to week')
        if args.screenshots:page.screenshot(path=str(args.screenshots/'week.png'),full_page=True)
        page.locator('#settings-button').click()
        check(page.locator('.member-card').count()==4,'Four generic members')
        page.locator('[name="title"]').fill('Shared planner')
        page.locator('[data-field="label"]').first.fill('Household A')
        page.locator('[name="timezone"]').fill('Europe/London')
        page.locator('[name="weekStart"]').select_option('0')
        page.locator('[name="anchor"]').fill('2026-10-01')
        page.locator('[name="defaultView"]').select_option('month')
        page.locator('button[type="submit"]').click();page.wait_for_timeout(80)
        check(not page.locator('#settings').is_visible(),'Settings applied')
        check(page.evaluate("JSON.parse(__settings.get('paperweek.settings.v3')).title")=='Shared planner','Settings persisted locally')
        page.locator('#settings-button').click()
        check(page.locator('[data-field="label"]').first.input_value()=='Household A','Member label saved')
        check(page.locator('[name="weekStart"]').input_value()=='0','Week start saved')
        page.locator('#add-member').click();page.locator('#add-member').click()
        check(page.locator('.member-card').count()==6,'Can add up to six calendars')
        check(page.locator('#add-member').is_disabled(),'Six-calendar limit enforced')
        page.locator('.remove-member').last.click()
        check(page.locator('.member-card').count()==5,'Can remove calendar')
        page.locator('[data-field="badge"]').nth(1).fill('1')
        page.locator('button[type="submit"]').click()
        check('unique' in page.locator('#settings-message').inner_text(),'Duplicate badge error displayed')
        page.locator('[data-field="badge"]').nth(1).fill('2')
        page.locator('[name="persistentLabels"]').select_option('false')
        page.locator('[name="helpSeconds"]').fill('5')
        page.locator('[name="refreshSeconds"]').fill('0')
        page.locator('button[type="submit"]').click();page.wait_for_timeout(50)
        check(page.locator('[data-nav="0"] span').inner_text()=='','Overlay controls have no always-visible labels')
        page.locator('[data-nav="3"]').click();page.wait_for_timeout(50)
        check('help is visible' in page.locator('#message').inner_text(),'First press reveals help')
        if args.screenshots:page.screenshot(path=str(args.screenshots/'overlay.png'),full_page=True)
        page.locator('#settings-button').click()
        check(page.locator('[name="anchor"]').input_value()=='2026-10-01','First press did not navigate')
        page.locator('#cancel-settings').click()
        page.locator('[data-nav="3"]').click();page.wait_for_timeout(50)
        page.locator('#settings-button').click()
        check(page.locator('[name="anchor"]').input_value()=='2026-11-01','Second press navigates')
        page.locator('#cancel-settings').click()
        # Timer is checked once each second, so allow one scheduling interval.
        page.wait_for_timeout(6200)
        check('help hidden' in page.locator('#message').inner_text(),'Help times out')
        page.locator('#settings-button').click()
        page.locator('[name="source"]').select_option('google')
        page.locator('button[type="submit"]').click()
        check('Choose a Google calendar' in page.locator('#settings-message').inner_text(),'Unmapped live calendars rejected')
        page.locator('[name="source"]').select_option('demo')
        page.locator('[name="persistentLabels"]').select_option('true')
        page.locator('[name="refreshSeconds"]').fill('1')
        page.locator('button[type="submit"]').click()
        check(page.locator('[data-nav="0"]').is_disabled(),'Navigation disabled during refresh')
        page.wait_for_timeout(1200)
        check(page.locator('[data-nav="0"]').is_enabled(),'Navigation restored after refresh')
        page.locator('#settings-button').click()
        if args.screenshots:page.screenshot(path=str(args.screenshots/'settings.png'),full_page=True)
        page.on('dialog',lambda d:d.accept())
        page.locator('#forget').click();page.wait_for_timeout(80)
        check(page.evaluate('__settings.size')==0,'Forget removes saved settings')
        page.locator('#settings-button').click()
        check(page.locator('[data-field="label"]').first.input_value()=='Adult 1','Forget resets names to generic defaults')
        page.locator('#cancel-settings').click()
        check(not errors,f'No unhandled browser exceptions: {errors}')
        # An Android-like viewport tests layout, not the actual Android OS/browser.
        page.set_viewport_size({'width':1280,'height':800});page.wait_for_timeout(50)
        check(page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Tablet layout has no horizontal overflow')
        if args.screenshots:page.screenshot(path=str(args.screenshots/'tablet.png'),full_page=True)
        page.set_viewport_size({'width':800,'height':1280});page.wait_for_timeout(50)
        check(page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Portrait layout has no horizontal overflow')
        browser.close()
    print(f'{checks} offline Chromium component checks passed')
if __name__=='__main__':main()
