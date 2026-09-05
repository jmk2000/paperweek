import {defaults,validateConfig} from './config.mjs';
import {createRenderer} from './renderer.mjs';
import {demoEvents,normaliseEvent,validateEvents} from './events.mjs';
import {isoDay,ordinal,zonedParts} from './dates.mjs';
import {api,ApiError,preferences,setPreferences,cacheSnapshot,readOffline,clearOffline} from './backend-client.mjs';
const $=id=>document.getElementById(id);
let config=defaults(),renderer,auth=null,lastGood=null,lastHash='',busy=false,lastPoll=0,retryMs=20000;
let revision=-1,epoch=-1,followToday=true,stale=false,prefs=preferences(),wake=null;
const now=()=>zonedParts(new Date(),config.timezone);
function say(text,error=false){$('message').textContent=text;$('source-badge').textContent=error?'STALE / WAIT':config.source==='demo'?'DEMO':'SERVER';$('source-badge').classList.toggle('error',error);}
function setBusy(value){busy=value;document.querySelectorAll('[data-nav]').forEach(b=>b.disabled=value);$('refresh').disabled=value;}
function labels(){const names=['Previous','Today',renderer.month?'Week view':'Month view','Next'];document.querySelectorAll('[data-nav]').forEach((b,i)=>b.querySelector('span').textContent=config.persistentLabels?names[i]:'');}
function blank(text){renderer.events([]);renderer.render('unavailable',text,true);lastHash='';$('agenda-text').replaceChildren();}
function requirePair(){auth=null;lastGood=null;clearOffline();blank('DISPLAY NOT PAIRED / Open administration to get a pairing code');if(!$('pair-dialog').open)$('pair-dialog').showModal();}
$('pair-dialog').addEventListener('cancel',e=>e.preventDefault());
function assignConfig(next,newRevision,newEpoch){
  const changed=revision!==newRevision||epoch!==newEpoch;
  config=validateConfig(next);
  if(changed){clearOffline();lastGood=null;lastHash='';renderer.configure(config);blank('LOADING / Fetching configured calendars');}
  revision=newRevision;epoch=newEpoch;
  return changed;
}
function expand(snapshot){
  if(snapshot.config.source==='demo')return demoEvents(ordinal(snapshot.first),snapshot.days,config);
  const events=[];
  for(const b of snapshot.batches){const index=config.members.findIndex(m=>m.key===b.member);if(index<0)throw new Error('Calendar mapping changed. Retrying.');
    for(const raw of b.items){const e=normaliseEvent(raw,config.members[index],index,config);if(e)events.push(e);}
  }return validateEvents(events,config);
}
function agenda(events){
  const root=$('agenda-text');root.replaceChildren();
  const groups=new Map();
  for(const e of events){const key=e.startDay; if(!groups.has(key))groups.set(key,[]);groups.get(key).push(e);}
  for(const [day,entries]of [...groups].sort((a,b)=>a[0]-b[0])){
    const heading=document.createElement('h3');heading.textContent=isoDay(day);root.append(heading);
    const list=document.createElement('ul');
    for(const e of entries.sort((a,b)=>a.sortTime-b.sortTime)){const li=document.createElement('li');
      const t=e.allDay?'All day':`${String(Math.floor(e.startSecond/3600)).padStart(2,'0')}:${String(Math.floor(e.startSecond/60)%60).padStart(2,'0')}`;
      const title=['','Working','Working + on-call','Not working'][e.kind]||e.title;
      li.textContent=`${t} — ${config.members[e.calendar].label}: ${title}`;list.append(li);
    }root.append(list);
  }
}
async function paint(force=false){
  const current=now();renderer.clock(current.day,current.second);
  const status=`${stale?'STALE / ':''}${config.source==='demo'?'DEMO / Invented events':'LOCAL SERVER / Read-only'} / ${config.timezone}`;
  const hash=`${renderer.prepare(config.source,status,stale)}:${renderer.helpOpen}:${config.paperPalette}`;
  if(hash===lastHash&&!force)return;
  if(config.refreshSeconds){renderer.placeholder();say(`Refresh delay: ${config.refreshSeconds}s. Not an actual pigment-waveform simulation.`);await new Promise(r=>setTimeout(r,config.refreshSeconds*1000));}
  renderer.draw();lastHash=hash;renderer.visible(performance.now());labels();
}
async function useSnapshot(snapshot,offline=false){
  config=validateConfig(snapshot.config);if(JSON.stringify(renderer.config)!==JSON.stringify(config))renderer.configure(config);
  const range=renderer.range;
  if(ordinal(snapshot.first)!==range.first||snapshot.days!==range.count){
    // Offline copies only cover the saved view; never display a falsely empty month.
    renderer.select(snapshot.anchor??ordinal(snapshot.first)+7,snapshot.month??true);
  }
  const events=expand(snapshot);renderer.events(events);stale=offline||snapshot.stale;
  await paint();agenda(events);lastGood={snapshot,events,anchor:renderer.anchor,month:renderer.month,today:now().day};
  if(!offline&&prefs.offline&&auth){try{cacheSnapshot({...snapshot,anchor:renderer.anchor,month:renderer.month},auth.expires);}catch{say('View loaded, but offline storage is unavailable.',true);}}
  const stamp=snapshot.lastSuccess?new Date(snapshot.lastSuccess*1000).toLocaleString():'';
  if(offline)say('SERVER UNREACHABLE · Showing the saved view; it may be out of date.',true);
  else if(config.source==='demo')say('Invented demo events · Configure Google calendars in Administration');
  else if(stale)say(`${snapshot.connection==='connected'?'Sync delayed': 'Google '+snapshot.connection.replaceAll('_',' ')} · Last complete Google sync ${stamp||'unavailable'}`,true);
  else say(`Google synced ${stamp} · Server checks Google every ${config.pollMinutes} min`);
}
async function load(){
  if(!renderer||busy)return;setBusy(true);retryMs=20000;
  try{
    if(!auth)auth=await api('/api/session');
    const record=await api('/api/display/config');
    const anchor=renderer.anchor,month=renderer.month;
    assignConfig(record.config,record.revision,record.dataEpoch??0);
    renderer.select(anchor,month);renderer.clock(now().day,now().second);
    const range=renderer.range;
    const snapshot=await api(`/api/display/snapshot?first=${isoDay(range.first)}&days=${range.count}`);
    if(snapshot.revision!==record.revision||snapshot.dataEpoch!==record.dataEpoch)throw new Error('Settings changed while loading. Retrying shortly.');
    if(!snapshot.ready){
      retryMs=3000;const problems=snapshot.coverage.filter(c=>!c.ready).length;
      throw new Error(snapshot.connection==='connected'?`Fetching ${problems} calendar/month cache window(s). This can take a minute on the first sync.`:`Google ${snapshot.connection.replaceAll('_',' ')}. An administrator needs to connect Google.`);
    }
    snapshot.anchor=anchor;snapshot.month=month;
    await useSnapshot(snapshot);
  }catch(e){
    if(e.status===401){requirePair();say('Pair this display to continue.',true);return;}
    stale=true;
    if(lastGood){renderer.select(lastGood.anchor,lastGood.month);renderer.events(lastGood.events);await paint();say(e.message+' Showing the last loaded view.',true);}
    else{const cached=prefs.offline&&e.status===0?readOffline():null;
      if(cached){config=validateConfig(cached.snapshot.config);renderer.configure(config);renderer.select(cached.snapshot.anchor,cached.snapshot.month);await useSnapshot(cached.snapshot,true);}
      else{blank('NOT LOADED / '+e.message);say(e.message,true);}
    }
  }finally{lastPoll=Date.now();setBusy(false);labels();document.documentElement.dataset.ready='true';}
}
async function navigate(index){
  if(!renderer||busy||$('pair-dialog').open)return;
  const action=renderer.press(performance.now(),false);
  if(action===1){setBusy(true);try{await paint(true);}finally{setBusy(false);}return;}
  if(action!==2)return;
  if(index===0||index===3)followToday=false;else if(index===1)followToday=true;
  renderer.navigate(index);await load();
}
async function keepAwake(){
  if(!prefs.wake||document.visibilityState!=='visible')return;
  try{if(!navigator.wakeLock)throw new Error('This browser needs HTTPS and wake-lock support.');wake=await navigator.wakeLock.request('screen');$('wake').textContent='Awake · turn off';wake.addEventListener('release',()=>{$('wake').textContent=prefs.wake?'Awake paused':'Keep awake';});}
  catch(e){say('Keep awake unavailable: '+e.message,true);}
}
$('wake').onclick=async()=>{prefs.wake=!prefs.wake;setPreferences(prefs);if(prefs.wake)await keepAwake();else{await wake?.release();$('wake').textContent='Keep awake';}};
$('offline-copy').checked=prefs.offline;
$('offline-copy').onchange=()=>{prefs.offline=$('offline-copy').checked;setPreferences(prefs);if(!prefs.offline)clearOffline();else if(lastGood&&auth)cacheSnapshot(lastGood.snapshot,auth.expires);};
$('pair-form').onsubmit=async e=>{e.preventDefault();$('pair-message').textContent='Pairing…';try{await api('/api/pair',{method:'POST',body:{code:$('pair-code').value}});auth=await api('/api/session');$('pair-code').value='';$('pair-dialog').close();await load();}catch(e){$('pair-message').textContent=e.message;}};
$('forget-device').onclick=async()=>{if(!confirm('Unpair this browser and remove its saved offline calendar?'))return;clearOffline();try{await api('/api/logout',{method:'POST'});}catch{}requirePair();};
$('refresh').onclick=load;
$('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{say('Use Chrome’s home-screen installation or fullscreen controls.');}};
for(const b of document.querySelectorAll('[data-nav]'))b.onclick=()=>navigate(Number(b.dataset.nav));
document.addEventListener('keydown',e=>{if($('pair-dialog').open||['INPUT','BUTTON','SELECT'].includes(document.activeElement?.tagName))return;const map={ArrowLeft:0,ArrowRight:3,t:1,T:1,m:2,M:2,'1':0,'2':1,'3':2,'4':3};if(Object.hasOwn(map,e.key)){e.preventDefault();navigate(map[e.key]);}});
window.addEventListener('online',()=>load());
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){keepAwake();if(renderer&&!busy)load();}});
setInterval(async()=>{
  if(!renderer||busy||$('pair-dialog').open||document.visibilityState!=='visible')return;
  if(renderer.expire(performance.now(),false)){setBusy(true);try{await paint(true);}finally{setBusy(false);}return;}
  const current=now();if(lastGood&&current.day!==lastGood.today&&followToday)renderer.select(current.day,renderer.month);
  if(Date.now()-lastPoll>=retryMs)await load();
},1000);
try{
  renderer=await createRenderer($('calendar'));$('engine-label').textContent=renderer.type;
  renderer.configure(config);renderer.select(now().day,true);blank('CONNECTING TO LOCAL SERVER');
  if('serviceWorker'in navigator&&isSecureContext)navigator.serviceWorker.register('/server-sw.js',{scope:'/'}).catch(()=>{});
  try{auth=await api('/api/session');}catch(e){if(e.status===401){requirePair();throw e;}if(!prefs.offline)throw e;}
  const record=await api('/api/display/config').catch(e=>{if(e.status!==0)throw e;return null;});
  if(record){assignConfig(record.config,record.revision,record.dataEpoch??0);renderer.select(now().day,config.defaultView==='month');}
  await load();await keepAwake();
}catch(e){if(e.status!==401)say('Unable to start: '+e.message,true);document.documentElement.dataset.ready='true';}
