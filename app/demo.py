"""Invented events only. Repeat relative to the selected week, never impersonate real data."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from .model import Calendar, Event, monday

CALENDARS = [Calendar("alex", "Alex", "blue"), Calendar("sam", "Sam", "red"),
             Calendar("kids", "Kids", "green"), Calendar("family", "Together", "black"),
             Calendar("home", "Home", "yellow")]


def events_for(week: date, zone: ZoneInfo) -> list[Event]:
    week = monday(week)
    rows = [
        (0, "kids", "08:30", "School drop-off", 30),
        (0, "alex", "17:30", "Evening run", 45),
        (0, "home", "19:00", "Plan the meals", 30),
        (1, "sam", "09:30", "Working from home", 480),
        (1, "kids", "16:30", "Swimming", 60),
        (2, "alex", "08:15", "Train to town", 45),
        (2, "kids", "18:00", "Cubs", 90),
        (2, "family", "19:30", "Pasta night", 60),
        (3, "home", "07:00", "Recycling out", 15),
        (3, "sam", "18:30", "Book club", 90),
        (4, "kids", "15:30", "Playdate", 120),
        (4, "family", "18:00", "Pizza & a film", 120),
        (5, "kids", "09:00", "Football", 90),
        (5, "family", "12:30", "Lunch with friends", 120),
        (6, "family", "10:00", "Walk in the woods", 120),
        (6, "home", "17:00", "Get ready for Monday", 30),
    ]
    events = []
    for n, (day, who, at, title, minutes) in enumerate(rows):
        start = datetime.fromisoformat(f"{week + timedelta(days=day)}T{at}:00").replace(tzinfo=zone)
        events.append(Event(f"demo-{n}", who, title, start, start + timedelta(minutes=minutes), False))
    events.append(Event("birthday", "family", "Grandad's birthday", week + timedelta(days=5),
                        week + timedelta(days=6), True))
    return events
