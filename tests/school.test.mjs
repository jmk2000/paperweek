import test from 'node:test';
import assert from 'node:assert/strict';
import {validateSchool,schoolDay,weekday,UNIFORMS,snackLabel} from '../web/school.mjs';
import {ordinal} from '../web/dates.mjs';
import {defaults,validateConfig} from '../web/config.mjs';
const members=defaults().members;
const profile=(overrides={})=>({member:'member-3',cycleWeeks:2,anchor:'2026-09-07',terms:[{start:'2026-09-01',end:'2026-10-16'},{start:'2026-11-02',end:'2026-12-18'}],days:[{week:1,weekday:1,uniform:'pe',snacks:2,lessons:[{name:'Maths'}]},{week:2,weekday:1,uniform:'school',snacks:0}],activities:[{name:'Music',weekday:1,start:'16:00',end:'16:30'}],...overrides});
const valid=p=>validateSchool([p],members)[0];
const day=(p,date)=>schoolDay(valid(p),ordinal(date));
test('old settings still load; school profiles are optional',()=>assert.deepEqual(validateConfig(defaults()).school,[]));
test('rolling settings survive validation',()=>assert.equal(validateConfig({...defaults(),defaultView:'rolling'}).defaultView,'rolling'));
test('weekly rule repeats without A/B changes',()=>{const p=profile({cycleWeeks:1,days:[{week:1,weekday:1,uniform:'pe',snacks:2}]});for(const d of ['2026-09-07','2026-09-14'])assert.equal(day(p,d).uniform,'pe');});
test('fortnightly week A and B; snacks zero is not unknown',()=>{assert.equal(day(profile(),'2026-09-07').uniform,'pe');const b=day(profile(),'2026-09-14');assert.equal(b.week,2);assert.equal(b.uniform,'school');assert.equal(b.snacks,0);assert.equal(snackLabel(b.snacks),'No snacks');});
test('dates before anchor use positive modulo',()=>{const d=day(profile({terms:[{start:'2026-08-01',end:'2026-09-30'}]}),'2026-08-31');assert.equal(d.week,2);});
test('inclusive term start/end and holidays do not create school',()=>{assert.equal(day(profile(),'2026-09-01').school,true);assert.equal(day(profile(),'2026-10-16').school,true);assert.equal(day(profile(),'2026-10-19').school,false);assert.equal(day(profile(),'2026-10-19').activities.length,0);});
test('term anchor can explicitly reset A/B after holidays',()=>{const p=profile({terms:[{start:'2026-11-02',end:'2026-12-18',weekA:'2026-10-26'}]});assert.equal(day(p,'2026-11-02').week,2);});
test('cycles continue over holidays and year boundary',()=>{const p=profile({terms:[{start:'2026-12-01',end:'2027-02-01'}]});assert.equal(day(p,'2027-01-04').week,2);});
test('DST has no effect on civil-week parity',()=>{const p=profile({terms:[{start:'2026-10-01',end:'2026-11-30'}]});assert.equal(day(p,'2026-10-19').week,1);assert.equal(day(p,'2026-10-26').week,2);assert.equal(day(p,'2026-11-02').week,1);});
test('INSET exclusion suppresses essentials, lessons and activities',()=>{const d=day(profile({excludeDates:['2026-09-07']}),'2026-09-07');assert.equal(d.school,false);assert.deepEqual(d.lessons,[]);assert.deepEqual(d.activities,[]);});
test('an activity cancellation does not remove school',()=>{const p=profile({activities:[{name:'Music',weekday:1,start:'16:00',end:'16:30',skipDates:['2026-09-07']}]});assert.equal(day(p,'2026-09-07').activities.length,0);assert.equal(day(p,'2026-09-07').school,true);assert.equal(day(p,'2026-09-14').activities.length,1);});
test('B-only activity is separate from every-week clubs',()=>{const p=profile({activities:[{name:'Club',weekday:1,week:2,start:'16:00',end:'17:00'}]});assert.equal(day(p,'2026-09-07').activities.length,0);assert.equal(day(p,'2026-09-14').activities.length,1);});
test('weekend music is possible without pretending school is open',()=>{const p=profile({activities:[{name:'Music',weekday:6,start:'10:00',end:'11:00'}]});const d=day(p,'2026-09-12');assert.equal(d.school,false);assert.equal(d.activities.length,1);});
test('missing setup remains visibly unknown',()=>{const p=profile({days:[]});assert.equal(day(p,'2026-09-07').uniform,'unknown');assert.equal(day(p,'2026-09-07').snacks,null);assert.equal(day(profile({terms:[]}),'2026-09-07').reason,'Term dates not set');assert.equal(snackLabel(null),'Snacks not set');assert.ok(UNIFORMS.unknown);});
for(const [name,mutate] of [
 ['overlapping terms',p=>p.terms.push({start:'2026-10-16',end:'2026-11-03'})],
 ['impossible date',p=>p.terms[0].start='2026-02-30'],
 ['non-Monday anchor',p=>p.anchor='2026-09-08'],
 ['reversed term',p=>p.terms[0].end='2026-08-01'],
 ['duplicate day',p=>p.days.push(p.days[0])],
 ['B rules in a weekly cycle',p=>p.cycleWeeks=1],
 ['negative snacks',p=>p.days[0].snacks=-1],
 ['boolean snacks',p=>p.days[0].snacks=true],
 ['invalid uniform',p=>p.days[0].uniform='sports'],
 ['invalid time',p=>p.activities[0].start='25:00'],
 ['overnight club',p=>p.activities[0].end='08:00'],
 ['missing club time',p=>p.activities[0].start=''],
 ['unknown member',p=>p.member='not-configured'],
 ['control character',p=>p.activities[0].name='Bad\nname'],
 ['duplicate exclusion',p=>p.excludeDates=['2026-09-07','2026-09-07']],
 ['unknown field',p=>p.secret='never sent'],
])test(`validation rejects ${name}`,()=>{const p=profile();mutate(p);assert.throws(()=>valid(p));});
test('duplicate school profiles rejected',()=>assert.throws(()=>validateSchool([profile(),profile()],members)));
test('no mutation of original profiles when normalising',()=>{const p=profile(),before=JSON.stringify(p);valid(p);assert.equal(JSON.stringify(p),before);});
test('weekday uses ISO Monday=1 Sunday=7',()=>{assert.equal(weekday(ordinal('2026-09-06')),7);assert.equal(weekday(ordinal('2026-09-07')),1);});
