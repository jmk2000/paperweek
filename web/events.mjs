import {ascii} from './config.mjs';
import {ordinal, zonedParts} from './dates.mjs';
export const MAX_EVENTS=2048;
export const KINDS={event:0,work:1,oncall:2,off:3};
const offsets=/(?:Z|[+-]\d{2}:\d{2})$/i;
export function normaliseEvent(raw, member, index, config) {
  if(raw.status==='cancelled'||raw.attendees?.some(a=>a.self&&a.responseStatus==='declined')) return null;
  const start=raw.start||{}, end=raw.end||{};
  let allDay=false,s,e;
  if(start.date){
    allDay=true;s={day:ordinal(start.date),second:0,epoch:ordinal(start.date)*86400000};
    e={day:ordinal(end.date||''),second:0,epoch:ordinal(end.date||'')*86400000};
    if(e.day<=s.day) throw new Error('An all-day event has an invalid exclusive end date.');
  }else{
    // Google normally supplies RFC3339 offsets. Reject ambiguous local times
    // instead of silently applying the tablet's timezone or guessing DST folds.
    if(!offsets.test(start.dateTime||'')||!offsets.test(end.dateTime||'')) throw new Error('A timed event is missing its UTC offset.');
    s=zonedParts(start.dateTime,config.timezone);e=zonedParts(end.dateTime,config.timezone);
    if(e.epoch<s.epoch)throw new Error('An event ends before it starts.');
  }
  let kind=KINDS.event;
  let title=String(raw.summary||'Busy');
  if(member.key===config.rotaMember){const tag=title.match(/^\[PW:(WORK|ONCALL|OFF)\](?:\s|$)/i);if(tag)kind=KINDS[tag[1].toLowerCase()];}
  if(kind===KINDS.off&&!allDay)throw new Error('A [PW:OFF] marker must be an all-day event.');
  if(member.maskTitles||(config.maskPrivate&&raw.visibility==='private'))title='Busy';
  const uid=String(raw.iCalUID||`${member.key}:${raw.id||'unknown'}`);
  // Hash the complete identity rather than truncate it. This avoids collisions
  // from long Calendar IDs sharing a common prefix; no identifier reaches UI.
  const key=identityHash(`${uid}|${allDay?start.date:new Date(s.epoch).toISOString()}`);
  return {key,title:ascii(title),calendar:index,startDay:s.day,endDay:e.day,
    startSecond:s.second,endSecond:e.second,allDay,kind,sortTime:s.epoch};
}
export function identityHash(value) {
  // Two independent 32-bit rolling hashes + full length. Not cryptographic and
  // not a privacy/security boundary; only an in-memory deduplication key.
  let a=2166136261,b=5381;
  for(let i=0;i<value.length;++i){a=Math.imul(a^value.charCodeAt(i),16777619)>>>0;b=(Math.imul(b,33)^value.charCodeAt(i))>>>0;}
  return `${a.toString(16)}:${b.toString(16)}:${value.length}`;
}
export function validateEvents(events,config) {
  if(!Array.isArray(events)||events.length>MAX_EVENTS)throw new Error(`This prototype supports at most ${MAX_EVENTS} expanded records per loaded range. Narrow the selection.`);
  for(const e of events){
    if(!Number.isInteger(e.calendar)||e.calendar<0||e.calendar>=config.members.length)throw new Error('Invalid calendar index.');
    for(const k of ['startDay','endDay','startSecond','endSecond','kind'])if(!Number.isInteger(e[k]))throw new Error('Invalid event field.');
    if(e.startDay<-25567||e.endDay>84370||e.endDay<e.startDay||e.startSecond<0||e.startSecond>86399||e.endSecond<0||e.endSecond>86399)throw new Error('Invalid event date or time.');
    if(e.kind<0||e.kind>3||typeof e.allDay!=='boolean'||!Number.isFinite(e.sortTime))throw new Error('Invalid event type.');
    if(e.kind===3&&!e.allDay)throw new Error('Off-duty markers must be all-day.');
    if(e.allDay&&e.endDay<=e.startDay)throw new Error('All-day end dates must be exclusive.');
    if(typeof e.key!=='string'||typeof e.title!=='string')throw new Error('Invalid event text.');
  }
  return events;
}
export function demoEvents(first,count,config) {
  const result=[];
  const add=(calendar,day,title,hour=10,kind=0,duration=3600,allDay=false)=>{
    const masked=config.members[calendar].maskTitles;
    result.push({key:`demo-${calendar}-${day}-${title}`,title:masked?'Busy':title,calendar,
      startDay:day,endDay:allDay?day+1:day+Math.floor((hour*3600+duration)/86400),
      startSecond:allDay?0:hour*3600,endSecond:allDay?0:(hour*3600+duration)%86400,
      allDay,kind,sortTime:day*86400000+hour*3600000});
  };
  const rota=config.members.findIndex(m=>m.key===config.rotaMember);
  for(let d=first;d<first+count;++d){
    const weekday=((d+4)%7+7)%7;
    if(rota>=0){const phase=((d%9)+9)%9;
      if(phase===0||phase===3||phase===8)add(rota,d,'[PW:OFF]',0,3,0,true);
      else if(phase!==6)add(rota,d,'[PW:WORK]',phase===5?20:8,phase===2?2:1,phase===5?12*3600:9*3600);
    }
    if(weekday===1)add(0,d,'Team planning',9);
    if(weekday===2)add(Math.min(2,config.members.length-1),d,'Swimming',17);
    if(weekday===3)add(Math.min(3,config.members.length-1),d,'Music lesson',16);
    if(weekday===4)add(Math.min(1,config.members.length-1),d,'Library visit',18);
    if(weekday===5&&d%2===0)add(0,d,'School closed',0,0,0,true);
    if(weekday===6){add(Math.min(2,config.members.length-1),d,'Sports practice',10);add(Math.min(3,config.members.length-1),d,'Birthday party',14);}
    if(weekday===0&&d%3===0)add(0,d,'Lunch with friends',13);
    if(d%13===0)for(let k=0;k<7;++k)add(k%config.members.length,d,`Demo appointment ${k+1}`,9+k);
  }
  return validateEvents(result,config);
}
