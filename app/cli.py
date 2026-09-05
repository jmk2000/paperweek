"""Local launcher. Google fetching runs off the UI thread; the UI remains native C/LVGL."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from zoneinfo import ZoneInfo
from . import demo
from .model import Calendar, Event, COLOURS, build_view, encode_view, monday, readable_ascii
from .storage import ROOT, data_dir, atomic_write, read_config, write_config, cache_key
from .google_source import CalendarError
from .export import ppm_to_png


def cache_path(config: dict, week: date) -> Path:
    return data_dir() / "cache" / (cache_key(config, week.isoformat()) + ".json")


def save_snapshot(config: dict, week: date, events: list[Event], fetched_at: datetime) -> None:
    atomic_write(cache_path(config, week), json.dumps({
        "version": 1, "week": week.isoformat(), "fetched_at": fetched_at.isoformat(),
        "events": [e.to_json() for e in events]}, ensure_ascii=False))
    # Bound local retention. Only selected, redacted event fields are stored.
    paths = sorted((data_dir() / "cache").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in paths[12:]:
        old.unlink(missing_ok=True)


def load_snapshot(config: dict, week: date) -> tuple[list[Event], datetime] | None:
    path = cache_path(config, week)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if data["version"] != 1 or data["week"] != week.isoformat():
            return None
        return [Event.from_json(e) for e in data["events"]], datetime.fromisoformat(data["fetched_at"])
    except (ValueError, KeyError, TypeError, OSError):
        return None


def fetch_snapshot(source, config: dict, week: date, calendars: list[Calendar], zone: ZoneInfo):
    events = source.events(calendars, week, zone, config["mask_private"])
    fetched_at = datetime.now(timezone.utc)
    save_snapshot(config, week, events, fetched_at)
    return week, events, fetched_at


def connect(args) -> int:
    from .auth import source
    adapter = source(interactive=True, credentials_path=args.credentials)
    available = adapter.calendars()
    if not available:
        raise CalendarError("No readable calendars were found for this account.")
    print("\nChoose up to six calendars to SHOW. This selection is an application filter, not an OAuth permission boundary.")
    for n, cal in enumerate(available, 1):
        primary = " (primary)" if cal.get("primary") else ""
        print(f"  {n:2}. {cal.get('summary', 'Untitled calendar')}{primary}")
    while True:
        answer = input("\nCalendar numbers, separated by commas [1]: ").strip() or "1"
        try:
            numbers = list(dict.fromkeys(int(v.strip()) - 1 for v in answer.split(",")))
            if not 1 <= len(numbers) <= 6 or any(n < 0 or n >= len(available) for n in numbers):
                raise ValueError()
            break
        except ValueError:
            print("Enter between one and six valid numbers, for example 1,3,4.")
    selections = []
    for i, number in enumerate(numbers):
        raw = available[number]
        suggested = readable_ascii(raw.get("summary", "Calendar"), 24)
        label = input(f"Short display name for {suggested} [{suggested}]: ").strip() or suggested
        default_colour = COLOURS[i % len(COLOURS)]
        while True:
            colour = input(f"Colour: blue/red/green/black/yellow [{default_colour}]: ").strip().lower() or default_colour
            if colour in ("blue", "red", "green", "black", "yellow"):
                break
            print("Please use one of those five colour names.")
        mask = input("Show every event in this calendar as 'Busy'? [y/N]: ").strip().lower() in ("y", "yes")
        selections.append(asdict(Calendar(raw["id"], label, colour, mask)))
    config = read_config()
    config["calendars"] = selections
    config["title"] = input(f"Heading [{config['title']}]: ").strip() or config["title"]
    write_config(config)
    for cached in (data_dir() / "cache").glob("*.json"):
        cached.unlink(missing_ok=True)
    print("\nSaved. Run ./run.sh google to open your calendar.\nPrivate-marked event titles are hidden by default. No calendar write access was requested.")
    return 0


def build_display(config, mode, calendars, week, zone, snapshot, error="", fetching=False):
    now = datetime.now(zone)
    if mode == "demo":
        events = demo.events_for(week, zone)
        status = "DEMO / invented events / six items per day; longer titles shortened / " + zone.key
        available, stale = True, False
    else:
        available = snapshot is not None
        events, fetched_at = snapshot if available else ([], None)
        stale = not available or bool(error) or (now - fetched_at).total_seconds() > config["poll_seconds"] + 60
        if not available:
            status = "GOOGLE / " + ("LOADING - no calendar data yet" if fetching else "NOT LOADED - check Terminal")
        else:
            stamp = fetched_at.astimezone(zone).strftime("%a %d %b %H:%M")
            label = "OFFLINE OR SYNC ERROR" if error else ("CACHED - updating" if fetching else ("STALE" if stale else "GOOGLE / read-only"))
            status = f"{label} / last success {stamp} / {zone.key} / long titles shortened"
    view = build_view(events, calendars, week, now, zone, config["title"], status, stale,
                      mode if available else "unavailable", config["deduplicate"])
    if not available:
        view["footer"] = "Calendar not loaded. This is not an empty schedule."
    return encode_view(view)


def run_preview(args) -> int:
    config = read_config()
    zone = ZoneInfo(config["timezone"])
    mode = args.command
    calendars = demo.CALENDARS if mode == "demo" else [Calendar(**c) for c in config["calendars"]]
    if not calendars:
        raise CalendarError("Choose your calendars first: ./run.sh connect")
    binary = ROOT / "build" / "paperweek"
    if not binary.exists():
        raise CalendarError("The native preview has not been built. Run bash setup.sh.")
    follow_today = args.date is None
    week = monday(args.date or datetime.now(zone).date())
    adapter = None
    if mode == "google":
        from .auth import source
        try:
            adapter = source()
        except CalendarError as error:
            if not load_snapshot(config, week):
                raise
            print(str(error) + " Showing cached data only; close and reconnect to resume.", file=sys.stderr)
    snapshot = load_snapshot(config, week) if mode == "google" else None
    state = data_dir()
    view_path, ppm_path = state / "view.pwv", state / "export.ppm"
    initial_error = "Sign-in unavailable" if mode == "google" and adapter is None else ""
    atomic_write(view_path, build_display(config, mode, calendars, week, zone, snapshot, initial_error, bool(adapter)))
    command = [str(binary), "--view", str(view_path), "--export-path", str(ppm_path), "--scale", str(args.scale)]
    if args.clean:
        command += ["--clean"]
    if args.simulate_refresh:
        command += ["--simulate-refresh"]
    if args.export:
        if mode == "google":
            if adapter is None:
                raise CalendarError("Export requires a fresh Google fetch. Reconnect first.")
            _, events, stamp = fetch_snapshot(adapter, config, week, calendars, zone)
            snapshot = (events, stamp)
        atomic_write(view_path, build_display(config, mode, calendars, week, zone, snapshot))
        subprocess.run(command + ["--snapshot", str(ppm_path)], check=True)
        ppm_to_png(ppm_path, args.export.expanduser().resolve())
        ppm_path.unlink(missing_ok=True)
        print(f"Saved actual LVGL framebuffer: {args.export}")
        return 0

    print("\nPaperweek controls: Left/Right = week; T = today; R = sync; E = palette; D = 19s delay; F = full screen; S = PNG; Q = quit.")
    print("The monitor preview cannot reproduce physical e-paper colour or viewing conditions.\n")
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, text=True, bufsize=1)
    controls: queue.Queue[str] = queue.Queue()
    def receive() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            if line.startswith("PW:"):
                controls.put(line.strip()[3:])
    threading.Thread(target=receive, daemon=True).start()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="calendar-fetch")
    future: Future | None = None
    requested_week = None
    error = initial_error
    next_fetch = 0.0
    last_minute = ""
    published = ""
    dirty = True
    try:
        while proc.poll() is None:
            tick = time.monotonic()
            now = datetime.now(zone)
            minute = now.strftime("%Y-%m-%d %H:%M")
            if minute != last_minute:
                last_minute, dirty = minute, True
                if follow_today and monday(now.date()) != week:
                    week = monday(now.date())
                    snapshot = load_snapshot(config, week) if mode == "google" else None
                    next_fetch = 0
            while not controls.empty():
                action = controls.get_nowait()
                if action in ("previous", "next", "today"):
                    follow_today = action == "today"
                    week = monday(now.date()) if follow_today else week + timedelta(days=-7 if action == "previous" else 7)
                    snapshot = load_snapshot(config, week) if mode == "google" else None
                    error = initial_error
                    next_fetch = 0
                    dirty = True
                elif action == "refresh":
                    if future is None:
                        next_fetch = 0
                    dirty = True
                elif action == "exported":
                    target = ROOT / "exports" / ("paperweek-" + now.strftime("%Y%m%d-%H%M%S") + ".png")
                    ppm_to_png(ppm_path, target)
                    ppm_path.unlink(missing_ok=True)
                    print(f"Saved visible frame: {target}", flush=True)
            if future is not None and future.done():
                try:
                    got_week, events, fetched_at = future.result()
                    if got_week == week:
                        snapshot = (events, fetched_at)
                        error = ""
                        next_fetch = tick + config["poll_seconds"]
                        print(f"Google refresh complete: {len(events)} selected events. No event titles are logged.", flush=True)
                except Exception as exc:
                    if requested_week == week:
                        error = str(exc) if isinstance(exc, CalendarError) else "Local refresh/cache error. Check disk space and retry."
                        next_fetch = tick + 60
                        print(error, file=sys.stderr, flush=True)
                future = None
                dirty = True
            if mode == "google" and adapter is not None and future is None and tick >= next_fetch:
                requested_week = week
                future = executor.submit(fetch_snapshot, adapter, config, week, calendars, zone)
                dirty = True
            if dirty:
                value = build_display(config, mode, calendars, week, zone, snapshot, error,
                                      future is not None and requested_week == week)
                if value != published:
                    atomic_write(view_path, value)
                    published = value
                dirty = False
            time.sleep(0.12)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        executor.shutdown(wait=True, cancel_futures=True)
        if adapter is not None:
            adapter.session.close()
    return proc.returncode or 0


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Paperweek: native LVGL family calendar prototype")
    sub = parser.add_subparsers(dest="command")
    for name in ("demo", "google"):
        p = sub.add_parser(name)
        p.add_argument("--date", type=date.fromisoformat, help="Any date in the desired week (YYYY-MM-DD)")
        p.add_argument("--scale", type=float, default=0, help="Window scale; 0 fits the screen")
        p.add_argument("--clean", action="store_true", help="Start with the clean monitor palette")
        p.add_argument("--simulate-refresh", action="store_true", help="Hold old frames for 19 seconds")
        p.add_argument("--export", type=Path, help="Render to a PNG and exit (no window)")
    p = sub.add_parser("connect")
    p.add_argument("--credentials", type=Path, help="Downloaded Google Desktop app JSON")
    sub.add_parser("disconnect")
    sub.add_parser("config")
    argv = sys.argv[1:] or ["demo"]
    args = parser.parse_args(argv)
    try:
        if args.command in ("demo", "google"):
            # A single writer per user keeps the IPC snapshot coherent.
            import fcntl
            with (data_dir() / "preview.lock").open("w") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise CalendarError("Another Paperweek preview is running. Close it first.") from None
                return run_preview(args)
        if args.command == "connect":
            return connect(args)
        if args.command == "disconnect":
            from .auth import disconnect
            disconnect()
            return 0
        if args.command == "config":
            print(data_dir() / "config.json")
            return 0
        parser.print_help()
        return 0
    except (CalendarError, ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        print(f"\nPaperweek: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nPaperweek closed.")
        return 130
