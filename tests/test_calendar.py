from __future__ import annotations
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.model import (Calendar, Event, monday, at_midnight, normalise_google_event,
                       overlaps_day, build_view, encode_view, readable_ascii)
from app.google_source import GoogleCalendarSource, CalendarError
from app.storage import atomic_write, cache_key, DEFAULT_CONFIG, read_config
from app.cli import save_snapshot, load_snapshot, build_display, fetch_snapshot
from app.export import ppm_to_png
from app import demo

ZONE = ZoneInfo("Europe/London")
CAL = Calendar("test@example.test", "Test", "blue")
WEEK = date(2026, 8, 31)
NOW = datetime(2026, 9, 5, 10, 30, tzinfo=ZONE)


def raw_event(**overrides):
    data = {"id": "one", "iCalUID": "one@example.test", "summary": "Swimming",
            "start": {"dateTime": "2026-09-05T16:30:00+01:00"},
            "end": {"dateTime": "2026-09-05T17:30:00+01:00"}}
    data.update(overrides)
    return data


class CalendarSemantics(unittest.TestCase):
    def test_monday_and_year_boundary(self):
        self.assertEqual(monday(date(2027, 1, 1)), date(2026, 12, 28))

    def test_cancelled_event_omitted(self):
        self.assertIsNone(normalise_google_event(raw_event(status="cancelled"), CAL, ZONE))

    def test_declined_event_omitted(self):
        self.assertIsNone(normalise_google_event(raw_event(attendees=[{"self": True, "responseStatus": "declined"}]), CAL, ZONE))

    def test_someone_else_declining_does_not_hide_event(self):
        self.assertIsNotNone(normalise_google_event(raw_event(attendees=[{"self": False, "responseStatus": "declined"}]), CAL, ZONE))

    def test_private_title_redacted(self):
        event = normalise_google_event(raw_event(visibility="private", summary="Secret title"), CAL, ZONE)
        self.assertEqual(event.title, "Busy")
        self.assertNotIn("Secret", json.dumps(event.to_json()))

    def test_explicit_private_opt_in(self):
        self.assertEqual(normalise_google_event(raw_event(visibility="private"), CAL, ZONE, False).title, "Swimming")

    def test_whole_calendar_mask(self):
        masked = Calendar(CAL.id, "Work", "red", True)
        self.assertEqual(normalise_google_event(raw_event(), masked, ZONE).title, "Busy")

    def test_title_missing_is_busy(self):
        self.assertEqual(normalise_google_event(raw_event(summary=None), CAL, ZONE).title, "Busy")

    def test_all_day_end_exclusive(self):
        event = normalise_google_event(raw_event(start={"date": "2026-09-04"}, end={"date": "2026-09-06"}), CAL, ZONE)
        self.assertTrue(overlaps_day(event, date(2026, 9, 4), ZONE))
        self.assertTrue(overlaps_day(event, date(2026, 9, 5), ZONE))
        self.assertFalse(overlaps_day(event, date(2026, 9, 6), ZONE))

    def test_midnight_end_does_not_spill(self):
        event = normalise_google_event(raw_event(start={"dateTime": "2026-09-05T22:00:00+01:00"},
             end={"dateTime": "2026-09-06T00:00:00+01:00"}), CAL, ZONE)
        self.assertTrue(overlaps_day(event, date(2026, 9, 5), ZONE))
        self.assertFalse(overlaps_day(event, date(2026, 9, 6), ZONE))

    def test_overnight_event_on_both_days(self):
        event = normalise_google_event(raw_event(start={"dateTime": "2026-09-05T23:00:00+01:00"},
             end={"dateTime": "2026-09-06T02:00:00+01:00"}), CAL, ZONE)
        view = build_view([event], [CAL], WEEK, NOW, ZONE)
        self.assertEqual(view["days"][5]["items"][0]["time"], "23:00 >")
        self.assertEqual(view["days"][6]["items"][0]["time"], "Until 02:00")

    def test_zero_duration_event_visible(self):
        event = normalise_google_event(raw_event(end={"dateTime": "2026-09-05T16:30:00+01:00"}), CAL, ZONE)
        self.assertTrue(overlaps_day(event, date(2026, 9, 5), ZONE))

    def test_spring_clock_change(self):
        event = normalise_google_event(raw_event(start={"dateTime": "2026-03-29T01:30:00Z"},
             end={"dateTime": "2026-03-29T02:30:00Z"}), CAL, ZONE)
        view = build_view([event], [CAL], date(2026, 3, 23), NOW, ZONE)
        self.assertEqual(view["days"][6]["items"][0]["time"], "02:30")

    def test_autumn_clock_change(self):
        first = normalise_google_event(raw_event(start={"dateTime": "2026-10-25T00:30:00Z"},
             end={"dateTime": "2026-10-25T00:45:00Z"}), CAL, ZONE)
        second = normalise_google_event(raw_event(id="two", iCalUID="two", start={"dateTime": "2026-10-25T01:30:00Z"},
             end={"dateTime": "2026-10-25T01:45:00Z"}), CAL, ZONE)
        self.assertNotEqual(first.start, second.start)
        view = build_view([second, first], [CAL], date(2026, 10, 19), NOW, ZONE)
        self.assertEqual(len(view["days"][6]["items"]), 2)
        self.assertEqual([x["time"] for x in view["days"][6]["items"]], ["01:30", "01:30"])

    def test_dst_week_query_bounds_have_different_offsets(self):
        self.assertTrue(at_midnight(date(2026, 3, 23), ZONE).isoformat().endswith("+00:00"))
        self.assertTrue(at_midnight(date(2026, 3, 30), ZONE).isoformat().endswith("+01:00"))

    def test_recurrence_instances_have_distinct_keys(self):
        one = normalise_google_event(raw_event(), CAL, ZONE)
        two = normalise_google_event(raw_event(start={"dateTime": "2026-09-12T16:30:00+01:00"},
            end={"dateTime": "2026-09-12T17:30:00+01:00"}), CAL, ZONE)
        self.assertNotEqual(one.key, two.key)

    def test_duplicate_shared_invitation_optional(self):
        other = Calendar("partner", "Partner", "red")
        one = normalise_google_event(raw_event(), CAL, ZONE)
        two = normalise_google_event(raw_event(), other, ZONE)
        view = build_view([two, one], [CAL, other], WEEK, NOW, ZONE)
        self.assertEqual(len(view["days"][5]["items"]), 1)
        self.assertEqual(view["days"][5]["items"][0]["owner"], "Test")
        view = build_view([two, one], [CAL, other], WEEK, NOW, ZONE, deduplicate=False)
        self.assertEqual(len(view["days"][5]["items"]), 2)

    def test_overflow_is_explicit(self):
        events = [normalise_google_event(raw_event(id=str(i), iCalUID=str(i)), CAL, ZONE) for i in range(10)]
        view = build_view(events, [CAL], WEEK, NOW, ZONE)
        self.assertEqual(len(view["days"][5]["items"]), 6)
        self.assertEqual(view["days"][5]["overflow"], 4)

    def test_all_day_sorted_before_timed(self):
        events = [normalise_google_event(raw_event(), CAL, ZONE), normalise_google_event(
            raw_event(iCalUID="birthday", start={"date": "2026-09-05"}, end={"date": "2026-09-06"}), CAL, ZONE)]
        self.assertEqual(build_view(events, [CAL], WEEK, NOW, ZONE)["days"][5]["items"][0]["time"], "ALL DAY")

    def test_invalid_end_rejected(self):
        with self.assertRaises(ValueError):
            normalise_google_event(raw_event(end={"dateTime": "2026-09-04T10:00:00Z"}), CAL, ZONE)

    def test_malformed_event_not_silently_skipped(self):
        with self.assertRaises(ValueError):
            normalise_google_event(raw_event(start={}), CAL, ZONE)

    def test_ascii_and_control_sanitisation(self):
        self.assertEqual(readable_ascii("Cécile’s\tparty\n→ home"), "Cecile's party > home")
        self.assertTrue(readable_ascii("🎂 birthday").isascii())
        self.assertLessEqual(len(readable_ascii("a" * 200)), 160)

    def test_view_protocol_always_seven_days(self):
        encoded = encode_view(build_view(demo.events_for(WEEK, ZONE), demo.CALENDARS, WEEK, NOW, ZONE))
        self.assertEqual(sum(line.startswith("DAY\t") for line in encoded.splitlines()), 7)
        self.assertTrue(encoded.isascii())

    def test_event_round_trip(self):
        original = normalise_google_event(raw_event(), CAL, ZONE)
        self.assertEqual(Event.from_json(original.to_json()), original)

    def test_bad_colour_and_duplicate_calendars_rejected(self):
        with self.assertRaises(ValueError): Calendar("x", "X", "purple")
        with self.assertRaises(ValueError): build_view([], [CAL, CAL], WEEK, NOW, ZONE)


