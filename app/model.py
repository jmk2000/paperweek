"""Calendar semantics, independent of Google, LVGL, and desktop libraries."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import unicodedata

COLOURS = ("blue", "red", "green", "black", "yellow")
MAX_CALENDARS = 6
MAX_ITEMS = 6


@dataclass(frozen=True)
class Calendar:
    id: str
    label: str
    colour: str = "blue"
    mask_titles: bool = False

    def __post_init__(self) -> None:
        if not self.id or not self.label.strip():
            raise ValueError("Calendar ID and label must not be empty.")
        if self.colour not in COLOURS:
            raise ValueError(f"Unknown colour: {self.colour}")


@dataclass(frozen=True)
class Event:
    key: str
    calendar_id: str
    title: str
    start: datetime | date
    end: datetime | date   # Exclusive, including for all-day events.
    all_day: bool

    def to_json(self) -> dict:
        return {**asdict(self), "start": self.start.isoformat(), "end": self.end.isoformat()}

    @classmethod
    def from_json(cls, data: dict) -> Event:
        parser = date.fromisoformat if data["all_day"] else datetime.fromisoformat
        return cls(**{**data, "start": parser(data["start"]), "end": parser(data["end"])})


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def at_midnight(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=zone)


def parse_google_time(value: dict, fallback_zone: ZoneInfo) -> datetime:
    result = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
    if result.tzinfo is None:
        # Google's API normally returns an offset. Accept documented timezone fields too.
        result = result.replace(tzinfo=ZoneInfo(value.get("timeZone", fallback_zone.key)))
    return result


def normalise_google_event(raw: dict, cal: Calendar, zone: ZoneInfo,
                           mask_private: bool = True) -> Event | None:
    """The API expands recurrence; this adapter handles each occurrence independently."""
    if raw.get("status") == "cancelled":
        return None
    if any(a.get("self") and a.get("responseStatus") == "declined"
           for a in raw.get("attendees", [])):
        return None
    start, end = raw.get("start", {}), raw.get("end", {})
    all_day = "date" in start
    if all_day:
        if "date" not in end:
            raise ValueError("All-day event has no end date.")
        begin, finish = date.fromisoformat(start["date"]), date.fromisoformat(end["date"])
    else:
        if "dateTime" not in start or "dateTime" not in end:
            raise ValueError("Timed event has no start/end time.")
        begin, finish = parse_google_time(start, zone), parse_google_time(end, zone)
    if finish < begin:
        raise ValueError("Event ends before it starts.")
    title = str(raw.get("summary") or "Busy")
    if cal.mask_titles or (mask_private and raw.get("visibility") == "private"):
        title = "Busy"
    # Occurrences share iCalUID, so include occurrence start in the identity.
    key = str(raw.get("iCalUID") or f'{cal.id}:{raw.get("id", "unknown")}') + "|" + begin.isoformat()
    return Event(key, cal.id, title, begin, finish, all_day)


def overlaps_day(event: Event, day: date, zone: ZoneInfo) -> bool:
    if event.all_day:
        return event.start <= day < event.end
    start, end = event.start.astimezone(zone), event.end.astimezone(zone)
    lo, hi = at_midnight(day, zone), at_midnight(day + timedelta(days=1), zone)
    if start == end:
        return lo <= start < hi
    return start < hi and end > lo


def readable_ascii(text: object, limit: int = 160) -> str:
    """Built-in LVGL fonts are ASCII-focused. Never pass controls into our wire format."""
    translations = str.maketrans({"–": "-", "—": "-", "’": "'", "‘": "'", "“": '"',
                                 "”": '"', "…": "...", "→": ">", "←": "<", "•": "/",
                                 "ß": "ss", "ø": "o", "Ø": "O", "æ": "ae", "œ": "oe"})
    source = unicodedata.normalize("NFKD", str(text).translate(translations))
    source = "".join(c for c in source if not unicodedata.combining(c))
    source = " ".join(source.split())
    source = "".join(c if 32 <= ord(c) < 127 else "?" for c in source)
    return source if len(source) <= limit else source[:limit - 3] + "..."


def day_label(day: date) -> str:
    return f"{day.day} {day.strftime('%b')}"


def build_view(events: list[Event], calendars: list[Calendar], week: date, now: datetime,
               zone: ZoneInfo, title: str = "Our week", status: str = "",
               stale: bool = False, mode: str = "demo", deduplicate: bool = True) -> dict:
    week = monday(week)
    now = now.astimezone(zone)
    last = week + timedelta(days=6)
    by_id = {c.id: c for c in calendars}
    if len(calendars) > MAX_CALENDARS:
        raise ValueError(f"At most {MAX_CALENDARS} calendars can be displayed.")
    if len(by_id) != len(calendars):
        raise ValueError("Calendar IDs must be unique.")
    selected = []
    seen = set()
    # Calendar order resolves duplicate invitations, not the arbitrary API order.
    for cal in calendars:
        for event in events:
            if event.calendar_id != cal.id:
                continue
            if deduplicate and event.key in seen:
                continue
            seen.add(event.key)
            selected.append(event)

    days = []
    for i in range(7):
        day = week + timedelta(days=i)
        matching = [e for e in selected if overlaps_day(e, day, zone)]
        def order(e: Event) -> tuple:
            return (0, "", e.title) if e.all_day else (1, e.start.astimezone(timezone.utc).isoformat(), e.title)
        matching.sort(key=order)
        entries = []
        for event in matching[:MAX_ITEMS]:
            cal = by_id[event.calendar_id]
            if event.all_day:
                when = "ALL DAY"
            else:
                start, end = event.start.astimezone(zone), event.end.astimezone(zone)
                if start.date() < day:
                    when = "Until " + end.strftime("%H:%M") if end.date() == day else "Continues"
                else:
                    when = start.strftime("%H:%M")
                    if end > at_midnight(day + timedelta(days=1), zone):
                        when += " >"
            entries.append({"time": when, "title": event.title, "owner": cal.label,
                            "colour": cal.colour, "all_day": event.all_day})
        days.append({"dow": day.strftime("%a").upper(), "number": str(day.day),
                     "month": day.strftime("%b").upper(), "today": day == now.date(),
                     "items": entries, "overflow": max(0, len(matching) - MAX_ITEMS)})
    month = week.strftime("%B %Y") if week.month == last.month else (
        f"{week.strftime('%b')} / {last.strftime('%b %Y')}" if week.year == last.year else
        f"{week.strftime('%b %Y')} / {last.strftime('%b %Y')}")
    upcoming = [e for e in selected if not e.all_day and e.start >= now]
    upcoming.sort(key=lambda e: e.start.astimezone(timezone.utc))
    if upcoming:
        nxt = upcoming[0]
        start = nxt.start.astimezone(zone)
        footer = f"NEXT  /  {start.strftime('%a')} {start.day} {start.strftime('%b %H:%M')}  /  {nxt.title}"
    else:
        footer = "A little room to plan.  /  No upcoming timed events in the loaded week."
    return {"title": title, "month": month, "span": f"{day_label(week)} - {day_label(last)}",
            "week_number": f"WEEK {week.isocalendar().week:02}",
            "today": f"{now.strftime('%A').upper()}  /  {now.day} {now.strftime('%b').upper()}",
            "timezone": zone.key, "mode": mode,
            "calendars": [asdict(c) for c in calendars], "days": days,
            "footer": footer, "status": status, "stale": stale}


def encode_view(view: dict) -> str:
    """Simple bounded tab-separated records; no JSON parser needed in firmware."""
    def row(kind: str, *values: object) -> str:
        return "\t".join([kind] + [readable_ascii(v, 240) for v in values])
    lines = ["PAPERWEEK1", row("META", view["title"], view["month"], view["span"],
        view["week_number"], view["today"], view["timezone"], view["mode"])]
    for i, cal in enumerate(view["calendars"]):
        lines.append(row("LEGEND", i, cal["label"], cal["colour"]))
    for i, day in enumerate(view["days"]):
        lines.append(row("DAY", i, day["dow"], day["number"], int(day["today"]), day["month"]))
        for item in day["items"]:
            lines.append(row("EVENT", i, item["time"], item["title"], item["owner"],
                             item["colour"], int(item["all_day"])))
        lines.append(row("OVERFLOW", i, day["overflow"]))
    lines += [row("FOOTER", view["footer"]), row("STATUS", view["status"], int(view["stale"]))]
    return "\n".join(lines) + "\n"
