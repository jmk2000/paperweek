import {setupDisplay,showBuild} from './display-controls.mjs';
import {defaults,validateConfig,loadConfig,saveConfig,clearConfig,ascii} from './config.mjs';
import {createRenderer} from './renderer.mjs';
import {demoEvents} from './events.mjs';
import {GoogleSource,loadGoogleLibrary,ReconnectError} from './google.mjs';
import {isoDay,ordinal,zonedParts} from './dates.mjs';

const $=id=>document.getElementById(id), form=$('settings-form'), dialog=$('settings');
let config, startupWarning='';
try{config=loadConfig();}catch{config=defaults();startupWarning='Saved settings were invalid or unavailable. Generic defaults loaded; review Settings.';}
const googleSource=new GoogleSource();
let renderer, availableCalendars=[], connectedClient='', revision=0, controller=null, busy=false;
let lastGood=null, lastHash='', draft=null, wake=null, wantWake=false, lastPoll=0, staleData=false, followToday=true;
const now=()=>zonedParts(new Date(),config.timezone);
function say(text,error=false){$('message').textContent=text;$('source-badge').textContent=error?'NOT SYNCED':config.source==='demo'?'DEMO':'GOOGLE';$('source-badge').classList.toggle('error',error);}
function note(text){$('settings-message').textContent=text;}
function setBusy(value){busy=value;document.querySelectorAll('[data-nav]').forEach(b=>b.disabled=value);$('refresh').disabled=value;}
function updateLabels(){const labels=['Previous','Today',renderer?.month?'Week view':'Month view','Next'];document.querySelectorAll('[data-nav]').forEach((b,i)=>{b.querySelector('span').textContent=labels[i];});}
function stableStatus(stale=false){return `${stale?'STALE / ':''}${config.source==='demo'?'DEMO / Invented events':'GOOGLE / Read-only'} / ${config.timezone}`;}
function pause(ms,signal){return new Promise((resolve,reject)=>{
  if(signal.aborted)return reject(new DOMException('Cancelled','AbortError'));
  const onAbort=()=>{clearTimeout(id);reject(new DOMException('Cancelled','AbortError'));};
  const id=setTimeout(()=>{signal.removeEventListener('abort',onAbort);resolve();},ms);signal.addEventListener('abort',onAbort,{once:true});
});}
async function paint(force,run,signal,stale=staleData){
  const current=now();renderer.clock(current.day,current.second);
  const hash=`${renderer.prepare(config.source,stableStatus(stale),stale)}:${renderer.helpOpen}:${config.paperPalette}`;
  if(hash===lastHash&&!force)return;
  if(config.refreshSeconds){renderer.placeholder();say(`Refresh delay: ${config.refreshSeconds}s. Real e-paper would pass through intermediate pigment states.`);await pause(config.refreshSeconds*1000,signal);}
  if(run!==revision)return;
  renderer.draw();lastHash=hash;renderer.visible(performance.now());updateLabels();
}
function displayAgenda(events,first,count){
  const container=$('agenda-text');container.replaceChildren();
  const intro=document.createElement('p');intro.textContent=`${config.source==='demo'?'Invented demo events':'Google events'} in the loaded range. Includes entries hidden by the visual layout's density limit.`;container.append(intro);
  const seen=new Set();const selected=events.filter(e=>{if(!config.deduplicate)return true;if(seen.has(e.key))return false;seen.add(e.key);return true;});
  for(let d=first;d<first+count;++d){
    const matching=selected.filter(e=>e.allDay?e.startDay<=d&&d<e.endDay:e.startDay<=d&&(e.endDay>d||(e.endDay===d&&e.endSecond>0)||(e.startDay===d&&e.startSecond===e.endSecond))).sort((a,b)=>Number(b.allDay)-Number(a.allDay)||a.sortTime-b.sortTime);
    if(!matching.length)continue;
    const h=document.createElement('h3');h.textContent=new Intl.DateTimeFormat('en-GB',{dateStyle:'full',timeZone:'UTC'}).format(new Date(d*86400000));container.append(h);
    const list=document.createElement('ul');
    for(const e of matching){const li=document.createElement('li');const label=config.members[e.calendar].label;const title=['', 'Working', 'Working + on-call', 'Not working'][e.kind]||e.title;const time=e.allDay?'All day':e.startDay<d?'Continues':`${String(Math.floor(e.startSecond/3600)).padStart(2,'0')}:${String(Math.floor(e.startSecond/60)%60).padStart(2,'0')}`;li.textContent=`${time} — ${label}: ${title}`;list.append(li);}container.append(list);
  }
}
async function load(reason='refresh',force=false){
  if(!renderer)return;
  const run=++revision;controller?.abort();controller=new AbortController();const signal=controller.signal;
  setBusy(true);const current=now();renderer.clock(current.day,current.second);
  const target={anchor:renderer.anchor,month:renderer.month,...renderer.range};say(config.source==='demo'?'Preparing invented demo events…':'Loading selected calendars…');
  try{
    let events;
    if(config.source==='demo')events=demoEvents(target.first,target.count,config);
    else events=await googleSource.events(config,target.first,target.count,signal);
    if(run!==revision)return;
    staleData=false;renderer.events(events);await paint(force,run,signal);
    if(run!==revision)return;
    lastGood={...target,events,source:config.source,today:current.day};lastPoll=Date.now();displayAgenda(events,target.first,target.count);
    say(config.source==='demo'?'Invented events · no Google connection required':`Synced ${new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})} · read-only · reconnect when prompted`);
    if(startupWarning){say(startupWarning,true);startupWarning='';}
  }catch(error){
    if(run!==revision)return;
    staleData=true;
    if(lastGood){renderer.select(lastGood.anchor,lastGood.month);renderer.events(lastGood.events);
      try{await paint(false,run,signal,true);}catch{/* Keep the previously drawn canvas on a cancelled render. */}
    }else{renderer.events([]);renderer.render('unavailable','NOT LOADED / Connect Google or choose Demo in Settings',true);}
    if(run!==revision)return;
    lastPoll=Date.now();if(lastGood)lastGood.today=current.day;
    say((error.name==='AbortError'?'Request timed out.':error.message)+(lastGood?' Showing the last loaded period.':''),true);
    if(error instanceof ReconnectError)$('connect').textContent='Reconnect Google';
  }finally{if(run===revision){setBusy(false);updateLabels();}}
}
async function helpPaint(){
  if(busy||!renderer)return;
  const run=++revision;controller?.abort();controller=new AbortController();setBusy(true);
  try{await paint(true,run,controller.signal);if(run===revision)say(renderer.helpOpen?'Button help is visible. Press again to act.':'Button help hidden.');}
  catch(e){if(run===revision&&e.name!=='AbortError')say(e.message,true);}
  finally{if(run===revision)setBusy(false);}
}
async function navigate(index){
  if(!renderer||busy||dialog.open)return;
  const result=renderer.press(performance.now(),busy);
  if(result===1)return helpPaint();if(result!==2)return;
  if(index===0||index===3)followToday=false;else if(index===1)followToday=true;
  renderer.navigate(index);await load('navigation');
}
function inputLabel(text,input){const label=document.createElement('label');label.textContent=text;label.append(input);return label;}
function field(tag,value,name){const el=document.createElement(tag);el.dataset.field=name;el.value=value;return el;}
function option(value,label){const o=document.createElement('option');o.value=value;o.textContent=label;return o;}
function readMembers(){return [...$('members').children].map(card=>{const get=n=>card.querySelector(`[data-field="${n}"]`);return {key:card.dataset.key,label:get('label').value,badge:get('badge').value,colour:get('colour').value,calendarId:get('calendarId').value,maskTitles:get('maskTitles').checked};});}
function drawMembers(){
  const root=$('members');root.replaceChildren();
  for(const m of draft.members){
    const card=document.createElement('div');card.className='member-card';card.dataset.key=m.key;
    const grid=document.createElement('div');grid.className='member-grid';
    const label=field('input',m.label,'label');label.maxLength=40;
    const badge=field('input',m.badge,'badge');badge.maxLength=2;
    const colour=field('select',m.colour,'colour');for(const value of ['blue','green','red','yellow','black'])colour.append(option(value,value[0].toUpperCase()+value.slice(1)));colour.value=m.colour;
    const remove=document.createElement('button');remove.type='button';remove.className='remove-member';remove.textContent='−';remove.setAttribute('aria-label',`Remove ${m.label}`);remove.disabled=draft.members.length===1;
    remove.onclick=()=>{draft.members=readMembers().filter(member=>member.key!==m.key);if(draft.rotaMember===m.key)draft.rotaMember='';drawMembers();};
    grid.append(inputLabel('Display name',label),inputLabel('Badge',badge),inputLabel('Colour',colour),remove);
    const extra=document.createElement('div');extra.className='member-extra';
    const cal=field('select',m.calendarId,'calendarId');cal.append(option('','Not linked'));
    for(const entry of availableCalendars)cal.append(option(entry.id,entry.label));
    if(m.calendarId&&!availableCalendars.some(c=>c.id===m.calendarId))cal.append(option(m.calendarId,'Saved calendar (connect to load names)'));
    cal.value=m.calendarId;
    const mask=field('input','', 'maskTitles');mask.type='checkbox';mask.checked=m.maskTitles;
    const maskLabel=inputLabel('Only show Busy',mask);maskLabel.className='check-inline';
    extra.append(inputLabel('Google calendar · connect below to choose',cal),maskLabel);card.append(grid,extra);root.append(card);
  }
  const rota=form.elements.rotaMember;const selected=draft.rotaMember;rota.replaceChildren(option('','No rota band'));
  for(const m of draft.members)rota.append(option(m.key,m.label));rota.value=selected;$('add-member').disabled=draft.members.length>=6;
}
function fillForm(c){draft=structuredClone(c);for(const [key,value] of Object.entries(c)){const el=form.elements[key];if(!el||key==='members'||key==='rotaMember')continue;if(el.type==='checkbox')el.checked=value;else el.value=String(value);}
  drawMembers();form.elements.anchor.value=renderer?isoDay(renderer.anchor):isoDay(now().day);$('origin').textContent=location.origin;note('');
}
function readForm(){const value=structuredClone(draft);value.members=readMembers();for(const key of ['title','timezone','defaultView','clientId','source','rotaMember'])value[key]=form.elements[key].value;
  for(const key of ['weekStart','helpSeconds','refreshSeconds','pollMinutes'])value[key]=Number(form.elements[key].value);
  value.persistentLabels=form.elements.persistentLabels.value==='true';for(const key of ['paperPalette','maskPrivate','deduplicate'])value[key]=form.elements[key].checked;return validateConfig(value);
}
function openSettings(){fillForm(config);dialog.showModal();}
function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}
async function prepare(){try{note('Loading Google sign-in…');await loadGoogleLibrary();note('Ready. Tap “Sign in & load calendar choices” to continue.');}catch(e){note(e.message);}}
async function connectFromDialog(){
  try{
    if(!globalThis.google?.accounts?.oauth2){note('Tap “Prepare Google sign-in” first, then tap this button again.');return;}
    const c=readForm();const pending=googleSource.connect(c.clientId);note('Complete Google sign-in in its popup.');await pending;connectedClient=c.clientId;
    availableCalendars=await googleSource.calendars();draft=c;draft.members=readMembers();draft.source='google';form.elements.source.value='google';drawMembers();note('Select a Google calendar for each person, then Apply settings.');
  }catch(e){note(e.message);}
}
async function connectFromHeader(){
  if(!config.clientId){openSettings();note('Enter your Web application OAuth client ID, then prepare sign-in.');return;}
  if(!globalThis.google?.accounts?.oauth2){try{await loadGoogleLibrary();$('connect').textContent='Sign in to Google';say('Google sign-in ready. Tap Sign in to Google to continue.');}catch(e){say(e.message,true);}return;}
  try{
    const pending=googleSource.connect(config.clientId);await pending;connectedClient=config.clientId;
    if(config.source==='google'&&config.members.every(m=>m.calendarId))await load('connect');
    else{availableCalendars=await googleSource.calendars();openSettings();form.elements.source.value='google';note('Choose the calendars to display, then Apply settings.');}
    $('connect').textContent='Connect Google';
  }catch(e){say(e.message,true);}
}
async function keepAwake(){
  if(!wantWake||document.visibilityState!=='visible')return;
  try{if(!navigator.wakeLock)throw new Error('Screen wake lock needs a supported browser and HTTPS.');wake=await navigator.wakeLock.request('screen');$('wake').textContent='Awake · turn off';wake.addEventListener('release',()=>{$('wake').textContent=wantWake?'Awake paused':'Keep awake';});}
  catch(e){wantWake=false;$('wake').textContent='Keep awake';say(e.message,true);}
}
$('settings-button').onclick=openSettings;
$('close-settings').onclick=$('cancel-settings').onclick=()=>dialog.close();
$('device-timezone').onclick=()=>{form.elements.timezone.value=Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC';};
$('add-member').onclick=()=>{draft.members=readMembers();draft.rotaMember=form.elements.rotaMember.value;if(draft.members.length>=6)return;let index=1;while(draft.members.some(m=>m.key===`member-${index}`||m.badge===String(index)))++index;draft.members.push({key:`member-${index}`,label:`Calendar ${index}`,badge:String(index),colour:'black',calendarId:'',maskTitles:false});drawMembers();};
form.elements.rotaMember.onchange=()=>{draft.rotaMember=form.elements.rotaMember.value;};
form.onsubmit=async e=>{
  e.preventDefault();try{
    const updated=readForm(),anchor=ordinal(form.elements.anchor.value);
    if(updated.source==='google'&&updated.members.some(m=>!m.calendarId))throw new Error('Choose a Google calendar for every displayed person, or keep the source on Demo.');
    config=saveConfig(updated);if(connectedClient&&connectedClient!==config.clientId){googleSource.disconnect();connectedClient='';availableCalendars=[];}
    ++revision;controller?.abort();lastGood=null;lastHash='';renderer.configure(config);renderer.select(anchor,config.defaultView==='month');followToday=anchor===now().day;dialog.close();await load('settings',true);
  }catch(error){note(error.message);}
};
$('prepare-google').onclick=prepare;$('choose-google').onclick=connectFromDialog;$('connect').onclick=connectFromHeader;
$('export-settings').onclick=()=>{try{const c=readForm();download(new Blob([JSON.stringify(c,null,2)+'\n'],{type:'application/json'}),'paperweek-settings.private.json');note('This private file contains names and calendar IDs. Keep it out of public repositories.');}catch(e){note(e.message);}};
$('import-settings').onchange=async event=>{try{const f=event.target.files[0];if(!f)return;if(f.size>65536)throw new Error('Settings file is too large.');const c=validateConfig(JSON.parse(await f.text()));fillForm(c);note('Imported into the form only. Review and Apply settings to save.');}catch(e){note(e.message);}finally{event.target.value='';}};
$('forget').onclick=async()=>{if(!confirm('Remove this browser’s saved names and calendar IDs, and disconnect locally? This does not delete Google events or revoke Google consent.'))return;++revision;controller?.abort();googleSource.disconnect();connectedClient='';availableCalendars=[];try{clearConfig();}catch{}config=defaults();lastGood=null;lastHash='';renderer.configure(config);renderer.select(now().day,true);followToday=true;fillForm(config);dialog.close();await load('reset',true);};
$('revoke').onclick=async()=>{if(!googleSource.connected){note('There is no active token. Remove Paperweek access in your Google Account’s third-party connections to revoke older consent.');return;}if(!confirm('Revoke this app’s Google permissions? This does not delete any calendar events.'))return;try{++revision;controller?.abort();setBusy(false);await googleSource.revoke();connectedClient='';availableCalendars=[];lastGood=null;renderer.events([]);renderer.render('unavailable','GOOGLE DISCONNECTED',true);$('agenda-text').replaceChildren();note('Google access revoked.');say('Google access revoked.',true);}catch{note('Unable to confirm revocation. Remove the app in Google Account settings.');}};
$('export-screen').onclick=()=>{if(config.source==='google'&&!confirm('This image may contain private calendar information. Save it locally?'))return;$('calendar').toBlob(blob=>{if(blob)download(blob,'paperweek-display.private.png');},'image/png');};
$('refresh').onclick=()=>load('manual');
$('wake').onclick=async()=>{wantWake=!wantWake;if(wantWake)await keepAwake();else{await wake?.release();wake=null;$('wake').textContent='Keep awake';}};
setupDisplay(navigate,say);showBuild();
for(const b of document.querySelectorAll('[data-nav]'))b.onclick=()=>navigate(Number(b.dataset.nav));
document.addEventListener('keydown',e=>{if(dialog.open||['INPUT','SELECT','TEXTAREA','BUTTON'].includes(document.activeElement?.tagName))return;const map={ArrowLeft:0,ArrowRight:3,t:1,T:1,m:2,M:2,'1':0,'2':1,'3':2,'4':3};if(Object.hasOwn(map,e.key)){e.preventDefault();navigate(map[e.key]);}});
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){keepAwake();if(renderer&&!busy)load('resume');}});
window.addEventListener('online',()=>{if(renderer&&!busy)load('online');});
window.addEventListener('offline',()=>{if(config.source==='google'){staleData=true;say('Offline. Previously loaded data remains in memory only; reload requires a new connection.',true);}});
setInterval(()=>{
  if(!renderer||busy||dialog.open||document.visibilityState!=='visible')return;
  if(renderer.expire(performance.now(),busy)){helpPaint();return;}
  const current=now();if(lastGood&&(current.day!==lastGood.today||Date.now()-lastPoll>config.pollMinutes*60000)){
    if(current.day!==lastGood.today&&followToday)renderer.select(current.day,renderer.month);
    // Only update the date once; the model hash suppresses unchanged frame redraws.
    lastGood.today=current.day;load('poll');
  }
},1000);
try{
  renderer=await createRenderer($('calendar'));$('engine-label').textContent=renderer.type;
  renderer.configure(config);renderer.select(now().day,config.defaultView==='month');await load('start',true);
  if(lastGood)lastGood.today=now().day;
  if('serviceWorker'in navigator&&isSecureContext)navigator.serviceWorker.register('./sw.js').catch(()=>{});
  document.documentElement.dataset.ready='true';
}catch(e){say(`Unable to start: ${e.message} Use the supplied web build over HTTP/HTTPS, not a file:// URL.`,true);document.documentElement.dataset.ready='error';}