class FakeResponse:
    def __init__(self, data=None, status=200): self.data, self.status_code = data or {}, status
    def json(self): return self.data


class FakeSession:
    def __init__(self, responses): self.responses, self.calls = list(responses), []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class GoogleAdapterTests(unittest.TestCase):
    def test_empty_page_with_next_token_still_followed(self):
        session = FakeSession([FakeResponse({"items": [], "nextPageToken": "second"}),
                               FakeResponse({"items": [raw_event()]})])
        events = GoogleCalendarSource(session).events([CAL], WEEK, ZONE)
        self.assertEqual(len(events), 1)
        self.assertEqual(session.calls[1][1]["params"]["pageToken"], "second")

    def test_recurrence_expansion_readonly_get_and_encoded_id(self):
        session = FakeSession([FakeResponse()])
        GoogleCalendarSource(session).events([CAL], WEEK, ZONE)
        url, options = session.calls[0]
        self.assertIn("test%40example.test", url)
        self.assertEqual(options["params"]["singleEvents"], "true")
        self.assertEqual(options["params"]["showDeleted"], "false")
        self.assertNotIn("description", options["params"]["fields"])
        self.assertNotIn("location", options["params"]["fields"])

    def test_calendar_pagination_and_access_filter(self):
        session = FakeSession([FakeResponse({"items": [{"id": "a", "accessRole": "reader"}], "nextPageToken": "x"}),
           FakeResponse({"items": [{"id": "b", "accessRole": "freeBusyReader"}, {"id": "c", "accessRole": "owner"}]})])
        self.assertEqual([c["id"] for c in GoogleCalendarSource(session).calendars()], ["a", "c"])

    def test_transient_failure_retried(self):
        session = FakeSession([FakeResponse(status=503), FakeResponse({"items": [raw_event()]})])
        sleeps = []
        self.assertEqual(len(GoogleCalendarSource(session, sleeper=sleeps.append).events([CAL], WEEK, ZONE)), 1)
        self.assertEqual(sleeps, [1])

    def test_permission_failure_does_not_return_partial_week(self):
        session = FakeSession([FakeResponse({"items": [raw_event()]}), FakeResponse(status=403)])
        with self.assertRaises(CalendarError):
            GoogleCalendarSource(session).events([CAL, Calendar("b", "B")], WEEK, ZONE)

    def test_repeated_page_token_rejected(self):
        session = FakeSession([FakeResponse({"nextPageToken": "x"}), FakeResponse({"nextPageToken": "x"})])
        with self.assertRaises(CalendarError): list(GoogleCalendarSource(session).pages("/test", {}))

    def test_bad_event_fails_refresh(self):
        session = FakeSession([FakeResponse({"items": [raw_event(start={})]})])
        with self.assertRaises(CalendarError): GoogleCalendarSource(session).events([CAL], WEEK, ZONE)

    def test_error_body_never_disclosed(self):
        session = FakeSession([FakeResponse({"error": "SECRET_ACCESS_TOKEN"}, status=401)])
        with self.assertRaises(CalendarError) as caught: GoogleCalendarSource(session).calendars()
        self.assertNotIn("SECRET", str(caught.exception))


class LocalStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.dict(os.environ, {"PAPERWEEK_DATA_DIR": self.tmp.name})
        self.patch.start()
        self.config = {**DEFAULT_CONFIG, "calendars": [{"id": CAL.id, "label": CAL.label, "colour": CAL.colour, "mask_titles": False}]}
    def tearDown(self): self.patch.stop(); self.tmp.cleanup()

    def test_files_private_and_atomic(self):
        path = Path(self.tmp.name) / "test.txt"
        atomic_write(path, "first")
        atomic_write(path, "second")
        self.assertEqual(path.read_text(), "second")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_privacy_change_invalidates_cache_key(self):
        key = cache_key(self.config, WEEK.isoformat())
        self.assertNotEqual(key, cache_key({**self.config, "mask_private": False}, WEEK.isoformat()))

    def test_week_change_does_not_reuse_old_events(self):
        events = [normalise_google_event(raw_event(), CAL, ZONE)]
        save_snapshot(self.config, WEEK, events, NOW)
        self.assertIsNone(load_snapshot(self.config, WEEK + timedelta(days=7)))
        self.assertEqual(load_snapshot(self.config, WEEK)[0], events)

    def test_cache_contains_redacted_events_only(self):
        events = [normalise_google_event(raw_event(visibility="private", summary="Private detail"), CAL, ZONE)]
        save_snapshot(self.config, WEEK, events, NOW)
        contents = next((Path(self.tmp.name) / "cache").glob("*.json")).read_text()
        self.assertNotIn("Private detail", contents)
        self.assertIn("Busy", contents)

    def test_failed_refresh_preserves_previous_snapshot(self):
        events = [normalise_google_event(raw_event(), CAL, ZONE)]
        save_snapshot(self.config, WEEK, events, NOW)
        session = FakeSession([FakeResponse(status=403)])
        with self.assertRaises(CalendarError):
            fetch_snapshot(GoogleCalendarSource(session), self.config, WEEK, [CAL], ZONE)
        self.assertEqual(load_snapshot(self.config, WEEK)[0], events)

    def test_unavailable_is_not_empty_calendar(self):
        wire = build_display(self.config, "google", [CAL], WEEK, ZONE, None, fetching=True)
        self.assertIn("unavailable", wire)
        self.assertIn("This is not an empty schedule", wire)
        self.assertNotIn("DEMO", wire)

    def test_invalid_config_poll_rejected(self):
        atomic_write(Path(self.tmp.name) / "config.json", json.dumps({"poll_seconds": 1}))
        with self.assertRaises(ValueError): read_config()

    def test_png_dimensions_pixels_crc_and_physical_size(self):
        ppm = Path(self.tmp.name) / "frame.ppm"
        rgb = bytes([20, 30, 40]) * (1600 * 1200)
        ppm.write_bytes(b"P6\n1600 1200\n255\n" + rgb)
        png = Path(self.tmp.name) / "frame.png"
        ppm_to_png(ppm, png)
        data = png.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        chunks = {}
        pos = 8
        while pos < len(data):
            n = struct.unpack(">I", data[pos:pos+4])[0]
            kind, payload = data[pos+4:pos+8], data[pos+8:pos+8+n]
            crc = struct.unpack(">I", data[pos+8+n:pos+12+n])[0]
            self.assertEqual(crc, zlib.crc32(kind + payload) & 0xffffffff)
            chunks[kind] = payload
            pos += 12+n
        self.assertEqual(struct.unpack(">II", chunks[b"IHDR"][:8]), (1600, 1200))
        self.assertEqual(struct.unpack(">IIB", chunks[b"pHYs"]), (5917, 5917, 1))
        self.assertEqual(len(zlib.decompress(chunks[b"IDAT"])), 1200 * (1 + 1600 * 3))


if __name__ == "__main__": unittest.main()
