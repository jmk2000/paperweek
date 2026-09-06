/** Small form editor. Saves with the existing revision-checked shared settings. */
import {validateSchool,WEEKDAYS,UNIFORMS,mondayOf} from './school.mjs';
import {isoDay,zonedParts} from './dates.mjs';
const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const action=(text,handler)=>{const b=el('button',text);b.type='button';b.onclick=handler;return b;};
function input(label,value,write,type='text',max) {
  const wrap=el('label',label),field=el('input');field.type=type;field.value=value??'';
  if(max)field.maxLength=max;
  if(type==='number'){field.min=0;field.max=9;field.step=1;}
  field.oninput=()=>write(type==='number'?(field.value===''?null:Number(field.value)):field.value);
  wrap.append(field);return wrap;
}
function select(label,value,choices,write) {
  const wrap=el('label',label),field=el('select');
  for(const [v,t]of choices){const o=el('option',t);o.value=v;field.append(o);}field.value=String(value);
  field.onchange=()=>write(field.value);wrap.append(field);return wrap;
}
function dateList(label,values,write) {
  const wrap=el('label',label),field=el('textarea');field.rows=3;field.value=values.join('\n');field.placeholder='YYYY-MM-DD, one date per line';
  field.oninput=()=>write(field.value.split(/[\s,]+/).filter(Boolean));wrap.append(field);return wrap;
}
function group(title,open=false) {const d=el('details',undefined,'school-editor-group');d.open=open;d.append(el('summary',title));return d;}
export function createSchoolEditor(root,getMembers,onChange,getZone=()=> 'UTC') {
  let profiles=[];
  const change=()=>onChange();
  const redraw=()=>{change();render();};
  function profileEditor(p,index) {
    const m=getMembers().find(m=>m.key===p.member),box=group(`${m?.label||'Removed person'} · ${p.cycleWeeks===2?'two-week timetable':'weekly timetable'}`,index===0);
    const setup=el('div',undefined,'school-editor-grid');
    setup.append(select('Repeat school timetable',p.cycleWeeks,[[1,'Every week'],[2,'Two weeks: A / B']],value=>{
      const n=Number(value);
      if(n===1 && p.cycleWeeks===2 && !confirm('Switch to weekly? This removes Week B day rules and Week B-only activities.')){render();return;}
      p.cycleWeeks=n;p.days=p.days.filter(d=>d.week<=n);p.activities=p.activities.filter(a=>a.week<=n);redraw();
    }),input('A Monday in Week A',p.anchor,v=>p.anchor=v,'date'));
    box.append(setup,el('p','Choose a known Monday in Week A, not an ISO week number. Holidays do not pause the cycle. A term can override the anchor when school restarts its cycle.','hint'));
    const terms=group('Term dates and INSET / closed dates',true);
    terms.append(el('p','Add each teaching block separately, leaving half-term and holidays out. End dates include that day. Nothing repeats outside saved term dates.','hint'));
    for(const t of p.terms) {
      const row=el('div',undefined,'school-editor-grid');
      row.append(input('First day',t.start,v=>t.start=v,'date'),input('Last day (inclusive)',t.end,v=>t.end=v,'date'),input('Reset Week A Monday (optional)',t.weekA,v=>t.weekA=v,'date'),action('Remove term',()=>{p.terms.splice(p.terms.indexOf(t),1);redraw();}));terms.append(row);
    }
    terms.append(action('Add term dates',()=>{if(p.terms.length>=32)return;p.terms.push({start:'',end:'',weekA:''});redraw();}),dateList('INSET / excluded dates — suppress school and all term-time activities',p.excludeDates,v=>p.excludeDates=v));box.append(terms);
    for(let week=1;week<=p.cycleWeeks;week++) {
      const weekBox=group(p.cycleWeeks===2?`Week ${week===1?'A':'B'} · uniform, snacks and lessons`:'Monday to Friday · uniform, snacks and lessons',week===1);
      for(let weekday=1;weekday<=5;weekday++) {
        let rule=p.days.find(d=>d.week===week&&d.weekday===weekday);
        // Explicit unknowns are intentional: never invent a uniform/snack count.
        if(!rule){rule={week,weekday,uniform:'unknown',snacks:null,kit:'',lessons:[]};p.days.push(rule);}
        const day=group(WEEKDAYS[weekday-1]),row=el('div',undefined,'school-editor-grid');
        const summary=()=>{day.firstChild.textContent=`${WEEKDAYS[weekday-1]} · ${UNIFORMS[rule.uniform]} · ${rule.snacks==null?'snacks not set':rule.snacks+' snacks'} · ${rule.lessons.length} lessons`;};summary();
        row.append(select('Wear',rule.uniform,Object.entries(UNIFORMS),(v)=>{rule.uniform=v;summary();}),input('Snacks (blank = not set)',rule.snacks,v=>{rule.snacks=v;summary();},'number'),input('Extra kit / packing note',rule.kit,v=>rule.kit=v,'text',120));day.append(row);
        for(const l of rule.lessons)day.append(lessonRow(l,()=>{rule.lessons.splice(rule.lessons.indexOf(l),1);redraw();}));
        day.append(action('Add lesson',()=>{if(rule.lessons.length>=10)return;rule.lessons.push({name:'',start:'',end:'',room:''});redraw();}));weekBox.append(day);
      }
      if(p.cycleWeeks===2 && week===2)weekBox.append(action('Copy Week A to Week B',()=>{if(!confirm('Replace Week B uniform, snack, kit and lesson rules with Week A? Clubs are unchanged.'))return;p.days=[...p.days.filter(d=>d.week===1),...p.days.filter(d=>d.week===1).map(d=>({...structuredClone(d),week:2}))];redraw();}));box.append(weekBox);
    }
    const activities=group('Clubs and music lessons · term time',true);
    activities.append(el('p','These stay visible even when the school timetable is hidden. Use the end time for pickup and the note for the pickup place, instrument or other kit. Weekend activities can repeat too.','hint'));
    for(const a of p.activities) {
      const item=el('fieldset',undefined,'school-activity');item.append(el('legend',a.name||'New activity'));
      const row=el('div',undefined,'school-editor-grid');
      row.append(select('Day',a.weekday,WEEKDAYS.map((d,i)=>[i+1,d]),v=>a.weekday=Number(v)),select('Repeat',a.week,[[0,'Every week'],[1,p.cycleWeeks===2?'Week A only':'Every week'],...(p.cycleWeeks===2?[[2,'Week B only']]:[])],v=>a.week=Number(v)));
      item.append(row,lessonRow(a,()=>{p.activities.splice(p.activities.indexOf(a),1);redraw();}),input('Pickup / kit note',a.notes,v=>a.notes=v,'text',160),dateList('Cancelled dates for this activity only',a.skipDates,v=>a.skipDates=v));activities.append(item);
    }
    activities.append(action('Add club or music lesson',()=>{if(p.activities.length>=24)return;p.activities.push({name:'',start:'',end:'',room:'',weekday:1,week:0,notes:'',skipDates:[]});redraw();}));box.append(activities);
    box.append(action('Remove school profile',()=>{if(confirm(`Remove the school profile for ${m?.label||'this person'}? Save shared settings to apply.`)){profiles.splice(index,1);redraw();}}));
    return box;
  }
  function lessonRow(l,remove) {
    const row=el('div',undefined,'school-editor-grid lesson-editor');
    row.append(input('Subject / activity',l.name,v=>l.name=v,'text',80),input('Start',l.start,v=>l.start=v,'time'),input('End',l.end,v=>l.end=v,'time'),input('Room / place',l.room,v=>l.room=v,'text',40),action('Remove',remove));return row;
  }
  function render() {
    // Preserve open day/term sections when adding a row, without storing any
    // family data in localStorage or writing settings before the Save button.
    const opened=new Set([...root.querySelectorAll('details[open]')].map(d=>d.firstChild.textContent.split(' · ')[0]));
    root.replaceChildren();profiles.forEach((p,i)=>root.append(profileEditor(p,i)));
    const available=getMembers().filter(m=>!profiles.some(p=>p.member===m.key));
    if(available.length) {
      const row=el('div',undefined,'row');let member=available[0].key;
      row.append(select('Add school profile for',member,available.map(m=>[m.key,m.label]),v=>member=v),action('Add school profile',()=>{
        let today;try{today=zonedParts(new Date(),getZone()).day;}catch{today=zonedParts(new Date(),'UTC').day;}
        profiles.push({member,cycleWeeks:1,anchor:isoDay(mondayOf(today)),terms:[],excludeDates:[],days:[],activities:[]});redraw();
      }));root.append(row);
    }
    for(const d of root.querySelectorAll('details'))if(opened.has(d.firstChild.textContent.split(' · ')[0]))d.open=true;
  }
  root.addEventListener('input',change);root.addEventListener('change',change);
  return {set(value){profiles=structuredClone(value||[]);render();},read(members=getMembers()){return validateSchool(profiles,members);},hasMember(key){return profiles.some(p=>p.member===key);}};
}
