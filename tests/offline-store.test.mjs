import test from 'node:test';
import assert from 'node:assert/strict';
import {combineOffline,offlineWindows} from '../web/offline-store.mjs';
import {ordinal,isoDay} from '../web/dates.mjs';
const now=1000;
const record=(first,days,extra={})=>({savedAt:500,expires:2000,snapshot:{first,days,ready:true,revision:2,dataEpoch:3,config:{},batches:[],...extra}});
test('download windows cover the supported range including Christmas, leap days and month ends',()=>{
  for(const day of ['2026-09-06','2028-02-29','2026-01-31']){
    const windows=offlineWindows(ordinal(day)),sorted=[...windows].sort((a,b)=>a.first-b.first);
    assert.ok(windows[0].first<=ordinal(day)&&windows[0].first+windows[0].count>ordinal(day));
    for(let i=0;i<sorted.length;i++){assert.ok(sorted[i].count>0&&sorted[i].count<=31);if(i)assert.equal(sorted[i-1].first+sorted[i-1].count,sorted[i].first);}
    assert.ok(sorted[0].first<ordinal(day)-700);assert.ok(sorted.at(-1).first>ordinal(day)+700);
  }
  const w=offlineWindows(ordinal('2026-09-06'));
  assert.ok(w.findIndex(x=>isoDay(x.first)==='2026-12-01')<w.findIndex(x=>isoDay(x.first)==='2026-08-01'));
});
test('offline views stitch months and deduplicate events that cross New Year',()=>{
  const event={id:'overnight',summary:'On call'},base=record('2026-09-06',7);
  const records=[record('2026-12-01',31,{batches:[{member:'m',items:[event]}]}),record('2027-01-01',31,{batches:[{member:'m',items:[event]}]})];
  const s=combineOffline(base,records,{first:ordinal('2026-12-28'),count:7},now);
  assert.equal(s.first,'2026-12-28');assert.equal(s.days,7);assert.equal(s.batches[0].items.length,1);assert.equal(s.stale,true);
});
test('gaps, expiry, changed settings and changed accounts never look like an empty offline calendar',()=>{
  const base=record('2026-09-06',7),range={first:ordinal('2026-12-01'),count:31};
  assert.equal(combineOffline(base,[],range,now),null);
  for(const r of [record('2026-12-01',30),{...record('2026-12-01',31),expires:999},record('2026-12-01',31,{revision:1}),record('2026-12-01',31,{dataEpoch:4}),record('2026-12-01',31,{ready:false})])assert.equal(combineOffline(base,[r],range,now),null);
});
