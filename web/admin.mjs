import {createSchoolEditor} from './school-editor.mjs';
import {showBuild} from './display-controls.mjs';
import {defaults,validateConfig} from './config.mjs';
import {api,clearOffline} from './backend-client.mjs';
const $=id=>document.getElementById(id),form=$('config-form');
let config=defaults(),revision=1,calendars=[],logged=false,dirty=false;
let sources=[],editingSource=null,sourceDirty=false;
const sourceForm=$('source-form');
const schoolEditor=createSchoolEditor($('school-editor'),readMembers,()=>{dirty=true;$('save-state').textContent='Unsaved school changes';},()=>form.elements.timezone.value);
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
    remove.onclick=()=>{if(schoolEditor.hasMember(m.key))return notice('Remove this person’s school profile before removing the person.',true);if(sources.some(s=>s.member===m.key)&&!confirm(`Remove ${m.label}? Saving the shared settings will also remove their attached sources and local cache, but never provider events.`))return;config.members=readMembers().filter(x=>x.key!==m.key);if(config.rotaMember===m.key)config.rotaMember='';dirty=true;drawMembers();};
    grid.append(labelled('Display name',name),labelled('Badge',badge),labelled('Colour',colour),remove);
    const extra=element('div');extra.className='member-extra';
    const calendar=field('select','calendarId',m.calendarId);calendar.append(opt('','No primary Google calendar'));
    for(const c of calendars)calendar.append(opt(c.id,c.label));
    if(m.calendarId&&!calendars.some(c=>c.id===m.calendarId))calendar.append(opt(m.calendarId,'Saved mapping · load choices to check'));
    calendar.value=m.calendarId;
    const mask=field('input','maskTitles','');mask.type='checkbox';mask.checked=m.maskTitles;
    const maskLabel=labelled('Only show Busy',mask);maskLabel.className='check-inline';
    extra.append(labelled('Primary Google calendar · optional',calendar),maskLabel);
    const attach=element('button','Add source for this person');attach.type='button';attach.className='attach-source';
    attach.onclick=()=>{if(dirty)return notice('Save shared settings first, then add a source for this person.',true);if(sourceDirty&&!confirm('Discard unsaved source changes?'))return;editSource(null);sourceForm.elements.member.value=m.key;$('source-heading').scrollIntoView({block:'center',behavior:'smooth'});};
    card.append(grid,extra,attach);$('members').append(card);
  }
  const rota=form.elements.rotaMember;rota.replaceChildren(opt('','No rota band'));
  for(const m of config.members)rota.append(opt(m.key,m.label));rota.value=config.rotaMember;
  $('add-member').disabled=config.members.length>=6;
  sourceSelectors();
}
function fill(c){config=structuredClone(c);for(const [key,value]of Object.entries(c)){const el=form.elements[key];if(!el||key==='members'||key==='rotaMember')continue;if(el.type==='checkbox')el.checked=value;else el.value=String(value);}drawMembers();schoolEditor.set(c.school||[]);dirty=false;$('save-state').textContent='';}
function read(){const c=structuredClone(config);c.members=readMembers();c.clientId='';
  for(const key of ['title','timezone','source','rotaMember','defaultView'])c[key]=form.elements[key].value;
  for(const key of ['pollMinutes','weekStart','helpSeconds','refreshSeconds'])c[key]=Number(form.elements[key].value);
  for(const key of ['paperPalette','maskPrivate','deduplicate'])c[key]=form.elements[key].checked;
  c.persistentLabels=form.elements.persistentLabels.value==='true';c.school=schoolEditor.read(c.members);return validateConfig(c);
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
    const table=element('table');const head=element('tr');for(const text of ['Person','Source','Month','Last good sync','Status'])head.append(element('th',text));table.append(head);
    for(const w of status.windows){const row=element('tr');for(const text of [names.get(w.member)||w.member,w.source||'Primary Google',w.month.slice(0,7),when(w.success),w.error||(w.warnings?.length?w.warnings.join(' '):!w.success?'Queued / not loaded':'Saved')])row.append(element('td',text));table.append(row);}
    $('windows').replaceChildren(table);
  }catch(e){if(e.status===401){logged=false;$('login-panel').hidden=false;$('admin-content').hidden=true;$('logout').hidden=true;}notice(e.message,true);}
}
async function loadChoices(){
  const result=await api('/api/admin/calendars');config.members=readMembers();config.rotaMember=form.elements.rotaMember.value;calendars=result.calendars;drawMembers();
  $('calendar-count').textContent=`${calendars.length} readable calendar${calendars.length===1?'':'s'} loaded. Primary mappings are optional; you can also attach additional Google sources below.`;
}
async function initialise(){
  const who=await api('/api/session');if(who.role!=='admin')throw new Error('This browser is paired as a display. Sign in with the administrator password to change shared settings.');
  logged=true;$('login-panel').hidden=true;$('admin-content').hidden=false;$('logout').hidden=false;
  const record=await api('/api/admin/config');revision=record.revision;fill(record.config);await refreshSources();editSource(null);notice('');await health();
  const status=await api('/api/admin/status');if(status.connection==='connected'){try{await loadChoices();}catch(e){notice(e.message,true);}}
}
$('login-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/admin/login',{method:'POST',body:{password:$('password').value}});$('password').value='';await initialise();}catch(e){notice(e.message,true);}};
$('logout').onclick=async()=>{try{await api('/api/logout',{method:'POST'});clearOffline();location.reload();}catch(e){notice(e.message,true);}};
$('google-connect').onclick=async()=>{if((dirty||sourceDirty)&&!confirm('Unsaved settings will be lost during Google sign-in. Continue?'))return;try{const result=await api('/api/admin/google/connect',{method:'POST'});location.assign(result.url);}catch(e){notice(e.message,true);}};
$('load-calendars').onclick=async()=>{try{await loadChoices();notice('Calendar choices loaded. Choose primary Google calendars for the people below, then save. Additional sources belong in the separate source section.');}catch(e){notice(e.message,true);}};
$('sync-now').onclick=async()=>{try{await api('/api/admin/sync',{method:'POST'});notice('Synchronisation queued. The worker will run shortly.');await health();}catch(e){notice(e.message,true);}};
$('google-disconnect').onclick=async()=>{if(!confirm('Remove server Google credentials and Google cached events? Independent iCalendar sources are retained. This does not delete anything in Google Calendar.'))return;try{await api('/api/admin/google/disconnect',{method:'POST'});clearOffline();calendars=[];notice('Disconnected locally. Remove consent in your Google Account to revoke the provider grant.');await health();}catch(e){notice(e.message,true);}};
form.addEventListener('input',()=>{dirty=true;$('save-state').textContent='Unsaved changes';});
form.elements.rotaMember.onchange=()=>{config.rotaMember=form.elements.rotaMember.value;};
$('add-member').onclick=()=>{config.members=readMembers();if(config.members.length>=6)return;let n=1;while(config.members.some(m=>m.key===`member-${n}`||m.badge===String(n)))++n;config.members.push({key:`member-${n}`,label:`Person ${n}`,badge:String(n),colour:'black',calendarId:'',maskTitles:false});dirty=true;drawMembers();};
form.onsubmit=async e=>{e.preventDefault();try{const c=read();const saved=await api('/api/admin/config',{method:'PUT',body:{revision,config:c}});revision=saved.revision;fill(saved.config);clearOffline();$('save-state').textContent='Saved · displays pick this up on their next check';notice('Shared settings saved. Live calendar synchronisation runs in the server.');await refreshSources();await health();}catch(e){$('save-state').textContent=e.message;notice(e.message,true);}};
$('import-settings').onchange=async e=>{try{const f=e.target.files[0];if(!f)return;if(f.size>65536)throw new Error('Settings file is too large.');const c=validateConfig(JSON.parse(await f.text()));c.clientId='';fill(c);dirty=true;$('save-state').textContent='Imported into the form · not saved yet';notice('Imported. Check calendar mappings and timezone, then save.');}catch(e){notice(e.message,true);}finally{e.target.value='';}};
$('export-settings').onclick=()=>{try{const c=read(),url=URL.createObjectURL(new Blob([JSON.stringify(c,null,2)],{type:'application/json'}));const a=element('a');a.href=url;a.download='paperweek-server-settings.private.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}catch(e){notice(e.message,true);}};
$('pair-create').onsubmit=async e=>{e.preventDefault();try{const result=await api('/api/admin/pairings',{method:'POST',body:{label:$('device-label').value,days:Number($('device-days').value)}});$('pair-code-output').textContent=result.code;notice(`Enter ${result.code} on the tablet within ten minutes. It can be used once.`);}catch(e){notice(e.message,true);}};

function sourceSelectors(){
  const owner=sourceForm.elements.member,selected=owner.value;
  owner.replaceChildren(...config.members.map(m=>opt(m.key,m.label)));
  owner.value=config.members.some(m=>m.key===selected)?selected:config.members[0]?.key||'';
  const google=sourceForm.elements.calendarId,chosen=google.value;
  google.replaceChildren(opt('','Select a loaded Google calendar'),...calendars.map(c=>opt(c.id,c.label)));
  const saved=editingSource?.calendarId;
  if(saved&&!calendars.some(c=>c.id===saved))google.append(opt(saved,'Saved Google source · load choices to check'));
  google.value=chosen||saved||'';
}
function showSourceFields(){
  const isIcal=sourceForm.elements.kind.value==='ical',rota=sourceForm.elements.mode.value==='rota';
  $('source-url-field').hidden=!isIcal;$('source-url-hint').hidden=!isIcal;$('source-google-field').hidden=isIcal;
  $('rota-options').hidden=!rota;
  for(const input of $('rota-rules').querySelectorAll('input,select,button')) input.disabled=!rota;
}
function addRule(rule={field:'title',match:'equals',text:'',action:'work'}){
  const row=element('div');row.className='rota-rule';
  for(const [key,title,choices]of [
    ['field','Match in',[['title','Title'],['category','Category']]],
    ['match','Match type',[['equals','Equals'],['contains','Contains']]],
    ['action','Interpret as',[['work','Working'],['oncall','On-call + working'],['off','Not working'],['ignore','Ignore']]],
  ]){const select=field('select',key,rule[key]);for(const [value,label]of choices)select.append(opt(value,label));select.value=rule[key];row.append(labelled(title,select));}
  const needle=field('input','text',rule.text);needle.maxLength=120;needle.required=true;needle.placeholder='Exact shift code or phrase';row.insertBefore(labelled('Text',needle),row.children[2]);
  const remove=element('button','Remove');remove.type='button';remove.onclick=()=>{row.remove();sourceDirty=true;};row.append(remove);$('rota-rules').append(row);
}
function editSource(source){
  editingSource=source?structuredClone(source):null;sourceForm.reset();$('rota-rules').replaceChildren();
  const values=source||{label:'',member:config.members[0]?.key||'',kind:'ical',mode:'events',url:'',calendarId:'',timezone:config.timezone,pollMinutes:30,defaultRota:'unknown',enabled:false,rules:[]};
  sourceSelectors();
  for(const [key,val]of Object.entries(values)){const el=sourceForm.elements[key];if(!el||key==='url')continue;if(el.type==='checkbox')el.checked=val;else el.value=String(val);}
  sourceForm.elements.url.value='';sourceForm.elements.kind.disabled=Boolean(source);
  sourceForm.elements.url.placeholder=source?.hasUrl?'Saved securely · leave blank to retain or paste a replacement':'https://… or webcal://…';
  for(const rule of values.rules)addRule(rule);
  $('source-heading').textContent=source?'Edit source: '+source.label:'New source';$('preview-source').disabled=!source;
  $('source-state').textContent='';$('source-preview-results').replaceChildren();$('source-preview-state').textContent='Preview uses the saved source and rules. No provider events are changed.';
  sourceDirty=false;showSourceFields();
}
function readSource(){
  const f=sourceForm.elements,kind=f.kind.value;
  return {label:f.label.value.trim(),member:f.member.value,kind,calendarId:kind==='google'?f.calendarId.value:'',url:kind==='ical'?f.url.value.trim():'',
    timezone:f.timezone.value.trim(),pollMinutes:Number(f.pollMinutes.value),mode:f.mode.value,defaultRota:f.defaultRota.value,emptyDaysOff:f.emptyDaysOff.checked,enabled:f.enabled.checked,
    rules:f.mode.value==='rota'?[...$('rota-rules').children].map(row=>Object.fromEntries(['field','match','text','action'].map(k=>[k,row.querySelector(`[data-field="${k}"]`).value]))):[]};
}
async function refreshSources(){
  const result=await api('/api/admin/sources');sources=result.sources;
  const record=await api('/api/admin/config');
  // Keep the optimistic revision paired with the actual shared config. Never
  // adopt another administrator's revision while retaining stale form values.
  if(!dirty){revision=record.revision;fill(record.config);}
  $('sources-list').replaceChildren();
  for(const s of sources){const row=element('div');row.className='source-card';
    const owner=config.members.find(m=>m.key===s.member)?.label||'Removed person';const info=element('div');
    info.append(element('strong',s.label),element('p',`${owner} · ${s.kind==='ical'?'iCalendar':'Google'} · ${s.mode==='rota'?'Rota band':'Appointments'} · ${s.enabled?'Enabled':'Paused'} · every ${s.pollMinutes} min`));
    if(s.mode==='rota'&&s.member!==config.rotaMember)info.append(element('p','Inactive: this person is not selected for the rota band.'));
    const edit=element('button','Edit / preview');edit.type='button';edit.onclick=()=>{if(sourceDirty&&!confirm('Discard unsaved source edits?'))return;editSource(s);$('source-heading').scrollIntoView({block:'center',behavior:'smooth'});};
    const remove=element('button','Delete');remove.type='button';remove.onclick=async()=>{if(dirty) return notice('Save shared settings before changing sources.',true);if(!confirm(`Remove ${s.label} and its local cache? Provider events are not deleted.`))return;
      try{await api('/api/admin/sources/'+s.id,{method:'DELETE',body:{revision:s.revision}});if(editingSource?.id===s.id)editSource(null);await refreshSources();await health();}catch(e){notice(e.message,true);}};
    const controls=element('div');controls.className='row';controls.append(edit,remove);row.append(info,controls);$('sources-list').append(row);
  }
  if(!sources.length)$('sources-list').append(element('p','No additional sources yet. Your primary Google mappings above still work.'));
}
sourceForm.addEventListener('input',()=>{sourceDirty=true;$('source-state').textContent='Unsaved source changes';});
sourceForm.elements.kind.onchange=showSourceFields;sourceForm.elements.mode.onchange=showSourceFields;
$('add-rota-rule').onclick=()=>{if($('rota-rules').children.length>=20)return;addRule();sourceDirty=true;};
$('new-source').onclick=$('cancel-source').onclick=()=>{if(sourceDirty&&!confirm('Discard unsaved source changes?'))return;editSource(null);};
sourceForm.onsubmit=async e=>{e.preventDefault();try{
  if(dirty)throw new Error('Save the shared layout and people before saving this source.');
  const source=readSource(),editing=editingSource;
  const result=await api('/api/admin/sources'+(editing?'/'+editing.id:''),{method:editing?'PUT':'POST',body:editing?{revision:editing.revision,source}:source});
  sourceForm.elements.url.value='';editSource(result.source);await refreshSources();clearOffline();
  $('source-state').textContent='Saved '+(result.source.enabled?'and enabled.':'but paused. Preview before enabling.');notice('Source saved securely. No events were copied into Google.');await health();
}catch(e){$('source-state').textContent=e.message;notice(e.message,true);}};
$('source-preview-month').value=new Date().toISOString().slice(0,7);
$('preview-source').onclick=async()=>{if(!editingSource)return;if(sourceDirty)return notice('Save the source before previewing its rules.',true);
  const button=$('preview-source');button.disabled=true;$('source-preview-state').textContent='Fetching and checking this month. The preview may take up to 40 seconds…';$('source-preview-results').replaceChildren();
  try{const first=$('source-preview-month').value+'-01';const month=new Date(first+'T12:00:00Z');const days=new Date(Date.UTC(month.getUTCFullYear(),month.getUTCMonth()+1,0)).getUTCDate();
    const r=await api('/api/admin/sources/'+editingSource.id+'/preview',{method:'POST',body:{first,days},timeout:60000});
    $('source-preview-state').textContent=`${r.total} occurrence(s). ${Object.entries(r.counts).map(([k,v])=>`${k}: ${v}`).join(' · ')}. ${r.warnings.join(' ')}${r.truncated?' First 100 shown.':''}`;
    const table=element('table'),head=element('tr');for(const t of ['Original title','Categories','Start','End','Interpretation'])head.append(element('th',t));table.append(head);
    const time=v=>v.date||new Date(v.dateTime).toLocaleString(undefined,{timeZone:config.timezone});
    for(const item of r.items){const row=element('tr');for(const t of [item.title,(item.categories||[]).join(', '),time(item.start),time(item.end),item.detail||item.interpretation])row.append(element('td',t));table.append(row);}
    $('source-preview-results').replaceChildren(table);
  }catch(e){$('source-preview-state').textContent=e.message;}finally{button.disabled=!editingSource;}
};
window.addEventListener('beforeunload',e=>{if(dirty||sourceDirty){e.preventDefault();e.returnValue='';}});
if('serviceWorker'in navigator&&isSecureContext)navigator.serviceWorker.register('/server-sw.js',{scope:'/'}).catch(()=>{});
try{await initialise();}catch(e){if(e.status!==401)notice(e.message,true);}
setInterval(health,15000);

showBuild();
$('device-timezone').onclick=()=>{form.elements.timezone.value=Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC';dirty=true;$('save-state').textContent='Timezone changed · save shared settings to apply';};
