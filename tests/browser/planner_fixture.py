"""Invented household only. No real school, provider, or family data."""
from copy import deepcopy


def fixture():
    profiles = []
    for child, cycle in [(3, 2), (4, 1)]:
        days = []
        for week in range(1, cycle + 1):
            for day in range(1, 6):
                pe = day in ([1, 4] if child == 3 and week == 1 else [2, 5])
                subjects = ['Maths', 'English', 'Science', 'History', 'French', 'Art']
                if week == 2:
                    subjects = ['English', 'Maths', 'Geography', 'Computing', 'Music', 'Science']
                if child == 4:
                    subjects = ['Reading', 'Maths', 'Writing', 'Topic', 'PE' if pe else 'Art']
                days.append(dict(week=week, weekday=day, uniform='pe' if pe else 'school',
                                 snacks=2 if child == 3 else 0 if day == 3 else 1,
                                 kit='Violin and music' if child == 3 and day == 1 else 'Swimming bag' if child == 4 and day == 2 else '',
                                 lessons=[dict(name=name, start='', end='', room='') for name in subjects]))
        clubs = [dict(name='Orchestra', weekday=1, week=0, start='15:30', end='16:30', room='Music room', notes='Collect at side gate', skipDates=[]),
                 dict(name='Football club', weekday=4, week=1, start='15:30', end='16:30', room='Playing field', notes='Boots and water bottle', skipDates=[])] if child == 3 else [
                 dict(name='Piano lesson', weekday=2, week=0, start='16:00', end='16:30', room='', notes='Bring music book', skipDates=[]),
                 dict(name='Art club', weekday=5, week=0, start='15:15', end='16:15', room='', notes='', skipDates=[])]
        profiles.append(dict(member=f'member-{child}', cycleWeeks=cycle, anchor='2026-09-07',
                             terms=[dict(start='2026-09-02', end='2026-10-16', weekA=''),
                                    dict(start='2026-11-02', end='2026-12-18', weekA='2026-11-02')],
                             excludeDates=['2026-10-05'], days=days, activities=clubs))
    config = dict(version=3, title='Our week', timezone='Europe/London', weekStart=1,
                  defaultView='rolling', paperPalette=True, maskPrivate=True, deduplicate=False,
                  rotaMember='member-1', persistentLabels=True, helpSeconds=20,
                  refreshSeconds=0, pollMinutes=5, clientId='', source='google', school=profiles,
                  members=[dict(key=f'member-{i}', label=label, badge=str(i), colour=colour, calendarId='', maskTitles=False)
                           for i, label, colour in [(1, 'Adult 1', 'blue'), (2, 'Adult 2', 'green'), (3, 'Child 1', 'red'), (4, 'Child 2', 'yellow')]])
    def timed(id_, title, start, end):
        return dict(id=id_, iCalUID=id_, summary=title, start={'dateTime':start}, end={'dateTime':end})
    events = {
        'member-1': [timed('shift-1', '[PW:WORK]', '2026-09-07T08:00:00+01:00', '2026-09-07T17:00:00+01:00'),
                     timed('shift-2', '[PW:WORK]', '2026-09-09T08:00:00+01:00', '2026-09-09T17:00:00+01:00'),
                     timed('shift-3', '[PW:ONCALL]', '2026-09-10T18:00:00+01:00', '2026-09-11T08:00:00+01:00'),
                     timed('shift-4', '[PW:WORK]', '2026-09-11T09:00:00+01:00', '2026-09-11T13:00:00+01:00'),
                     dict(id='off', iCalUID='off', summary='[PW:OFF]', start={'date':'2026-09-08'}, end={'date':'2026-09-09'})],
        'member-2': [timed('family-lunch', 'Lunch with friends', '2026-09-06T13:00:00+01:00', '2026-09-06T15:00:00+01:00'),
                     timed('parents-evening', 'Parents’ evening', '2026-09-10T17:00:00+01:00', '2026-09-10T17:30:00+01:00')],
        'member-3': [dict(id='birthday', iCalUID='birthday', summary='Birthday celebration', start={'date':'2026-09-12'}, end={'date':'2026-09-13'})],
        'member-4': [timed('party', 'Birthday party', '2026-09-12T14:00:00+01:00', '2026-09-12T16:00:00+01:00')],
    }
    return deepcopy(config), events
