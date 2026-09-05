import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {defaults,validateConfig,ascii,loadConfig,saveConfig,STORAGE_KEY} from '../web/config.mjs';
import {ordinal,isoDay,zonedParts,googleBounds} from '../web/dates.mjs';
import {normaliseEvent,demoEvents,validateEvents,MAX_EVENTS} from '../web/events.mjs';
import {GoogleSource,ReconnectError,validGoogleOrigin} from '../web/google.mjs';
import {Renderer} from '../web/renderer.mjs';

const config=defaults();config.timezone='Europe/London';
function raw(extra={}){return {id:'fixture-event',iCalUID:'fixture-uid',summary:'A title',start:{dateTime:'2026-10-04T13:00:00+01:00'},end:{dateTime:'2026-10-04T14:00:00+01:00'},...extra};}
function event(extra={},member=0,c=config){return normaliseEvent(raw(extra),c.members[member],member,c);}
test('default settings are generic and round-trip',()=>{assert.deepEqual(validateConfig(defaults()),defaults());});
test('unknown secrets are removed from configuration',()=>{const c=validateConfig({...defaults(),access_token:'mock',client_secret:'mock',refresh_token:'mock'});assert.equal('access_token'in c,false);assert.equal('client_secret'in c,false);});
test('settings storage contains no token fields',()=>{const values=new Map();const storage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)};saveConfig({...defaults(),token:'mock'},storage);assert.ok(values.has(STORAGE_KEY));assert.deepEqual(loadConfig(storage),defaults());assert.ok(!values.get(STORAGE_KEY).includes('token'));});
for(const [name,mutate]of[
  ['duplicate members',c=>c.members[1].key=c.members[0].key],['duplicate badges',c=>c.members[1].badge=c.members[0].badge],
  ['unknown timezone',c=>c.timezone='not/a-zone'],['invalid colour',c=>c.members[0].colour='purple'],
  ['empty member list',c=>c.members=[]],['too many members',c=>c.members.push(...c.members)],
  ['invalid rota member',c=>c.rotaMember='missing'],['string boolean',c=>c.maskPrivate='yes'],
  ['invalid client secret',c=>c.clientId='secret-is-not-a-client-id'],['bad refresh delay',c=>c.refreshSeconds=99],
  ['HTML badge',c=>c.members[0].badge='<x'],['control in title',c=>c.title='bad\n'],
])test(`reject ${name}`,()=>{const c=defaults();mutate(c);assert.throws(()=>validateConfig(c));});
test('duplicate Google calendars rejected',()=>{const c=defaults();c.members[0].calendarId='example-calendar';c.members[1].calendarId='example-calendar';assert.throws(()=>validateConfig(c));});
test('ASCII conversion is bounded and removes controls',()=>{assert.equal(ascii('Café — tea\nø'), 'Cafe - tea o');assert.equal(ascii('1234567890',7),'1234...');assert.equal(ascii('東京'), '??');});
test('Gregorian dates reject overflow',()=>{assert.throws(()=>ordinal('2026-02-30'));assert.throws(()=>ordinal('2026-13-01'));assert.equal(isoDay(ordinal('2024-02-29')),'2024-02-29');});
test('timezone conversion before and after spring DST',()=>{assert.equal(zonedParts('2026-03-29T00:30:00Z','Europe/London').second,1800);assert.equal(zonedParts('2026-03-29T01:30:00Z','Europe/London').second,9000);});
test('timezone conversion across midnight',()=>{const p=zonedParts('2026-01-01T23:30:00Z','Asia/Tokyo');assert.equal(isoDay(p.day),'2026-01-02');assert.equal(p.second,30600);});
test('Google range is generously bounded',()=>{const b=googleBounds(ordinal('2026-10-01'),35);assert.equal(b.timeMin,'2026-09-29T00:00:00.000Z');assert.equal(b.timeMax,'2026-11-07T00:00:00.000Z');});
test('normalisation keeps wall time and epoch ordering',()=>{const e=event();assert.equal(e.startSecond,13*3600);assert.equal(e.sortTime,Date.parse('2026-10-04T12:00:00Z'));});
test('cancelled and self-declined events disappear',()=>{assert.equal(event({status:'cancelled'}),null);assert.equal(event({attendees:[{self:true,responseStatus:'declined'}]}),null);assert.notEqual(event({attendees:[{self:false,responseStatus:'declined'}]}),null);});
test('private titles masked',()=>{assert.equal(event({visibility:'private',summary:'Sensitive title'}).title,'Busy');});
test('whole calendar masking',()=>{const c=defaults();c.members[0].maskTitles=true;assert.equal(event({summary:'Sensitive title'},0,c).title,'Busy');});
test('rota markers recognised only for the selected person',()=>{assert.equal(event({summary:'[PW:ONCALL] Shift'},1).kind,2);assert.equal(event({summary:'[PW:ONCALL] Shift'},0).kind,0);});
test('private rota classification precedes title masking',()=>{const e=event({summary:'[PW:WORK] Shift',visibility:'private'},1);assert.equal(e.kind,1);assert.equal(e.title,'Busy');});
test('off-duty marker must be all-day',()=>{assert.throws(()=>event({summary:'[PW:OFF] Off'},1));const e=event({summary:'[PW:OFF]',start:{date:'2026-10-04'},end:{date:'2026-10-05'}},1);assert.equal(e.kind,3);assert.ok(e.allDay);});
test('all-day exclusive end validation',()=>{assert.throws(()=>event({start:{date:'2026-10-04'},end:{date:'2026-10-04'}}));assert.equal(event({start:{date:'2026-10-04'},end:{date:'2026-10-06'}}).endDay-ordinal('2026-10-04'),2);});
test('ambiguous naive timestamps rejected',()=>{assert.throws(()=>event({start:{dateTime:'2026-10-04T13:00:00'}}));});
test('negative actual duration rejected',()=>{assert.throws(()=>event({end:{dateTime:'2026-10-04T12:00:00+01:00'}}));});
test('DST fall-back with locally earlier end accepted',()=>{const e=event({start:{dateTime:'2026-10-25T01:50:00+01:00'},end:{dateTime:'2026-10-25T01:10:00+00:00'}});assert.ok(e.endSecond<e.startSecond);});
test('recurrence instances have different keys; shared invites have matching keys',()=>{assert.notEqual(event().key,event({start:{dateTime:'2026-10-11T13:00:00+01:00'},end:{dateTime:'2026-10-11T14:00:00+01:00'}}).key);assert.equal(event({},0).key,event({},1).key);});
test('long identities with the same prefix do not collapse',()=>{const p='x'.repeat(300);assert.notEqual(event({iCalUID:p+'a'}).key,event({iCalUID:p+'b'}).key);});
test('demo varies with config and respects bounds',()=>{const c=defaults();for(const n of [1,4,6]){while(c.members.length<n)c.members.push({key:`m${c.members.length}`,label:'Calendar',badge:String(c.members.length+1),colour:'black',calendarId:'',maskTitles:false});c.members=c.members.slice(0,n);c.rotaMember=c.members[0].key;const list=demoEvents(ordinal('2026-10-01'),42,c);assert.ok(list.length>0&&list.length<MAX_EVENTS);assert.ok(list.every(e=>e.calendar<n));}});
test('oversized data rejected, not truncated',()=>{assert.throws(()=>validateEvents(Array.from({length:MAX_EVENTS+1},()=>event()),config));});
test('Google origins accept HTTPS/loopback but reject plain LAN HTTP',()=>{assert.ok(validGoogleOrigin(new URL('https://example.com')));assert.ok(validGoogleOrigin(new URL('http://localhost:8080')));assert.ok(!validGoogleOrigin(new URL('http://192.168.1.10:8080')));});
test('expired tokens require user reconnect',async()=>{let time=1000;const g=new GoogleSource(()=>{throw Error('should not fetch')},()=>time);g.acceptToken('mock-token',3600);assert.ok(g.connected);time+=3600000;assert.ok(!g.connected);await assert.rejects(g.calendars(),ReconnectError);});
test('Calendar list follows pagination and filters freeBusy-only entries',async()=>{const urls=[];const pages=[{items:[{id:'one',summary:'One',accessRole:'reader'},{id:'hidden',accessRole:'freeBusyReader'}],nextPageToken:'p2'},{items:[{id:'two',summary:'Two',accessRole:'owner'}]}];const g=new GoogleSource(async(url,opts)=>{urls.push(url);assert.equal(opts.headers.Authorization,'Bearer mock-token');assert.equal(opts.credentials,'omit');return Response.json(pages.shift());});g.acceptToken('mock-token',3600);assert.equal((await g.calendars()).length,2);assert.equal(urls[1].searchParams.get('pageToken'),'p2');});
test('event pagination includes empty intermediate pages',async()=>{const c=defaults();c.members=c.members.slice(0,1);c.members[0].calendarId='demo-calendar';c.rotaMember='';let calls=0;const g=new GoogleSource(async url=>{++calls;assert.equal(url.searchParams.get('singleEvents'),'true');return Response.json(calls===1?{items:[],nextPageToken:'second'}:{items:[raw()]});});g.acceptToken('mock-token',3600);assert.equal((await g.events(c,ordinal('2026-10-01'),35)).length,1);assert.equal(calls,2);});
test('partial cross-calendar responses are never returned',async()=>{const c=defaults();c.members=c.members.slice(0,2);c.members.forEach((m,i)=>m.calendarId=`cal-${i}`);let calls=0;const g=new GoogleSource(async()=>++calls===1?Response.json({items:[raw()]}):new Response('',{status:403}));g.acceptToken('mock-token',3600);await assert.rejects(g.events(c,ordinal('2026-10-01'),35),/denied/);});
test('401 clears token and asks to reconnect',async()=>{const g=new GoogleSource(async()=>new Response('',{status:401}));g.acceptToken('mock-token',3600);await assert.rejects(g.calendars(),ReconnectError);assert.ok(!g.connected);});
test('repeated pagination token is rejected',async()=>{const g=new GoogleSource(async()=>Response.json({items:[],nextPageToken:'repeat'}));g.acceptToken('mock-token',3600);await assert.rejects(g.calendars(),/pagination/);});
test('arbitrary endpoints cannot receive bearer credentials',async()=>{let calls=0;const g=new GoogleSource(async()=>{++calls;return Response.json({})});g.acceptToken('mock-token',3600);await assert.rejects(g.request('https://example.com/'),/Refusing/);assert.equal(calls,0);});
async function wasm(){const buffer=await fs.readFile(new URL('../dist-preview/paperweek-preview.wasm',import.meta.url));let instance;const texts=[],decoder=new TextDecoder(),encoder=new TextEncoder();const string=ptr=>{const h=new Uint8Array(instance.exports.memory.buffer);let end=ptr;while(h[end])++end;return decoder.decode(h.subarray(ptr,end));};({instance}=await WebAssembly.instantiate(buffer,{paperweek:{begin(){texts.length=0;},rect(){},text(x,y,w,h,p){texts.push(string(p));},end(){}}}));
  const call=(name,...args)=>{let p=instance.exports.pw_input_buffer();const heap=new Uint8Array(instance.exports.memory.buffer);const values=args.map(v=>{if(typeof v!=='string')return v;const b=encoder.encode(v),a=p;heap.set(b,p);p+=b.length;heap[p++]=0;return a;});return instance.exports[name](...values);};call('pw_init');return {r:new Renderer(call,'test',null),texts};}
