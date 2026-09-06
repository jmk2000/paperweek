"""School validation/publication tests; no provider or household data required."""
import copy
import pytest
from pydantic import ValidationError
from backend.settings import DisplayConfig


def profile():
    return dict(member='member-3',cycleWeeks=2,anchor='2026-09-07',
                terms=[dict(start='2026-09-01',end='2026-10-16')],
                days=[dict(week=1,weekday=1,uniform='pe',snacks=2,kit='Private instrument',
                           lessons=[dict(name='Private subject',room='Private room')])],
                activities=[dict(name='Private club',weekday=1,week=0,start='16:00',end='17:00',notes='Private pickup')])


def config(p=None):
    return DisplayConfig(school=[profile() if p is None else p])


def test_backwards_compatible_defaults():
    c=DisplayConfig()
    assert c.defaultView=='rolling'
    assert c.school==[]
    assert DisplayConfig.model_validate({**c.model_dump(),'defaultView':'month'}).defaultView=='month'


def test_roundtrip_settings_and_publication():
    c=config()
    assert DisplayConfig.model_validate(c.model_dump())==c
    assert c.public()['school'][0]['days'][0]['snacks']==2


def test_server_masks_school_titles_before_sending_to_displays():
    c=config()
    c.members[2].maskTitles=True
    public=c.public()
    assert 'Private' not in str(public['school'])
    assert public['school'][0]['days'][0]['uniform']=='pe'
    assert public['school'][0]['days'][0]['snacks']==2
    assert public['school'][0]['activities'][0]['start']=='16:00'
    assert 'Private' in str(c.model_dump())  # Masking must not destroy saved edits.


def test_zero_snacks_is_not_unknown():
    p=profile();p['days'][0]['snacks']=0
    assert config(p).public()['school'][0]['days'][0]['snacks']==0
    del p['days'][0]['snacks']
    assert config(p).school[0].days[0].snacks is None


@pytest.mark.parametrize('change',[
    lambda p:p.update(member='removed'),
    lambda p:p.update(anchor='2026-09-08'),
    lambda p:p['terms'].append(dict(start='2026-10-16',end='2026-11-01')),
    lambda p:p['terms'][0].update(start='2026-02-30'),
    lambda p:p['terms'][0].update(end='2026-08-31'),
    lambda p:p['terms'][0].update(weekA='2026-11-03'),
    lambda p:p['days'].append(copy.deepcopy(p['days'][0])),
    lambda p:p['days'][0].update(snacks=True),
    lambda p:p['days'][0].update(snacks=-1),
    lambda p:p['days'][0].update(snacks=10),
    lambda p:p['days'][0].update(uniform='invalid'),
    lambda p:p['days'][0].update(weekday=7),
    lambda p:p.update(cycleWeeks=1,days=[dict(week=2,weekday=1)]),
    lambda p:p['activities'][0].update(start='25:00'),
    lambda p:p['activities'][0].update(end='08:00'),
    lambda p:p['activities'][0].update(start=''),
    lambda p:p['activities'][0].update(name='Bad\nname'),
    lambda p:p.update(excludeDates=['2026-09-07','2026-09-07']),
    lambda p:p.update(secret='not allowed'),
])
def test_reject_invalid_rules(change):
    p=profile();change(p)
    with pytest.raises(ValidationError):config(p)


def test_profiles_are_unique():
    with pytest.raises(ValidationError):DisplayConfig(school=[profile(),profile()])


def test_profile_and_row_caps():
    p=profile();p['activities']*=25
    with pytest.raises(ValidationError):config(p)


def test_public_config_still_hides_provider_calendar_ids():
    c=config();c.source='google';c.members[2].calendarId='private-provider-id'
    assert 'private-provider-id' not in str(c.public())
