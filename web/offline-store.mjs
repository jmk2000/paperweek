import {isoDay,ordinal} from './dates.mjs';
const DB='paperweek-offline';
let opening;
function database(){
  if(!globalThis.indexedDB)return Promise.reject(new Error('Offline calendar storage is unavailable in this browser.'));
  return opening??=new Promise((resolve,reject)=>{
    const request=indexedDB.open(DB,1);
    request.onupgradeneeded=()=>request.result.createObjectStore('windows',{keyPath:'key'});
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>{opening=null;reject(request.error);};
  });
}
async function transaction(mode,run){
  const db=await database();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction('windows',mode);let value;
    tx.oncomplete=()=>resolve(value);tx.onerror=tx.onabort=()=>reject(tx.error||new Error('Offline storage failed.'));
    run(tx.objectStore('windows'),result=>{value=result;});
  });
}
export function clearWindowCache(){
  if(!globalThis.indexedDB)return Promise.resolve();
  return transaction('readwrite',store=>store.clear());
}
export async function cacheWindow(snapshot,sessionExpiry,now=Date.now()){
  if(!snapshot.ready)return;
  const expires=Math.min(now+7*86400000,sessionExpiry*1000);if(expires<=now)return;
  await transaction('readwrite',store=>{
    store.put({key:`${snapshot.first}:${snapshot.days}`,snapshot,savedAt:now,expires});
    const cursor=store.openCursor();cursor.onsuccess=()=>{const c=cursor.result;if(!c)return;if(c.value.expires<=now)c.delete();c.continue();};
  });
}
// Match the server's bounded browsing range; request calendar months future-first.
export function offlineWindows(today){
  const date=new Date(today*86400000),y=date.getUTCFullYear(),m=date.getUTCMonth(),d=date.getUTCDate();
  const shift=n=>Date.UTC(y,m+n,Math.min(d,new Date(Date.UTC(y,m+n+1,0)).getUTCDate()))/86400000;
  const first=shift(-24),end=shift(25),windows=[];
  for(let n=-24;n<=25;n++){
    const a=Math.max(first,Date.UTC(y,m+n,1)/86400000),b=Math.min(end,Date.UTC(y,m+n+1,1)/86400000);
    if(b>a)windows.push({first:a,count:b-a});
  }
  return windows.sort((a,b)=>(a.first>=today-d+1?0:1)-(b.first>=today-d+1?0:1)||(a.first>=today-d+1?a.first-b.first:b.first-a.first));
}
export function combineOffline(base,records,range,now=Date.now()){
  if(!base||base.expires<=now)return null;
  const current=base.snapshot;
  const valid=[base,...records].filter(r=>r.expires>now&&r.snapshot?.ready&&r.snapshot.revision===current.revision&&r.snapshot.dataEpoch===current.dataEpoch)
    .sort((a,b)=>b.savedAt-a.savedAt);
  const selected=new Set();
  for(let day=range.first;day<range.first+range.count;day++){
    const record=valid.find(r=>ordinal(r.snapshot.first)<=day&&ordinal(r.snapshot.first)+r.snapshot.days>day);
    if(!record)return null; // An unsaved day is never presented as an empty/off day.
    selected.add(record);
  }
  const batches=new Map(),success=[];
  for(const {snapshot}of [...selected].sort((a,b)=>a.savedAt-b.savedAt)){
    if(snapshot.lastSuccess)success.push(snapshot.lastSuccess);
    for(const batch of snapshot.batches||[]){
      if(!batches.has(batch.member))batches.set(batch.member,new Map());
      for(const raw of batch.items)batches.get(batch.member).set(raw.id||JSON.stringify(raw),raw);
    }
  }
  return {...current,first:isoDay(range.first),days:range.count,stale:true,lastSuccess:success.length?Math.min(...success):null,
    batches:[...batches].map(([member,items])=>({member,items:[...items.values()]}))};
}
export async function readWindowSnapshot(base,range){
  const records=await transaction('readonly',(store,done)=>{const request=store.getAll();request.onsuccess=()=>done(request.result);});
  return combineOffline(base,records,range);
}
