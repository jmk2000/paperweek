"""Optional no-network host for managed browsers that disallow all navigation.

Loads the exact packaged ES modules via native Blob module imports; actual C/WASM
runs unchanged. API and localStorage are in-memory test doubles. This exercises
rendering/behaviour, NOT origin security, CSP, service workers or real storage.
The default HTTP smoke test remains the deployment-facing test path.
"""
import base64
from pathlib import Path
import re

class MemoryHost:
    def __init__(self, page, site, api):
        self.page, self.site, self.api = page, Path(site), api
        self.storage = {}
        self.started = False

    async def setup(self):
        host = self
        class Request:
            def __init__(self, data):
                self.url=data['url']; self.method=data['method']; self.headers=data['headers']
                import json
                self.post_data_json=json.loads(data['body']) if data.get('body') else None
        class Route:
            def __init__(self,data): self.request=Request(data); self.result=None
            async def fulfill(self, status=200, json=None): self.result={'status':status,'json':json}
            async def abort(self,*_): self.result={'abort':True}
        async def request(data):
            route=Route(data); await host.api.handle(route); return route.result
        await self.page.expose_function('__fixtureAPI',request)

    async def load(self, admin=False):
        if self.started:
            self.storage = await self.page.evaluate('globalThis.__plannerTestStorage || {}')
        await self.page.goto('about:blank')
        html = (self.site/('admin.html' if admin else 'server.html')).read_text()
        # Embed local styles and remove network assets. No CSP is simulated here.
        html = re.sub(r'<link[^>]*rel="stylesheet"[^>]*href="\.\/([^\"]+)"[^>]*>',
                      lambda m:'<style>'+ (self.site/m[1]).read_text()+'</style>',html)
        html = re.sub(r'<link\b[^>]*>','',html)
        html = re.sub(r'<script\b[^>]*>.*?</script>','',html,flags=re.S)
        await self.page.set_content(html)
        modules = {p.name:p.read_text() for p in self.site.glob('*.mjs')}
        assets = {p.name:base64.b64encode(p.read_bytes()).decode() for p in self.site.iterdir() if p.suffix in ('.json','.wasm')}
        await self.page.evaluate(r'''async ({modules,assets,storage,entry})=>{
          globalThis.__plannerTestStorage=storage;
          Object.defineProperty(window,'localStorage',{configurable:true,value:{
            getItem:k=>Object.hasOwn(storage,k)?storage[k]:null,
            setItem:(k,v)=>{storage[k]=String(v)},removeItem:k=>{delete storage[k]},clear:()=>{for(const k in storage)delete storage[k]}
          }});
          globalThis.fetch=async (input,options={})=>{
            const url=new URL(String(input),'https://paperweek.test/');
            if(url.pathname.startsWith('/api/')) {
              const result=await globalThis.__fixtureAPI({url:url.href,method:options.method||'GET',headers:Object.fromEntries(new Headers(options.headers||{})),body:options.body});
              if(result.abort)throw new TypeError('Mock server is offline');
              return new Response(JSON.stringify(result.json),{status:result.status,headers:{'Content-Type':'application/json'}});
            }
            const name=url.pathname.split('/').pop();
            if(!Object.hasOwn(assets,name))return new Response('Not found',{status:404});
            const bytes=Uint8Array.from(atob(assets[name]),c=>c.charCodeAt(0));
            return new Response(bytes,{headers:{'Content-Type':name.endsWith('.wasm')?'application/wasm':'application/json'}});
          };
          const compiled=new Map();
          async function compile(name) {
            if(compiled.has(name))return compiled.get(name);
            const source=modules[name];if(source===undefined)throw Error('Missing module '+name);
            const imports=[...source.matchAll(/(['"])\.\/([a-zA-Z0-9_-]+\.mjs)\1/g)];
            // Give Emscripten a hierarchical virtual asset URL; no network is used.
            let rewritten=source.replaceAll('import.meta.url',JSON.stringify('https://paperweek.test/'+name));
            for(const m of imports){const target=await compile(m[2]);rewritten=rewritten.split(m[0]).join(JSON.stringify(target));}
            const url=URL.createObjectURL(new Blob([rewritten],{type:'text/javascript'}));compiled.set(name,url);return url;
          }
          await import(await compile(entry));
        }''',dict(modules=modules,assets=assets,storage=self.storage,entry='admin.mjs' if admin else 'backend-app.mjs'))
        self.started=True
