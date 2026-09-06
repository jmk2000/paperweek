/** Browser presentation helpers. Rota STATE is still read from the C engine. */
import {ordinal,isoDay} from './dates.mjs';
import {mod} from './school.mjs';
export const VIEWS=['rolling','week','month'];
export const ROTA=['Rota not confirmed','Off duty','Working','ON CALL','CHECK ROTA'];
export function viewRange(anchor, mode='rolling', weekStart=1) {
  if (mode==='rolling') return {first:anchor,count:7};
  const dt=new Date(anchor*86400000);
  const start=mode==='month'?ordinal(`${isoDay(anchor).slice(0,7)}-01`):anchor;
  const first=start-mod(mod(start+4,7)-weekStart,7);
  if (mode!=='month') return {first,count:7};
  const last=Math.floor(Date.UTC(dt.getUTCFullYear(),dt.getUTCMonth()+1,0)/86400000);
  return {first,count:(Math.floor((last-first)/7)+1)*7};
}
export function moveAnchor(anchor, month, delta) {
  if (!month) return anchor+7*delta;
  const d=new Date(anchor*86400000),year=d.getUTCFullYear(),m=d.getUTCMonth()+delta;
  const end=new Date(Date.UTC(year,m+1,0)).getUTCDate();
  return Math.floor(Date.UTC(year,m,Math.min(d.getUTCDate(),end))/86400000);
}
export function overlaps(e,day) {
  if (e.allDay) return e.startDay<=day && day<e.endDay;
  if (e.startDay===e.endDay && e.startSecond===e.endSecond) return e.startDay===day;
  return e.startDay<=day && (e.endDay>day || (e.endDay===day && e.endSecond>0));
}
export function appointments(events,config) {
  const rota=config.members.findIndex(m=>m.key===config.rotaMember);
  const visible=events.filter(e=>!(e.calendar===rota && e.kind!==0));
  const winners=new Map();
  if (config.deduplicate) for (const e of visible) {
    const prior=winners.get(e.key);
    if (e.key && (!prior || e.calendar<prior.calendar)) winners.set(e.key,e);
  }
  return visible.filter(e=>!config.deduplicate || !e.key || winners.get(e.key)===e)
    .sort((a,b)=>Number(b.allDay)-Number(a.allDay) || a.sortTime-b.sortTime || (a.title<b.title?-1:a.title>b.title?1:0) || a.calendar-b.calendar);
}
export const timeLabel = seconds => `${String(Math.floor(seconds/3600)).padStart(2,'0')}:${String(Math.floor(seconds/60)%60).padStart(2,'0')}`;
export function eventTime(e, day) {
  if (e.allDay) return 'All day';
  if (e.startDay<day) return e.endDay===day?`Until ${timeLabel(e.endSecond)}`:'Continues overnight';
  const extra=e.endDay-day;
  return `${timeLabel(e.startSecond)}–${timeLabel(e.endSecond)}${extra>0?` (+${extra} day${extra===1?'':'s'})`:''}`;
}
export function shiftDetails(events,config,day) {
  const rota=config.members.findIndex(m=>m.key===config.rotaMember);
  return [...new Set(events.filter(e=>e.calendar===rota && (e.kind===1 || e.kind===2) && overlaps(e,day))
    .sort((a,b)=>b.kind-a.kind || a.sortTime-b.sortTime)
    .map(e=>`${e.kind===2?'On call':'Work'} · ${eventTime(e,day)}`))];
}
export function dateLabel(day,options={weekday:'short',day:'numeric',month:'short'}) {
  return new Intl.DateTimeFormat('en-GB',{...options,timeZone:'UTC'}).format(new Date(day*86400000));
}
