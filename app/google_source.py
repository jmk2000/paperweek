"""Read-only Calendar API adapter. Authentication is only imported when needed."""
from __future__ import annotations
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote
import time
from .model import Calendar, Event, at_midnight, normalise_google_event

API_ROOT = "https://www.googleapis.com/calendar/v3"
SCOPES = ["https://www.googleapis.com/auth/calendar.events.readonly",
          "https://www.googleapis.com/auth/calendar.calendarlist.readonly"]


class CalendarError(RuntimeError):
    """Safe, user-facing error text; never include response bodies or tokens."""


class GoogleCalendarSource:
    def __init__(self, session, persist=lambda: None, sleeper=time.sleep):
        self.session = session
        self.persist = persist
        self.sleeper = sleeper

    def get(self, path: str, params: dict) -> dict:
        for attempt in range(3):
            try:
                response = self.session.get(API_ROOT + path, params=params, timeout=(5, 25))
            except Exception as exc:
                # Google authentication libraries have their own transport exceptions.
                # Don't log exception messages: they can contain request URLs and identifiers.
                raise CalendarError("Connection or sign-in failed. Check internet access; reconnect if needed.") from None
            if response.status_code == 200:
                try:
                    result = response.json()
                except (ValueError, TypeError):
                    raise CalendarError("Google returned an unreadable response.") from None
                if not isinstance(result, dict):
                    raise CalendarError("Google returned an unexpected response.")
                self.persist()
                return result
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                self.sleeper(2 ** attempt)
                continue
            messages = {
                401: "Google sign-in expired. Close the preview and run ./run.sh connect.",
                403: "Google denied access. Check API enablement, Workspace policy, calendar access, and quota.",
                404: "A selected calendar is no longer available. Run ./run.sh connect to reselect calendars.",
                429: "Google rate limit reached. The last successful calendar will remain visible.",
            }
            raise CalendarError(messages.get(response.status_code, "Google Calendar is temporarily unavailable."))
        raise CalendarError("Google Calendar is temporarily unavailable.")

    def pages(self, path: str, params: dict):
        token = None
        seen = set()
        # Defensive bound also protects against accidental pagination loops.
        for _ in range(100):
            query = dict(params)
            if token:
                query["pageToken"] = token
            result = self.get(path, query)
            yield result
            token = result.get("nextPageToken")
            if not token:
                return
            if token in seen:
                raise CalendarError("Google repeated a pagination token; the refresh was not used.")
            seen.add(token)
        raise CalendarError("Too much calendar data for this prototype; narrow the selection.")

    def calendars(self) -> list[dict]:
        rows = []
        for result in self.pages("/users/me/calendarList", {
            "maxResults": 250, "showHidden": "false",
            "fields": "nextPageToken,items(id,summary,primary,accessRole,timeZone)"
        }):
            rows.extend(result.get("items", []))
        # Free/busy-only calendars need a different API. Do not imply we can read titles.
        return [r for r in rows if r.get("accessRole") in ("owner", "writer", "reader", "writerWithoutPrivateAccess")]

    def events(self, calendars: list[Calendar], week: date, zone: ZoneInfo,
               mask_private: bool = True) -> list[Event]:
        events = []
        for cal in calendars:
            parameters = {
                "timeMin": at_midnight(week, zone).isoformat(),
                "timeMax": at_midnight(week + timedelta(days=7), zone).isoformat(),
                "timeZone": zone.key, "singleEvents": "true", "orderBy": "startTime",
                "showDeleted": "false", "maxResults": 250,
                "fields": "nextPageToken,items(id,iCalUID,summary,status,visibility,start,end,attendees(self,responseStatus))",
            }
            for page in self.pages("/calendars/" + quote(cal.id, safe="") + "/events", parameters):
                for raw in page.get("items", []):
                    try:
                        event = normalise_google_event(raw, cal, zone, mask_private)
                    except (ValueError, TypeError, KeyError):
                        # Keep the previous good snapshot, rather than silently lose an event.
                        raise CalendarError("An event could not be interpreted. Refresh rejected; last good data retained.") from None
                    if event is not None:
                        events.append(event)
                    if len(events) > 20000:
                        raise CalendarError("Over 20,000 events in one week; narrow the calendar selection.")
        # Publish only after every selected calendar succeeded.
        return events
