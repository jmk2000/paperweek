"""Bounded, household-owned school routines; never provider credentials.

Civil dates are deliberate: school weeks do not change with DST. Term ends are
inclusive. Week A continues through holidays unless a term supplies a new anchor.
"""
from __future__ import annotations
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import json
import re

Uniform = Literal['school', 'pe', 'none', 'unknown']


def civil(value: str) -> str:
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Use a date in YYYY-MM-DD format.')
    parsed = date.fromisoformat(value)
    if not 1900 <= parsed.year <= 2200:
        raise ValueError('School dates must be between 1900 and 2200.')
    return value


def monday(value: str) -> str:
    civil(value)
    if date.fromisoformat(value).weekday() != 0:
        raise ValueError('Week A must be anchored to a Monday.')
    return value


class SchoolModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    @field_validator('*', mode='before')
    @classmethod
    def text_controls(cls, value):
        if isinstance(value, str) and re.search(r'[\x00-\x1f\x7f]', value):
            raise ValueError('Control characters are not allowed.')
        return value


class Term(SchoolModel):
    start: str
    end: str
    weekA: str = ''

    @model_validator(mode='after')
    def valid(self):
        civil(self.start)
        civil(self.end)
        if self.end < self.start:
            raise ValueError('Term end must not precede its start.')
        if self.weekA:
            monday(self.weekA)
        return self


class Lesson(SchoolModel):
    name: str = Field(min_length=1, max_length=80)
    start: str = ''
    end: str = ''
    room: str = Field(default='', max_length=40)

    @model_validator(mode='after')
    def valid(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError('A lesson or activity needs a name.')
        if bool(self.start) != bool(self.end):
            raise ValueError('Enter both start and end times, or leave both blank.')
        for value in (self.start, self.end):
            if value and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
                raise ValueError('Use a time in HH:MM format.')
        if self.start and self.end <= self.start:
            raise ValueError('End time must be later on the same day.')
        return self


class SchoolDay(SchoolModel):
    week: int = Field(ge=1, le=2)
    weekday: int = Field(ge=1, le=5)  # ISO Monday to Friday
    uniform: Uniform = 'unknown'
    snacks: int | None = Field(default=None, ge=0, le=9)
    kit: str = Field(default='', max_length=120)
    lessons: list[Lesson] = Field(default_factory=list, max_length=10)


class Activity(Lesson):
    weekday: int = Field(ge=1, le=7)
    week: int = Field(default=0, ge=0, le=2)  # 0 = every week
    notes: str = Field(default='', max_length=160)
    skipDates: list[str] = Field(default_factory=list, max_length=80)

    @model_validator(mode='after')
    def activity_valid(self):
        if not self.start:
            raise ValueError('Clubs and music lessons need start and end times.')
        for value in self.skipDates:
            civil(value)
        if len(set(self.skipDates)) != len(self.skipDates):
            raise ValueError('Cancelled dates must be unique.')
        return self


class SchoolProfile(SchoolModel):
    member: str = Field(min_length=1, max_length=48, pattern=r'^[a-zA-Z0-9_-]+$')
    cycleWeeks: int = Field(default=1, ge=1, le=2)
    anchor: str
    terms: list[Term] = Field(default_factory=list, max_length=32)
    excludeDates: list[str] = Field(default_factory=list, max_length=180)
    days: list[SchoolDay] = Field(default_factory=list, max_length=10)
    activities: list[Activity] = Field(default_factory=list, max_length=24)

    @model_validator(mode='after')
    def valid(self):
        monday(self.anchor)
        terms = sorted(self.terms, key=lambda t: t.start)
        if any(a.end >= b.start for a, b in zip(terms, terms[1:])):
            raise ValueError('Term ranges must not overlap; both end dates are inclusive.')
        for value in self.excludeDates:
            civil(value)
        if len(set(self.excludeDates)) != len(self.excludeDates):
            raise ValueError('Excluded dates must be unique.')
        keys = [(d.week, d.weekday) for d in self.days]
        if len(set(keys)) != len(keys):
            raise ValueError('Only one school-day rule per weekday and cycle week.')
        if any(d.week > self.cycleWeeks for d in self.days) or any(a.week > self.cycleWeeks for a in self.activities):
            raise ValueError('Week B rules require a two-week timetable.')
        return self


def validate_school_members(profiles: list[SchoolProfile], members) -> None:
    keys = [p.member for p in profiles]
    if len(keys) != len(set(keys)) or not set(keys) <= {m.key for m in members}:
        raise ValueError('School profiles must use distinct, configured people.')
    # Stay below the existing 64 KiB API body ceiling, including other settings.
    if len(json.dumps([p.model_dump() for p in profiles], ensure_ascii=False).encode('utf-8')) > 48000:
        raise ValueError('School settings exceed 48 KB. Shorten notes or remove old terms.')


def public_school(profiles: list[SchoolProfile], members) -> list[dict]:
    """Mask at the server boundary, before display/offline JSON is delivered.

    Uniform and snack counts are operational status, like the rota. Descriptive
    titles, rooms and packing/pickup notes follow the person's title masking.
    """
    masked = {m.key for m in members if m.maskTitles}
    result = [p.model_dump() for p in profiles]
    for profile in result:
        if profile['member'] not in masked:
            continue
        for day in profile['days']:
            day['kit'] = ''
            for lesson in day['lessons']:
                lesson.update(name='Lesson', room='')
        for activity in profile['activities']:
            activity.update(name='Activity', room='', notes='')
    return result
