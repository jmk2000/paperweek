"""Bounded iCalendar VEVENT reader for subscribed household calendars.

Uses python-dateutil for RRULE and embedded VTIMEZONE. This is deliberately
not a CalDAV/iTIP implementation. Unsupported scheduling constructs fail the
whole fetch, retaining the previous cache instead of silently losing events.
Parsing runs in a resource-limited subprocess in production (ical_worker).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
from io import StringIO
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dateutil.rrule import rrulestr
from dateutil.tz import tzical, datetime_exists

UTC = timezone.utc
MAX_BYTES = 2 * 1024 * 1024
MAX_COMPONENTS = 6000
MAX_EVENTS = 6000
MAX_STEPS = 150000


class ICalError(ValueError):
    """Only static, safe messages; never include feed contents or addresses."""


@dataclass
class Prop:
    params: dict
    value: str


def split_quoted(text, separator):
    result, start, quoted = [], 0, False
    for i, ch in enumerate(text):
        if ch == '"':
            quoted = not quoted
        if ch == separator and not quoted:
            result.append(text[start:i]); start = i + 1
    if quoted:
        raise ICalError('Unclosed quoted iCalendar parameter.')
    result.append(text[start:])
    return result


def property_line(line):
    quoted, colon = False, None
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == ':' and not quoted:
            colon = i
            break
    if colon is None:
        raise ICalError('Malformed iCalendar content line.')
    head, value = line[:colon], line[colon+1:]
    tokens = split_quoted(head, ';')
    name, params = tokens[0].upper(), {}
    if not re.fullmatch('[A-Z0-9-]+', name):
        raise ICalError('Invalid iCalendar property name.')
    for token in tokens[1:]:
        if '=' not in token:
            raise ICalError('Malformed iCalendar parameter.')
        key, val = token.split('=', 1)
        key = key.upper()
        if key in params:
            raise ICalError('Repeated iCalendar parameter.')
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        # RFC 6868 parameter escapes; no URL/file dereferencing.
        params[key] = re.sub(r'\^(\^|n|N|\')', lambda m: {'^':'^', 'n':'\n', 'N':'\n', "'":'"'}[m[1]], val)
    return name, Prop(params, value)


def text(value):
    return re.sub(r'\\([nN,;\\])', lambda m: '\n' if m[1] in 'nN' else m[1], value)


def text_list(value):
    parts, start, escaped = [], 0, False
    for i, ch in enumerate(value):
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ',':
            parts.append(text(value[start:i])); start = i+1
    parts.append(text(value[start:]))
    return parts


def one(props, name, required=False):
    values = props.get(name, [])
    if len(values) > 1:
        raise ICalError('A single-valued event property was repeated.')
    if not values and required:
        raise ICalError('Event is missing a required date or UID.')
    return values[0] if values else None


def read_components(data):
    if len(data) > MAX_BYTES:
        raise ICalError('Calendar exceeds the 2 MiB subscription limit.')
    # Unfold bytes before UTF-8 decoding, including folds inside UTF-8 characters.
    data = re.sub(br'\r?\n[ \t]', b'', data)
    try:
        lines = data.decode('utf-8-sig').replace('\r\n', '\n').split('\n')
    except UnicodeError:
        raise ICalError('Calendar must be UTF-8 iCalendar, not a web page.') from None
    if len(lines) > 60000 or any(len(s) > 65536 for s in lines):
        raise ICalError('Calendar line limits exceeded.')
    stack, events, header, tzlines = [], [], {}, []
    current, tzblock, roots = None, None, 0
    ignored = set()
    for line in lines:
        if not line:
            continue
        name, prop = property_line(line)
        if name == 'BEGIN':
            kind = prop.value.upper()
            if not stack:
                if kind != 'VCALENDAR' or roots:
                    raise ICalError('Expected one complete VCALENDAR document.')
                roots += 1
            if len(stack) >= 6:
                raise ICalError('Calendar nesting limit exceeded.')
            if kind == 'VEVENT':
                if stack != ['VCALENDAR']:
                    raise ICalError('Unexpected nested calendar event.')
                current = {}
            if kind == 'VTIMEZONE':
                if stack != ['VCALENDAR']:
                    raise ICalError('Unexpected timezone component.')
                tzblock = []
            if len(stack) == 1 and kind not in ('VEVENT', 'VTIMEZONE'):
                ignored.add(kind)
            stack.append(kind)
        if tzblock is not None:
            tzblock.append(line)
        if name == 'END':
            if not stack or stack.pop() != prop.value.upper():
                raise ICalError('Incomplete or mismatched calendar component.')
            if prop.value.upper() == 'VEVENT':
                events.append(current); current = None
                if len(events) > MAX_COMPONENTS:
                    raise ICalError('Calendar has too many event components.')
            if prop.value.upper() == 'VTIMEZONE':
                tzlines.extend(tzblock); tzblock = None
            continue
        if name == 'BEGIN':
            continue
        if stack == ['VCALENDAR']:
            header.setdefault(name, []).append(prop)
        elif stack == ['VCALENDAR', 'VEVENT']:
            current.setdefault(name, []).append(prop)
        elif not stack:
            raise ICalError('Unexpected content outside the calendar.')
    if stack or roots != 1:
        raise ICalError('Truncated calendar; no partial data was saved.')
    version = one(header, 'VERSION', True)
    if version.value != '2.0':
        raise ICalError('Use an iCalendar VERSION 2.0 subscription.')
    method = one(header, 'METHOD')
    if method and method.value.upper() not in ('PUBLISH',):
        raise ICalError('This is an invitation/update message, not a complete subscribed calendar.')
    scale = one(header, 'CALSCALE')
    if scale and scale.value.upper() != 'GREGORIAN':
        raise ICalError('Only Gregorian subscribed calendars are supported.')
    warnings = ['Non-event components (tasks, availability or journals) were ignored.'] if ignored else []
    return header, events, tzlines, warnings


class Times:
    def __init__(self, header, tzlines, fallback):
        self.fallback = ZoneInfo(fallback)
        self.custom = {}
        if tzlines:
            try:
                parsed = tzical(StringIO('\r\n'.join(tzlines)))
                self.custom = {key:parsed.get(key) for key in parsed.keys()}
            except Exception:
                raise ICalError('Embedded VTIMEZONE could not be read.') from None
        floating = one(header, 'X-WR-TIMEZONE')
        if floating:
            self.fallback = self.zone(text(floating.value))

    def zone(self, name):
        if name in self.custom:
            return self.custom[name]
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ICalError('Unknown TZID; supply a valid timezone or embedded VTIMEZONE.') from None

    def parse(self, p):
        value = p.value
        if p.params.get('VALUE', '').upper() == 'DATE' or re.fullmatch(r'\d{8}', value):
            if not re.fullmatch(r'\d{8}', value):
                raise ICalError('Invalid all-day date.')
            result = datetime.strptime(value, '%Y%m%d').date()
        else:
            if not re.fullmatch(r'\d{8}T\d{6}Z?', value):
                raise ICalError('Invalid date-time; expected basic iCalendar date/time syntax.')
            if p.params.get('TZID') and value.endswith('Z'):
                raise ICalError('UTC date-time must not also have a TZID.')
            naive = datetime.strptime(value.rstrip('Z'), '%Y%m%dT%H%M%S')
            zone = UTC if value.endswith('Z') else self.zone(p.params['TZID']) if 'TZID' in p.params else self.fallback
            # fold=0 is the first occurrence of an ambiguous autumn clock time.
            result = naive.replace(tzinfo=zone, fold=0)
            if not datetime_exists(result):
                raise ICalError('An explicit event time falls in a daylight-saving gap; correct it at the source.')
        if not 1900 <= result.year <= 2199:
            raise ICalError('Event dates must be between 1900 and 2199.')
        return result


def is_day(value):
    return isinstance(value, date) and not isinstance(value, datetime)


def key(value):
    return ('date:' + value.isoformat()) if is_day(value) else ('time:' + value.astimezone(UTC).isoformat())


def delta_parse(value):
    match = re.fullmatch(r'\+?P(?:(\d+)W|(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?)', value)
    if not match or not any(g is not None for g in match.groups()):
        raise ICalError('Unsupported or negative DURATION.')
    w, d, h, m, s = [int(x or 0) for x in match.groups()]
    if max(w, d, h, m, s) > 40000000:
        raise ICalError('Event duration limit exceeded.')
    return timedelta(days=w*7+d), timedelta(hours=h, minutes=m, seconds=s)


def length(props, a, times):
    end, duration = one(props, 'DTEND'), one(props, 'DURATION')
    if end and duration:
        raise ICalError('DTEND and DURATION cannot both be specified.')
    if end:
        b = times.parse(end)
        if is_day(a) != is_day(b):
            raise ICalError('Start and end types must match.')
        delta = b-a if is_day(a) else b.astimezone(UTC)-a.astimezone(UTC)
        nominal = timedelta(0)
    elif duration:
        nominal, delta = delta_parse(duration.value)
        if is_day(a) and delta:
            raise ICalError('An all-day duration must use whole days or weeks.')
    else:
        nominal, delta = (timedelta(days=1), timedelta(0)) if is_day(a) else (timedelta(0), timedelta(0))
    if delta + nominal < timedelta(0) or delta + nominal > timedelta(days=366):
        raise ICalError('Invalid duration or event spans more than 366 days.')
    if is_day(a) and delta + nominal <= timedelta(0):
        raise ICalError('An all-day event must last at least one day (exclusive end).')
    return nominal, delta


def end_at(a, duration):
    nominal, exact = duration
    b = a + nominal
    return b+exact if is_day(a) else (b.astimezone(UTC)+exact).astimezone(a.tzinfo)


def overlaps(a, b, left, right, zone):
    if is_day(a):
        l, r = left.astimezone(zone).date(), right.astimezone(zone).date()
        return a < r and b > l
    return a < right and (b > left or (a == b and a >= left))


def rule_dates(p, a, low, high):
    value = p.value.upper()
    parts = dict(token.split('=', 1) for token in value.split(';'))
    if len(parts) != len(value.split(';')):
        raise ICalError('Duplicate RRULE part.')
    if parts.get('FREQ') not in ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'):
        raise ICalError('Only daily, weekly, monthly and yearly recurrence frequencies are supported.')
    if 'RSCALE' in parts or 'SKIP' in parts or ('COUNT' in parts and 'UNTIL' in parts):
        raise ICalError('Unsupported recurrence rule.')
    if int(parts.get('INTERVAL', '1')) < 1:
        raise ICalError('RRULE interval must be positive.')
    count = int(parts.pop('COUNT')) if 'COUNT' in parts else None
    if count is not None and not 1 <= count <= MAX_STEPS:
        raise ICalError('Recurrence count exceeds the supported limit.')
    all_day = is_day(a)
    start = datetime.combine(a, datetime.min.time()) if all_day else a
    lo = datetime.combine(low.date(), datetime.min.time()) if all_day else low
    hi = datetime.combine(high.date(), datetime.min.time()) if all_day else high
    until = parts.get('UNTIL')
    if until and not all_day and not until.endswith('Z'):
        # Floating UNTIL is interpreted in the DTSTART zone, then made explicit.
        if not re.fullmatch(r'\d{8}T\d{6}', until):
            raise ICalError('Timed RRULE UNTIL must be a date-time.')
        parts['UNTIL'] = datetime.strptime(until, '%Y%m%dT%H%M%S').replace(tzinfo=start.tzinfo).astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')
    r = rrulestr(';'.join(f'{k}={v}' for k,v in parts.items()), dtstart=start, cache=False)
    # COUNT is applied after excluding nonexistent clock times, as RFC 5545
    # requires. Without COUNT, xafter skips old dates without materialising them.
    iterator = iter(r) if count is not None else r.xafter(lo, inc=True)
    valid, steps = 0, 0
    for dt in iterator:
        steps += 1
        if steps > MAX_STEPS:
            raise ICalError('Recurrence expansion limit exceeded.')
        if dt >= hi:
            break
        if not all_day and not datetime_exists(dt):
            continue
        valid += 1
        if count is not None and valid > count:
            break
        if dt >= lo:
            yield dt.date() if all_day else dt


def occurrences(props, a, times, left, right, duration):
    if 'EXRULE' in props:
        raise ICalError('Legacy EXRULE is unsupported; use EXDATE instead.')
    excluded = set()
    for prop in props.get('EXDATE', []):
        for val in prop.value.split(','):
            d = times.parse(Prop(prop.params, val))
            if is_day(d) != is_day(a):
                raise ICalError('EXDATE and DTSTART types must match.')
            excluded.add(key(d))
    added = {key(a):a}
    for prop in props.get('RDATE', []):
        if prop.params.get('VALUE', '').upper() == 'PERIOD' or '/' in prop.value:
            raise ICalError('RDATE PERIOD is unsupported; use dated VEVENT instances.')
        for val in prop.value.split(','):
            d = times.parse(Prop(prop.params, val))
            if is_day(d) != is_day(a):
                raise ICalError('RDATE and DTSTART types must match.')
            added[key(d)] = d
    rule = one(props, 'RRULE')
    if rule:
        # Include starts before the window whose long/overnight events overlap it.
        low = left - sum(duration, timedelta(0)) - timedelta(days=2)
        high = right + timedelta(days=2)
        for d in rule_dates(rule, a, low, high):
            added[key(d)] = d
            if len(added) > MAX_EVENTS:
                raise ICalError('Too many expanded occurrences; previous data retained.')
    return [d for k,d in added.items() if k not in excluded]


def parse_calendar(data: bytes, start: str, stop: str, fallback: str, display_zone: str):
    """Return normalised event records, preserving source UID for deduplication."""
    try:
        return _parse(data, start, stop, fallback, display_zone)
    except ICalError:
        raise
    except Exception:
        raise ICalError('Invalid or unsupported iCalendar data; previous data retained.') from None


def _parse(data, start, stop, fallback, display_zone):
    header, events, tzlines, warnings = read_components(data)
    times = Times(header, tzlines, fallback)
    left, right = datetime.fromisoformat(start), datetime.fromisoformat(stop)
    if not left.tzinfo or not right.tzinfo or right <= left or right-left > timedelta(days=1600):
        raise ICalError('Invalid bounded query window.')
    zone = ZoneInfo(display_zone)
    groups = {}
    for props in events:
        uid = text(one(props, 'UID', True).value)
        if not uid or len(uid) > 1024:
            raise ICalError('Missing or oversized event UID.')
        rid_prop = one(props, 'RECURRENCE-ID')
        if rid_prop and rid_prop.params.get('RANGE'):
            raise ICalError('RECURRENCE-ID RANGE (this and future) is not supported; use fully expanded exports.')
        rid = times.parse(rid_prop) if rid_prop else None
        identity = key(rid) if rid is not None else ''
        seq = one(props, 'SEQUENCE')
        stamp = one(props, 'LAST-MODIFIED') or one(props, 'DTSTAMP')
        stamp_key = key(times.parse(stamp)) if stamp else ''
        priority = (int(seq.value) if seq else 0, stamp_key)
        group = groups.setdefault(uid, {})
        old = group.get(identity)
        if old and priority == old[0] and props != old[1]:
            raise ICalError('Conflicting duplicate UID/revision in feed.')
        if old is None or priority >= old[0]:
            group[identity] = (priority, props, rid)
    result = []
    def emit(uid, props, a, duration, original):
        b = end_at(a, duration)
        if not overlaps(a, b, left, right, zone):
            return
        summary = one(props, 'SUMMARY')
        visibility = one(props, 'CLASS')
        categories = []
        for p in props.get('CATEGORIES', []):
            categories.extend(text_list(p.value))
        raw = {'id':hashlib.sha256((uid+'\0'+key(original)).encode()).hexdigest(), 'iCalUID':uid,
               'summary':text(summary.value)[:4096] if summary else 'Busy',
               'categories':categories[:50],
               'visibility':'private' if visibility and visibility.value.upper() in ('PRIVATE','CONFIDENTIAL') else 'default',
               'start':{'date':a.isoformat()} if is_day(a) else {'dateTime':a.isoformat()},
               'end':{'date':b.isoformat()} if is_day(b) else {'dateTime':b.isoformat()}}
        result.append(raw)
        if len(result) > MAX_EVENTS:
            raise ICalError('Expanded feed exceeds the 6000 occurrence limit.')
    for uid, versions in groups.items():
        master = versions.get('')
        overrides = {k:v for k,v in versions.items() if k}
        master_props, master_a, duration = None, None, None
        if master:
            master_props = master[1]
            status = one(master_props, 'STATUS')
            if status and status.value.upper() == 'CANCELLED':
                continue
            master_a = times.parse(one(master_props, 'DTSTART', True))
            duration = length(master_props, master_a, times)
            for a in occurrences(master_props, master_a, times, left, right, duration):
                if key(a) not in overrides:
                    emit(uid, master_props, a, duration, a)
        for _, props, rid in overrides.values():
            status = one(props, 'STATUS')
            if status and status.value.upper() == 'CANCELLED':
                continue
            a = times.parse(one(props, 'DTSTART', True))
            if is_day(a) != is_day(rid) or (master_a is not None and is_day(a) != is_day(master_a)):
                raise ICalError('Recurrence override date types do not match the master.')
            if 'RRULE' in props or 'RDATE' in props:
                raise ICalError('Recurring overrides are unsupported.')
            merged = {**(master_props or {}), **props}
            own_length = length(props, a, times) if 'DTEND' in props or 'DURATION' in props or duration is None else duration
            emit(uid, merged, a, own_length, rid)
    result.sort(key=lambda r: r['start'].get('dateTime', r['start'].get('date')))
    if not events:
        warnings.append('The feed is valid but contains no VEVENT records. An empty feed does not confirm days off.')
    return {'items':result, 'warnings':warnings}
