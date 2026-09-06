import {createRenderer} from './renderer.mjs';
import {isoDay} from './dates.mjs';
import {schoolDay,UNIFORMS,snackLabel} from './school.mjs';
import {viewRange,moveAnchor,appointments,overlaps,eventTime,shiftDetails,dateLabel,ROTA,VIEWS} from './planner-model.mjs';
const PREF='paperweek.planner.v1';
export function readPlannerPreferences(storage=globalThis.localStorage) {
  try {
    const p=JSON.parse(storage.getItem(PREF)||'{}');
    return {view:VIEWS.includes(p.view)?p.view:null,school:p.school!==false,lessons:p.lessons===true,mono:p.mono===true};
  } catch { return {view:null,school:true,lessons:false,mono:false}; }
}
function node(tag,text,cls) {
  const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;
}
function button(text,handler,cls) { const b=node('button',text,cls);b.type='button';b.onclick=handler;return b; }
export class PlannerRenderer {
  constructor(core,root) {
    this.core=core;this.root=root;this.type=`Responsive browser · ${core.type}`;
    this.config=null;this._events=[];this._anchor=0;this.today=0;this.second=0;
    this.prefs=readPlannerPreferences();this.mode=this.prefs.view||'rolling';this.weekMode=this.mode==='week'?'week':'rolling';
    this.rotas=new Map();this.helpOpen=false;this.unavailable='';this.status='';this.stale=false;
    this.dialog=document.getElementById('day-dialog');
    document.getElementById('close-day').onclick=()=>this.dialog.close();
    this.dialog.addEventListener('close',()=>{this.openDay=null;});
    for (const name of ['school','lessons','mono']) {
      const b=document.getElementById('toggle-'+name);
      b.onclick=()=>{this.prefs[name]=!this.prefs[name];this.savePreferences();this.draw();};
    }
    this.updateControls();
  }
  savePreferences() {
    try { localStorage.setItem(PREF,JSON.stringify(this.prefs)); }
    catch { document.getElementById('message').textContent='Display preference changed for this session; browser storage is unavailable.'; }
  }
  updateControls() {
    document.getElementById('view-mode').value=this.mode;
    for (const name of ['school','lessons','mono']) {
      const b=document.getElementById('toggle-'+name);b.setAttribute('aria-pressed',String(this.prefs[name]));
    }
    document.body.classList.toggle('planner-mono',this.prefs.mono);
  }
  configure(config) { this.config=config;this.core.configure(config); }
  clock(day,second) { this.today=day;this.second=second;this.core.clock(day,second); }
  select(day,month) { this._anchor=day;this.mode=month?'month':this.weekMode;this.updateControls(); }
  setMode(mode,persist=true) {
    if (!VIEWS.includes(mode)) throw new Error('Unknown planner view.');
    this.mode=mode;if(mode!=='month')this.weekMode=mode;
    if (persist) { this.prefs.view=mode;this.savePreferences(); }
    this.updateControls();
  }
  get anchor() { return this._anchor; }
  get month() { return this.mode==='month'; }
  get range() { return viewRange(this.anchor,this.mode,this.config?.weekStart??1); }
  navigate(index) {
    if(index===0 || index===3)this._anchor=moveAnchor(this.anchor,this.month,index===0?-1:1);
    else if(index===1)this._anchor=this.today;
    else if(index===2)this.setMode(this.month?this.weekMode:'month');
  }
  events(events) { this.core.events(events);this._events=events;this.visibleEvents=appointments(events,this.config); }
  prepare(mode,status,stale=false) {
    this.unavailable='';this.status=status;this.stale=stale;
    const {first,count}=this.range;this.rotas.clear();
    // A rolling range can straddle two conventional C weeks. Build each once,
    // then read the existing tested rota state for the requested civil days.
    // No second JavaScript implementation of conflict/off/on-call decisions.
    const weeks=new Map();
    for(let d=first;d<first+count;d++) {
      const key=this.month?first:viewRange(d,'week',this.config.weekStart).first;
      if(!weeks.has(key))weeks.set(key,[]);weeks.get(key).push(d);
    }
    for(const days of weeks.values()) {
      this.core.select(this.month?this.anchor:days[0],this.month);
      this.core.prepare(mode,status,stale);
      const coreFirst=this.core.range.first;
      for(const day of days)this.rotas.set(day,this.core.call('pw_day_rota',day-coreFirst));
    }
    this.preparedKey=JSON.stringify([this.config,this._events,this.mode,this.anchor,this.today,this.second>=16*3600,this.status,this.stale]);
    return this.preparedKey;
  }
  render(mode,status,stale=false) {
    if(mode==='unavailable') { this.unavailable=status;this.stale=stale;this.dialog.close();this.draw(); }
    else { this.prepare(mode,status,stale);this.draw(); }
  }
  press(_now,busy) { return busy?0:2; }
  visible() {} expire() { return false; } placeholder() {} // No flashes or simulated pigment animation.
  member(key) { return this.config.members.find(m=>m.key===key); }
  owner(member) { return node('span',member.label,`planner-owner owner-${member.colour}`); }
  essentials(profile,day,full=false,preparation=false) {
    const s=schoolDay(profile,day),m=this.member(profile.member),box=node('section',undefined,'school-essential');
    box.append(this.owner(m));
    if(!s.school) { box.append(node('p',s.reason,'planner-muted'));return box; }
    const week=profile.cycleWeeks===2?`Week ${s.week===1?'A':'B'}`:'Every week';
    box.append(node('span',week,'cycle-label'));
    if(this.prefs.school || full || preparation) {
      const uniform=node('strong',UNIFORMS[s.uniform],s.uniform==='pe'?'uniform-pe':'');
      const line=node('p',undefined,'ready-line');line.append(uniform,node('span',snackLabel(s.snacks)));box.append(line);
      if(s.kit)box.append(node('p',`Pack: ${s.kit}`,'packing-note'));
    }
    if(!preparation && (this.prefs.lessons || full) && s.lessons.length) {
      const list=node('ol',undefined,'lesson-list');
      s.lessons.forEach((l,i)=>list.append(node('li',`${l.start?l.start:`${i+1}.`} ${l.name}${l.room?` · ${l.room}`:''}`)));
      box.append(list);
    } else if(!preparation && (this.prefs.lessons || full) && !s.lessons.length) box.append(node('p','Lessons not entered','planner-muted'));
    return box;
  }
  dayEntries(day) {
    const result=(this.visibleEvents||[]).filter(e=>overlaps(e,day)).map(e=>({member:this.config.members[e.calendar],name:e.title,time:eventTime(e,day),sort:e.allDay?-1:e.startDay<day?0:e.startSecond,notes:'',type:'event'}));
    for(const p of this.config.school||[])for(const a of schoolDay(p,day).activities)result.push({member:this.member(p.member),name:a.name,time:`${a.start}–${a.end}`,sort:Number(a.start.slice(0,2))*3600+Number(a.start.slice(3))*60,notes:[a.room,a.notes].filter(Boolean).join(' · '),type:'club'});
    return result.sort((a,b)=>a.sort-b.sort);
  }
  entry(item) {
    const row=node('li',undefined,`planner-entry owner-${item.member.colour}`);
    row.append(node('span',`${item.time}${item.type==='club'?' · Club / lesson':''}`,'entry-time'),node('strong',item.name),node('span',item.member.label,'entry-owner'));
    if(item.notes)row.append(node('span',item.notes,'entry-notes'));
    return row;
  }
  rota(day,compact=false) {
    if(!this.config.rotaMember)return null;
    const state=this.rotas.get(day)??0,member=this.member(this.config.rotaMember);
    const box=node('section',undefined,`planner-rota rota-${state}`);
    box.append(node('strong',`${member.label} · ${ROTA[state]}`));
    if(!compact) {
      if(state===4)box.append(node('span','Work and off-duty overlap. Check the source.'));
      else for(const line of shiftDetails(this._events,this.config,day))box.append(node('span',line));
    }
    return box;
  }
  showDay(day) {
    this.openDay=day;document.getElementById('day-heading').textContent=dateLabel(day,{weekday:'long',day:'numeric',month:'long',year:'numeric'});
    const content=document.getElementById('day-content');content.replaceChildren();
    const rota=this.rota(day);if(rota)content.append(rota);
    for(const p of this.config.school||[])content.append(this.essentials(p,day,true));
    const entries=this.dayEntries(day),list=node('ul',undefined,'planner-events');
    for(const e of entries)list.append(this.entry(e));
    content.append(entries.length?list:node('p','No appointments or activities in the loaded data.'));
    if(!this.dialog.open)this.dialog.showModal();
  }
  dayCard(day) {
    const today=day===this.today,card=node('article',undefined,`planner-day${today?' is-today':''}`);
    card.dataset.date=isoDay(day);card.tabIndex=0;card.setAttribute('aria-label',dateLabel(day,{weekday:'long',day:'numeric',month:'long'}));
    const heading=node('h2'),b=button(undefined,()=>this.showDay(day),'day-heading');
    b.dataset.day=isoDay(day);b.setAttribute('aria-label',`${dateLabel(day,{weekday:'long',day:'numeric',month:'long'})}${today?', today':''}: open full day`);
    if(today)b.setAttribute('aria-current','date');
    b.append(node('span',dateLabel(day,{weekday:'short'}),'day-dow'),node('strong',dateLabel(day,{day:'numeric'}),'day-number'),node('span',dateLabel(day,{month:'short'}),'day-month'));
    if(today)b.append(node('span','TODAY','today-label'));heading.append(b);card.append(heading);
    const rota=this.rota(day);if(rota)card.append(rota);
    if(this.prefs.school || this.prefs.lessons)for(const p of this.config.school||[]) {
      const s=schoolDay(p,day);
      if(s.school || ['Term dates not set','No school / excluded date'].includes(s.reason))card.append(this.essentials(p,day));
    }
    const entries=this.dayEntries(day),list=node('ul',undefined,'planner-events');
    for(const e of entries.slice(0,4))list.append(this.entry(e));card.append(list);
    if(entries.length>4) {
      const more=node('details',undefined,'more-events'),extra=node('ul',undefined,'planner-events');
      more.append(node('summary',`+${entries.length-4} more commitments`));for(const e of entries.slice(4))extra.append(this.entry(e));more.append(extra);card.append(more);
    }
    if(!entries.length)card.append(node('p','No other plans','empty-day'));
    return card;
  }
  monthCard(day) {
    const entries=this.dayEntries(day),state=this.rotas.get(day)??0,today=day===this.today;
    const b=button(undefined,()=>this.showDay(day),`month-day${today?' is-today':''}${isoDay(day).slice(0,7)!==isoDay(this.anchor).slice(0,7)?' outside-month':''}`);
    b.dataset.day=isoDay(day);
    b.setAttribute('aria-label',`${dateLabel(day,{weekday:'long',day:'numeric',month:'long'})}${today?', today':''}. ${this.config.rotaMember?ROTA[state]+'. ':''}${entries.length} commitments. Open day including school details.`);
    if(today)b.setAttribute('aria-current','date');
    b.append(node('strong',dateLabel(day,{day:'numeric'}),'month-number'));
    if(this.config.rotaMember)b.append(node('span',state===0?'Rota ?':ROTA[state],`month-rota rota-${state}`));
    b.append(node('span',entries.length?`${entries.length} plan${entries.length===1?'':'s'}`:'No plans','month-count'));
    return b;
  }
  draw() {
    this.updateControls();if(!this.config)return;
    const focused=document.activeElement?.dataset?.day;
    const focusOpen=this.root.querySelector('.school-focus-wrap')?.open;
    const expanded=new Set([...this.root.querySelectorAll('.more-events[open]')].map(n=>n.closest('[data-date]')?.dataset.date));
    this.root.replaceChildren();
    if(this.unavailable) {this.root.append(node('section',this.unavailable,'planner-unavailable'));return;}
    const {first,count}=this.range;
    const header=node('div',undefined,'planner-heading'),title=node('div');
    title.append(node('p',this.config.title,'planner-kicker'),node('h1',this.month?dateLabel(this.anchor,{month:'long',year:'numeric'}):`${dateLabel(first)} – ${dateLabel(first+count-1,{day:'numeric',month:'short',year:'numeric'})}`));
    header.append(title,node('p',`${this.month?'Month overview · tap a date for details':this.mode==='rolling'?'Seven days from the selected date':'Calendar week'} · ${this.config.timezone}`,'planner-caption'));this.root.append(header);
    if(this.config.rotaMember)this.root.append(node('p',`Work / on-call: ${this.member(this.config.rotaMember).label}. “Rota not confirmed” is not a day off.${this.stale?' Calendar data needs review; see status below.':''}`,'planner-guidance'));
    if(!this.month && this.prefs.school && this.config.school?.length) {
      const focus=node('section',undefined,'school-focus');focus.setAttribute('aria-label','Get ready for the next school day');
      focus.append(node('h2','Get ready','focus-title'));
      for(const p of this.config.school) {
        const start=Math.max(first,this.today+(this.second>=16*3600?1:0));
        let next=null;for(let d=start;d<first+count;d++)if(schoolDay(p,d).school){next=d;break;}
        if(next!==null) {
          const tile=node('div',undefined,'focus-child');tile.append(node('p',next===this.today?'Today':dateLabel(next,{weekday:'long',day:'numeric',month:'short'}),'focus-date'),this.essentials(p,next,false,true));focus.append(tile);
        } else {const tile=node('div',undefined,'focus-child');tile.append(this.owner(this.member(p.member)),node('p',p.terms.length?'No school day in the remaining saved range. Check term dates if unexpected.':'Add term dates in Administration to show school essentials.','planner-muted'));focus.append(tile);}
      }
      const wrap=node('details',undefined,'school-focus-wrap');wrap.open=focusOpen??!document.body.classList.contains('planner-fullscreen');
      wrap.append(node('summary','Get ready for school'),focus);this.root.append(wrap);
    }
    const grid=node('div',undefined,this.month?'planner-month':'planner-week');
    if(this.month)grid.style.setProperty('--weeks',String(count/7));
    if(this.month)for(let i=0;i<7;i++)grid.append(node('div',dateLabel(first+i,{weekday:'short'}),'month-dow'));
    for(let d=first;d<first+count;d++)grid.append(this.month?this.monthCard(d):this.dayCard(d));
    this.root.append(grid);
    for(const details of grid.querySelectorAll('.more-events'))details.open=expanded.has(details.closest('[data-date]').dataset.date);
    if(this.openDay!=null && this.dialog.open)this.showDay(this.openDay);
    else if(focused)this.root.querySelector(`[data-day="${focused}"]`)?.focus({preventScroll:true});
  }
}
export async function createPlannerRenderer(canvas) {
  return new PlannerRenderer(await createRenderer(canvas),document.getElementById('planner'));
}
