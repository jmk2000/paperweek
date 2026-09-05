import test from 'node:test';
import assert from 'node:assert/strict';
import {api,ApiError,cacheSnapshot,readOffline,clearOffline,preferences,setPreferences,CACHE_KEY} from '../web/backend-client.mjs';
function storage(){const map=new Map();return {getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)};}
const snap={ready:true,days:42,first:'2026-10-01',config:{title:'Example'},batches:[]};
test('offline copy is bounded by session expiry',()=>{const s=storage(),now=100000;cacheSnapshot(snap,(now+3600000)/1000,s,now);assert.ok(readOffline(s,now+500));assert.equal(readOffline(s,now+3600001),null);});
test('offline copy expires within seven days',()=>{const s=storage(),now=100000;cacheSnapshot(snap,999999999,s,now);assert.equal(readOffline(s,now+8*86400000),null);});
test('incomplete views never replace an offline copy',()=>{const s=storage();cacheSnapshot(snap,99999999999,s);cacheSnapshot({...snap,ready:false},99999999999,s);assert.deepEqual(readOffline(s).snapshot,snap);});
test('malformed local storage is cleared',()=>{const s=storage();s.setItem(CACHE_KEY,'not JSON');assert.equal(readOffline(s),null);assert.equal(s.getItem(CACHE_KEY),null);});
test('oversized local copy is refused',()=>{const s=storage();assert.throws(()=>cacheSnapshot({...snap,large:'x'.repeat(2_000_001)},99999999999,s));});
test('local preference defaults do not persist events by surprise',()=>{const s=storage();assert.equal(preferences(s).offline,false);setPreferences({offline:true},s);assert.equal(preferences(s).offline,true);});
test('clear offline removes the stored view',()=>{const s=storage();cacheSnapshot(snap,99999999999,s);clearOffline(s);assert.equal(readOffline(s),null);});
test('API rejects arbitrary targets',async()=>{await assert.rejects(api('https://example.com'),/local Paperweek/);});
test('API writes use JSON, a same-origin session and CSRF header',async()=>{const original=globalThis.fetch;let seen;globalThis.fetch=async(path,opts)=>{seen={path,opts};return Response.json({ok:true});};try{assert.deepEqual(await api('/api/admin/sync',{method:'POST'}),{ok:true});assert.equal(seen.opts.credentials,'same-origin');assert.equal(seen.opts.headers['X-Paperweek-Request'],'1');assert.equal(seen.opts.body,'{}');assert.equal(seen.opts.cache,'no-store');}finally{globalThis.fetch=original;}});
test('API surfaces authorization errors without relabelling them offline',async()=>{const original=globalThis.fetch;globalThis.fetch=async()=>Response.json({detail:'Pair again.'},{status:401});try{await assert.rejects(api('/api/session'),e=>e instanceof ApiError&&e.status===401);}finally{globalThis.fetch=original;}});
test('API distinguishes network failures',async()=>{const original=globalThis.fetch;globalThis.fetch=async()=>{throw new Error('network');};try{await assert.rejects(api('/api/session'),e=>e.status===0);}finally{globalThis.fetch=original;}});