test('actual WASM renders names from configuration, not hard-coded labels',async()=>{const {r,texts}=await wasm();const c=defaults();c.members[0].label='Household A';r.configure(c);const d=ordinal('2026-10-04');r.clock(d,3600);r.select(d,false);r.events(demoEvents(r.range.first,r.range.count,c));r.render('demo','DEMO');assert.ok(texts.includes('Household A'));assert.ok(!texts.includes('Adult 1'));assert.equal(r.call('pw_day_count'),7);});
test('actual WASM month navigation preserves dates and clamps month end',async()=>{const {r}=await wasm();r.configure(defaults());r.select(ordinal('2026-01-31'),true);r.navigate(3);assert.equal(isoDay(r.anchor),'2026-02-28');r.navigate(2);assert.equal(r.month,false);assert.equal(isoDay(r.anchor),'2026-02-28');});
test('actual WASM model hash does not depend on poll timestamp',async()=>{const {r}=await wasm();const c=defaults();r.configure(c);const d=ordinal('2026-10-01');r.clock(d,0);r.select(d,true);r.events(demoEvents(r.range.first,r.range.count,c));const a=r.prepare('demo','DEMO');r.clock(d,1);assert.equal(r.prepare('demo','DEMO'),a);assert.notEqual(r.prepare('demo','STALE',true),a);});
test('actual WASM renders Sunday first when configured',async()=>{const {r,texts}=await wasm();const c=defaults();c.weekStart=0;r.configure(c);const d=ordinal('2026-10-01');r.clock(d,0);r.select(d,true);r.events([]);r.render('demo','DEMO');const headers=texts.filter(t=>/^(MON|TUE|WED|THU|FRI|SAT|SUN)$/.test(t));assert.equal(headers[0],'SUN');});
test('actual WASM overlay consumes first press and expires after visible timer',async()=>{const {r}=await wasm();const c=defaults();c.persistentLabels=false;r.configure(c);assert.equal(r.press(0,false),1);assert.equal(r.helpOpen,true);assert.equal(r.expire(30000,true),false);r.visible(19000);assert.equal(r.expire(38999,false),false);assert.equal(r.expire(39000,false),true);assert.equal(r.press(40000,false),1);assert.equal(r.press(40001,false),2);});

test('swipes distinguish horizontal navigation from scrolling, taps and slow drags',async()=>{
  const {swipeAction}=await import('../web/display-controls.mjs');
  assert.equal(swipeAction(-120,10,200),3);
  assert.equal(swipeAction(120,-10,200),0);
  for(const args of [[20,0,200],[80,100,200],[120,0,1000],[0,0,0]])assert.equal(swipeAction(...args),null);
});
test('web viewport removes hardware labels and touch navigation acts immediately',async()=>{
  const {r,texts}=await wasm();r.canvas={};r.configure({...defaults(),persistentLabels:false});
  r.call('pw_viewport',1900);r.select(ordinal('2026-09-05'),true);r.clock(ordinal('2026-09-05'),0);r.events([]);r.render('demo','DEMO');
  assert.ok(!texts.some(t=>t.includes('PREVIOUS')||t.includes('frame button')));
  assert.equal(r.press(0,false),2);
});
