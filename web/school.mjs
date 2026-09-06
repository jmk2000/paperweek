/** School rules are civil-date patterns, not 24-hour recurrences or Google events. */
import {ordinal, isoDay} from './dates.mjs';
export const WEEKDAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
export const UNIFORMS = {unknown:'Uniform not set',school:'School uniform',pe:'PE uniform',none:'No uniform'};
export const mod = (n, d) => ((n % d) + d) % d;
export const weekday = day => mod(day + 3, 7) + 1;
export const mondayOf = day => day - weekday(day) + 1;
const fail = message => { throw new Error(`School: ${message}`); };
function object(raw, allowed, name) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) fail(`${name} must be an object.`);
  if (Object.keys(raw).some(k => !allowed.includes(k))) fail(`${name} contains an unknown field.`);
}
function text(value, max, name, required=false) {
  if (typeof value !== 'string' || value.length > max || /[\x00-\x1f\x7f]/.test(value) || (required && !value.trim())) fail(`Invalid ${name}.`);
  return value.trim();
}
function integer(value, min, max, name) {
  if (!Number.isInteger(value) || value < min || value > max) fail(`Invalid ${name}.`);
  return value;
}
function array(value, max, name) {
  if (!Array.isArray(value) || value.length > max) fail(`Too many or invalid ${name}.`);
  return value;
}
function date(value, anchor=false) {
  ordinal(value);
  if (anchor && weekday(ordinal(value)) !== 1) fail('Week A must be anchored to a Monday.');
  return value;
}
function dates(values, max) {
  const result=array(values ?? [],max,'exception dates').map(v=>date(v));
  if (new Set(result).size !== result.length) fail('Exception dates must be unique.');
  return result;
}
function lesson(raw, activity=false) {
  object(raw,['name','start','end','room',...(activity?['weekday','week','notes','skipDates']:[])],'lesson/activity');
  const result={name:text(raw.name,80,'lesson/activity name',true),start:raw.start??'',end:raw.end??'',room:text(raw.room??'',40,'room')};
  if (Boolean(result.start)!==Boolean(result.end)) fail('Enter both start and end times, or neither.');
  for (const t of [result.start,result.end]) if (typeof t!=='string'||(t&&!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(t))) fail('Use times in HH:MM format.');
  if (result.start && result.end <= result.start) fail('End time must be later on the same day.');
  if (activity) {
    if (!result.start) fail('Clubs and music lessons need start and end times.');
    Object.assign(result,{weekday:integer(raw.weekday,1,7,'activity weekday'),week:integer(raw.week??0,0,2,'activity week'),notes:text(raw.notes??'',160,'activity notes'),skipDates:dates(raw.skipDates,80)});
  }
  return result;
}
export function validateSchool(raw=[], members=[]) {
  const profiles=array(raw,6,'school profiles').map(p=>{
    object(p,['member','cycleWeeks','anchor','terms','excludeDates','days','activities'],'profile');
    if (!members.some(m=>m.key===p.member)) fail('Choose an existing person for each profile.');
    const cycleWeeks=integer(p.cycleWeeks??1,1,2,'cycle length');
    const terms=array(p.terms??[],32,'terms').map(t=>{
      object(t,['start','end','weekA'],'term');
      const term={start:date(t.start),end:date(t.end),weekA:t.weekA?date(t.weekA,true):''};
      if (term.end<term.start) fail('Term end must not precede its start.');
      return term;
    });
    const sorted=[...terms].sort((a,b)=>a.start.localeCompare(b.start));
    if (sorted.some((t,i)=>i && sorted[i-1].end>=t.start)) fail('Term ranges must not overlap; ends are inclusive.');
    const days=array(p.days??[],10,'school-day rules').map(d=>{
      object(d,['week','weekday','uniform','snacks','kit','lessons'],'day rule');
      const uniform=d.uniform??'unknown';
      if (!Object.hasOwn(UNIFORMS,uniform)) fail('Choose a supported uniform.');
      return {week:integer(d.week,1,cycleWeeks,'day week'),weekday:integer(d.weekday,1,5,'school weekday'),uniform,
        snacks:d.snacks==null?null:integer(d.snacks,0,9,'snack count'),kit:text(d.kit??'',120,'kit'),lessons:array(d.lessons??[],10,'lessons').map(l=>lesson(l))};
    });
    if (new Set(days.map(d=>`${d.week}:${d.weekday}`)).size!==days.length) fail('Duplicate school-day rules.');
    const activities=array(p.activities??[],24,'activities').map(a=>lesson(a,true));
    if (activities.some(a=>a.week>cycleWeeks)) fail('Week B activities require a two-week timetable.');
    return {member:p.member,cycleWeeks,anchor:date(p.anchor,true),terms,excludeDates:dates(p.excludeDates,180),days,activities};
  });
  if (new Set(profiles.map(p=>p.member)).size!==profiles.length) fail('Only one profile per person.');
  if (new TextEncoder().encode(JSON.stringify(profiles)).length>48000) fail('School settings exceed 48 KB. Shorten notes or remove old terms.');
  return profiles;
}
export function schoolDay(profile, day) {
  const iso=isoDay(day), term=profile.terms.find(t=>t.start<=iso && iso<=t.end);
  const base={member:profile.member,day,school:false,week:null,uniform:'unknown',snacks:null,kit:'',lessons:[],activities:[]};
  if (!profile.terms.length) return {...base,reason:'Term dates not set'};
  if (!term) return {...base,reason:'Outside saved term dates'};
  if (profile.excludeDates.includes(iso)) return {...base,reason:'No school / excluded date'};
  const week=mod(Math.floor((mondayOf(day)-ordinal(term.weekA||profile.anchor))/7),profile.cycleWeeks)+1;
  const dow=weekday(day), rule=profile.days.find(r=>r.week===week && r.weekday===dow);
  const activities=profile.activities.filter(a=>a.weekday===dow && (!a.week || a.week===week) && !a.skipDates.includes(iso)).sort((a,b)=>a.start.localeCompare(b.start));
  return {...base,...rule,day,week,school:dow<=5,reason:dow>5?'Weekend':'',activities};
}
export function snackLabel(count) { return count==null?'Snacks not set':count===0?'No snacks':`${count} snack${count===1?'':'s'}`; }
