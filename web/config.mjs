export const VERSION = '0.5.0';
export const STORAGE_KEY = 'paperweek.settings.v3';
export const COLOURS = {black: 0, red: 2, yellow: 3, blue: 4, green: 5};
export function defaults() {
  return {
    version: 3, title: 'Our calendar', timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC', weekStart: 1,
    defaultView: 'month', paperPalette: true, maskPrivate: true, deduplicate: false,
    rotaMember: 'member-2', persistentLabels: true, helpSeconds: 20,
    refreshSeconds: 0, pollMinutes: 5, clientId: '', source: 'demo',
    members: [
      {key: 'member-1', label: 'Adult 1', badge: '1', colour: 'blue', calendarId: '', maskTitles: false},
      {key: 'member-2', label: 'Adult 2', badge: '2', colour: 'green', calendarId: '', maskTitles: false},
      {key: 'member-3', label: 'Child 1', badge: '3', colour: 'red', calendarId: '', maskTitles: false},
      {key: 'member-4', label: 'Child 2', badge: '4', colour: 'yellow', calendarId: '', maskTitles: false},
    ],
  };
}
export function ascii(value, limit = 191) {
  const map = {'–':'-', '—':'-', '‘':"'", '’':"'", '“':'"', '”':'"', '…':'...', 'ß':'ss', 'ø':'o', 'Ø':'O', 'æ':'ae', 'œ':'oe', '•':'/', '→':'>', '←':'<'};
  let s = String(value ?? '').replace(/[–—‘’“”…ßøØæœ•→←]/g, c => map[c]).normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ').trim().replace(/[^\x20-\x7e]/g, '?');
  return s.length <= limit ? s : s.slice(0, Math.max(0, limit - 3)) + '...';
}
function text(value, name, max, empty = false) {
  if (typeof value !== 'string' || value.length > max || (!empty && !value.trim())) throw new Error(`${name} must be ${empty?'0':'1'}–${max} characters.`);
  if (/[\x00-\x1f\x7f]/.test(value)) throw new Error(`${name} contains a control character.`);
  return value.trim();
}
function boolean(value, name) { if (typeof value !== 'boolean') throw new Error(`${name} must be true or false.`); return value; }
function integer(value, name, min, max) { if (!Number.isInteger(value) || value < min || value > max) throw new Error(`${name} must be between ${min} and ${max}.`); return value; }
export function validateConfig(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw) || raw.version !== 3) throw new Error('This must be a Paperweek version 3 settings file.');
  const d = defaults();
  const c = {...d};
  c.title = text(raw.title, 'Calendar title', 80);
  c.timezone = text(raw.timezone, 'Timezone', 64);
  try { new Intl.DateTimeFormat('en', {timeZone:c.timezone}).format(); } catch { throw new Error('Choose a valid IANA timezone, such as UTC or Europe/London.'); }
  c.weekStart = integer(raw.weekStart, 'First day', 0, 1);
  if (!['week','month'].includes(raw.defaultView)) throw new Error('Default view must be week or month.');
  c.defaultView = raw.defaultView;
  for (const key of ['paperPalette','maskPrivate','deduplicate','persistentLabels']) c[key] = boolean(raw[key], key);
  c.helpSeconds = integer(raw.helpSeconds, 'Help timeout', 5, 120);
  c.refreshSeconds = integer(raw.refreshSeconds, 'Simulated refresh', 0, 60);
  c.pollMinutes = integer(raw.pollMinutes, 'Poll interval', 1, 60);
  c.clientId = text(raw.clientId, 'Google client ID', 250, true);
  if (c.clientId && !/^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$/.test(c.clientId)) throw new Error('Enter a Google Web application OAuth client ID, not a client secret or JSON file.');
  if (!['demo','google'].includes(raw.source)) throw new Error('Source must be demo or google.');
  c.source = raw.source;
  if (!Array.isArray(raw.members) || raw.members.length < 1 || raw.members.length > 6) throw new Error('Choose one to six calendars.');
  const keys = new Set(), ids = new Set(), badges = new Set();
  c.members = raw.members.map((m, index) => {
    if (!m || typeof m !== 'object') throw new Error(`Calendar ${index+1} is invalid.`);
    const key = text(m.key, 'Member key', 48);
    if (!/^[a-z0-9_-]+$/i.test(key) || keys.has(key)) throw new Error('Member keys must be unique letters, numbers, hyphens or underscores.');
    keys.add(key);
    const label = text(m.label, 'Display name', 40);
    const badge = text(m.badge, 'Badge', 2).toUpperCase();
    if (!/^[A-Z0-9]{1,2}$/.test(badge) || badges.has(badge)) throw new Error('Use a unique one- or two-character letter/number badge for each calendar.');
    badges.add(badge);
    if (!Object.hasOwn(COLOURS,m.colour)) throw new Error('Choose one of the supported e-paper colours.');
    const calendarId = text(m.calendarId, 'Calendar ID', 512, true);
    if (calendarId && ids.has(calendarId)) throw new Error('Each Google calendar can only be assigned once.');
    if (calendarId) ids.add(calendarId);
    return {key,label,badge,colour:m.colour,calendarId,maskTitles:boolean(m.maskTitles,'Mask titles')};
  });
  c.rotaMember = text(raw.rotaMember, 'Rota member', 48, true);
  if (c.rotaMember && !keys.has(c.rotaMember)) throw new Error('The rota calendar must be one of the selected members.');
  return c; // Unknown keys (including tokens and secrets) are intentionally dropped.
}
export function loadConfig(storage = globalThis.localStorage) {
  const saved = storage?.getItem(STORAGE_KEY);
  return saved ? validateConfig(JSON.parse(saved)) : defaults();
}
export function saveConfig(config, storage = globalThis.localStorage) {
  const safe = validateConfig(config); storage.setItem(STORAGE_KEY, JSON.stringify(safe)); return safe;
}
export function clearConfig(storage = globalThis.localStorage) { storage.removeItem(STORAGE_KEY); }
