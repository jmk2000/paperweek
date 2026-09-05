const DAY = 86400000;
const formatters = new Map();
export function ordinal(iso) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) throw new Error('Invalid calendar date.');
  const [y,m,d] = iso.split('-').map(Number);
  if (y < 1900 || y > 2200) throw new Error('Dates must be between 1900 and 2200.');
  const t = new Date(Date.UTC(y,m-1,d));
  if(t.getUTCFullYear()!==y||t.getUTCMonth()!==m-1||t.getUTCDate()!==d) throw new Error('Invalid calendar date.');
  return Math.floor(t.getTime()/DAY);
}
export function isoDay(day) { return new Date(day*DAY).toISOString().slice(0,10); }
export function zonedParts(value, zone) {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) throw new Error('Invalid event timestamp.');
  let fmt = formatters.get(zone);
  if(!fmt){fmt=new Intl.DateTimeFormat('en-GB',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});formatters.set(zone,fmt);}
  const p=Object.fromEntries(fmt.formatToParts(date).filter(x=>x.type!=='literal').map(x=>[x.type,x.value]));
  return {day:ordinal(`${p.year}-${p.month}-${p.day}`), second:Number(p.hour)*3600+Number(p.minute)*60+Number(p.second), epoch:date.getTime()};
}
export function googleBounds(first,count) {
  // A deliberately generous UTC window covers all display timezones, including
  // all-day records. The shared C core performs the exact civil-day filtering.
  return {timeMin:new Date((first-2)*DAY).toISOString(),timeMax:new Date((first+count+2)*DAY).toISOString()};
}
