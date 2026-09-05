import {defaults,validateConfig} from './config.mjs';
import {api,clearOffline} from './backend-client.mjs';
const $=id=>document.getElementById(id),form=$('config-form');
let config=defaults(),revision=1,calendars=[],logged=false,dirty=false;
function notice(message,error=false){$('notice').textContent=message;$('notice').classList.toggle('error',error);}
function element(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
function opt(value,label){const e=element('option',label);e.value=value;return e;}
function field(tag,name,value){const e=element(tag);e.dataset.field=name;e.value=value;return e;}
function labelled(text,input){const e=element('label',text);e.append(input);return e;}
function readMembers(){return [...$('members').children].map(card=>{const get=n=>card.querySelector(`[data-field="${n}"]`);return {key:card.dataset.key,label:get('label').value,badge:get('badge').value.toUpperCase(),colour:get('colour').value,calendarId:get('calendarId').value,maskTitles:get('maskTitles').checked};});}
function drawMembers(){
  $('members').replaceChildren();
  for(const m of config.members){
    const card=element('div');card.className='member-card';card.dataset.key=m.key;
    const grid=element('div');grid.className='member-grid';
    const name=field('input','label',m.label);name.maxLength=40;name.required=true;
    const badge=field('input','badge',m.badge);badge.maxLength=2;badge.required=true;
    const colour=field('select','colour',m.colour);for(const c of ['blue','green','red','yellow','black'])colour.append(opt(c,c));colour.value=m.colour;
    const remove=element('button','−');remove.type='button';remove.className='remove-member';remove.setAttribute('aria-label',`Remove ${m.label}`);remove.disabled=config.members.length===1;
    remove.onclick=()=>{config.members=readMembers().filter(x=>x.key!==m.key);if(config.rotaMember===m.key)config.rotaMember='';dirty=true;drawMembers();};
    grid.append(labelled('Display name',name),labelled('Badge',badge),labelled('Colour',colour),remove);
    const extra=element('div');extra.className='member-extra';
    const calendar=field('select','calendarId',m.calendarId);calendar.append(opt('','Not linked'));
    for(const c of calendars)calendar.append(opt(c.id,c.label));
    if(m.calendarId&&!calendars.some(c=>c.id===m.calendarId))calendar.append(opt(m.calendarId,'Saved mapping · load choices to check'));
    calendar.value=m.calendarId;
    const mask=field('input','maskTitles','');mask.type='checkbox';mask.checked=m.maskTitles;
    const maskLabel=labelled('Only show Busy',mask);maskLabel.className='check-inline';
    extra.append(labelled('Google calendar for this person',calendar),maskLabel);card.append(grid,extra);$('members').append(card);
  }
  const rota=form.elements.rotaMember;rota.replaceChildren(opt('','No rota band'));
  for(const m of config.members)rota.append(opt(m.key,m.label));rota.value=config.rotaMember;
  $('add-member').disabled=config.members.length>=6;
}
function fill(c){config=structuredClone(c);for(const [key,value]of Object.entries(c)){const el=form.elements[key];if(!el||key==='members'||key==='rotaMember')continue;if(el.type==='checkbox')el.checked=value;else el.value=String(value);}drawMembers();dirty=false;$('save-state').textContent='';}
function read(){const c=structuredClone(config);c.members=readMembers();c.clientId='';
  for(const key of ['title','timezone','source','rotaMember','defaultView'])c[key]=form.elements[key].value;
  for(const key of ['pollMinutes','weekStart','helpSeconds','refreshSeconds'])c[key]=Number(form.elements[key].value);
  for(const key of ['paperPalette','maskPrivate','deduplicate'])c[key]=form.elements[key].checked;
  c.persistentLabels=form.elements.persistentLabels.value==='true';return validateConfig(c);
}
function when(t){return t?new Date(t*1000).toLocaleString():'Never';}
async function health(){
  if(!logged)return;
  try{const [status,devices]=await Promise.all([api('/api/admin/status'),api('/api/admin/devices')]);
    $('google-state').textContent=status.connection.replaceAll('_',' ');
    $('sync-state').textContent=status.schedulerRunning?`Every ${status.pollMinutes} min`:'Worker not running';
    $('device-count').textContent=`${devices.length} paired display${devices.length===1?'':'s'}`;
    $('callback').textContent=status.callbackUrl;
    $('oauth-config-hint').textContent=status.oauthConfigured?'Server credentials are configured. Register the exact callback below in the Web application client.':'Google client credentials are missing. Run the private server configuration tool, then recreate the container.';
    $('google-connect').disabled=!status.oauthConfigured;
    if(status.notice)notice(status.notice,true);
    $('devices').replaceChildren();
    for(const d of devices){const row=element('div');row.className='device-row';
      const description=element('div');description.append(element('strong',d.label),element('p',`Last seen ${when(d.lastSeen)} · expires ${when(d.expires)}`));
      const revoke=element('button','Revoke');revoke.onclick=async()=>{if(!confirm(`Revoke read-only access for ${d.label}?`))return;try{await api(`/api/admin/devices/${d.id}`,{method:'DELETE'});await health();}catch(e){notice(e.message,true);}};
      row.append(description,revoke);$('devices').append(row);
    }
    const names=new Map(config.members.map(m=>[m.key,m.label]));
    const table=element('table');const head=element('tr');for(const text of ['Calendar','Month','Last good sync','Status'])head.append(element('th',text));table.append(head);
    for(const w of status.windows){const row=element('tr');for(const text of [names.get(w.member)||w.member,w.month.slice(0,7),when(w.success),w.error||(!w.success?'Queued / not loaded':'Saved')])row.append(element('td',text));table.append(row);}
    $('windows').replaceChildren(table);
  }catch(e){if(e.status===401){logged=false;$('login-panel').hidden=false;$('admin-content').hidden=true;$('logout').hidden=true;}notice(e.message,true);}
}
async function loadChoices(){
  const result=await api('/api/admin/calendars');config.members=readMembers();config.rotaMember=form.elements.rotaMember.value;calendars=result.calendars;drawMembers();
  $('calendar-count').textContent=`${calendars.length} readable calendar${calendars.length===1?'':'s'} loaded. Select one on each person's card.`;
}
async function initialise(){
  const who=await api('/api/session');if(who.role!=='admin')throw new Error('This browser is paired as a display. Sign in with the administrator password to change shared settings.');
  logged=true;$('login-panel').hidden=true;$('admin-content').hidden=false;$('logout').hidden=false;
  const record=await api('/api/admin/config');revision=record.revision;fill(record.config);notice('');await health();
  const status=await api('/api/admin/status');if(status.connection==='connected'){try{await loadChoices();}catch(e){notice(e.message,true);}}
}
$('login-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/admin/login',{method:'POST',body:{password:$('password').value}});$('password').value='';await initialise();}catch(e){notice(e.message,true);}};
$('logout').onclick=async()=>{try{await api('/api/logout',{method:'POST'});clearOffline();location.reload();}catch(e){notice(e.message,true);}};
$('google-connect').onclick=async()=>{if(dirty&&!confirm('Unsaved settings will be lost during Google sign-in. Continue?'))return;try{const result=await api('/api/admin/google/connect',{method:'POST'});location.assign(result.url);}catch(e){notice(e.message,true);}};
$('load-calendars').onclick=async()=>{try{await loadChoices();notice('Calendar choices loaded. Map each person below, then save.');}catch(e){notice(e.message,true);}};
$('sync-now').onclick=async()=>{try{await api('/api/admin/sync',{method:'POST'});notice('Synchronisation queued. The worker will run shortly.');await health();}catch(e){notice(e.message,true);}};
$('google-disconnect').onclick=async()=>{if(!confirm('Remove server Google credentials and cached events? This does not delete anything in Google Calendar.'))return;try{await api('/api/admin/google/disconnect',{method:'POST'});clearOffline();calendars=[];notice('Disconnected locally. Remove consent in your Google Account to revoke the provider grant.');await health();}catch(e){notice(e.message,true);}};
form.addEventListener('input',()=>{dirty=true;$('save-state').textContent='Unsaved changes';});
form.elements.rotaMember.onchange=()=>{config.rotaMember=form.elements.rotaMember.value;};
$('add-member').onclick=()=>{config.members=readMembers();if(config.members.length>=6)return;let n=1;while(config.members.some(m=>m.key===`member-${n}`||m.badge===String(n)))++n;config.members.push({key:`member-${n}`,label:`Calendar ${n}`,badge:String(n),colour:'black',calendarId:'',maskTitles:false});dirty=true;drawMembers();};
form.onsubmit=async e=>{e.preventDefault();try{const c=read();if(c.source==='google'&&c.members.some(m=>!m.calendarId))throw new Error('Map each person to a Google calendar first.');const saved=await api('/api/admin/config',{method:'PUT',body:{revision,config:c}});revision=saved.revision;fill(saved.config);clearOffline();$('save-state').textContent='Saved · displays pick this up on their next check';notice('Shared settings saved. Google synchronisation is running in the server.');await health();}catch(e){$('save-state').textContent=e.message;notice(e.message,true);}};
$('import-settings').onchange=async e=>{try{const f=e.target.files[0];if(!f)return;if(f.size>65536)throw new Error('Settings file is too large.');const c=validateConfig(JSON.parse(await f.text()));c.clientId='';fill(c);dirty=true;$('save-state').textContent='Imported into the form · not saved yet';notice('Imported. Check calendar mappings and timezone, then save.');}catch(e){notice(e.message,true);}finally{e.target.value='';}};
$('export-settings').onclick=()=>{try{const c=read(),url=URL.createObjectURL(new Blob([JSON.stringify(c,null,2)],{type:'application/json'}));const a=element('a');a.href=url;a.download='paperweek-server-settings.private.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}catch(e){notice(e.message,true);}};
$('pair-create').onsubmit=async e=>{e.preventDefault();try{const result=await api('/api/admin/pairings',{method:'POST',body:{label:$('device-label').value,days:Number($('device-days').value)}});$('pair-code-output').textContent=result.code;notice(`Enter ${result.code} on the tablet within ten minutes. It can be used once.`);}catch(e){notice(e.message,true);}};
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
if('serviceWorker'in navigator&&isSecureContext)navigator.serviceWorker.register('/server-sw.js',{scope:'/'}).catch(()=>{});
try{await initialise();}catch(e){if(e.status!==401)notice(e.message,true);}
setInterval(health,15000);
