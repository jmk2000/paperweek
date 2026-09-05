/** Same-origin API and deliberately bounded, opt-in private offline storage. */
export class ApiError extends Error {
  constructor(message,status=0,payload=null){super(message);this.status=status;this.payload=payload;}
}
export async function api(path,{method='GET',body,timeout=15000,signal}={}){
  if(!path.startsWith('/api/'))throw new Error('Only local Paperweek API routes are allowed.');
  const controller=new AbortController(), abort=()=>controller.abort();
  if(signal?.aborted)controller.abort();signal?.addEventListener('abort',abort,{once:true});
  const timer=setTimeout(abort,timeout);
  try{
    const headers={'Accept':'application/json'};
    if(method!=='GET'){headers['Content-Type']='application/json';headers['X-Paperweek-Request']='1';}
    const response=await fetch(path,{method,headers,credentials:'same-origin',cache:'no-store',
      body:method==='GET'?undefined:JSON.stringify(body??{}),signal:controller.signal});
    let payload;try{payload=await response.json();}catch{throw new ApiError('The server did not return JSON. Check the proxy destination and deployed version.',response.status);}
    if(!response.ok)throw new ApiError(typeof payload.detail==='string'?payload.detail:'Request failed.',response.status,payload);
    return payload;
  }catch(e){if(e instanceof ApiError)throw e;throw new ApiError('Paperweek server is unreachable. Check Wi-Fi, VPN and the server.',0);}
  finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
export const CACHE_KEY='paperweek.offline.v4';
export const PREF_KEY='paperweek.device.v4';
export function preferences(storage=localStorage){try{return {offline:false,wake:false,...JSON.parse(storage.getItem(PREF_KEY)||'{}')};}catch{return {offline:false,wake:false};}}
export function setPreferences(p,storage=localStorage){storage.setItem(PREF_KEY,JSON.stringify(p));}
export function clearOffline(storage=localStorage){storage.removeItem(CACHE_KEY);}
export function cacheSnapshot(snapshot,sessionExpiry,storage=localStorage,now=Date.now()){
  if(!snapshot.ready)return;
  const expires=Math.min(now+7*86400000,sessionExpiry*1000);
  if(expires<=now)return;
  // Retain only the last complete view, never the entire Google cache or tokens.
  const record={version:4,savedAt:now,expires,snapshot};
  const encoded=JSON.stringify(record);if(encoded.length>2_000_000)throw new Error('Offline view exceeds the local storage limit.');
  storage.setItem(CACHE_KEY,encoded);
}
export function readOffline(storage=localStorage,now=Date.now()){
  try{const r=JSON.parse(storage.getItem(CACHE_KEY)||'null');
    if(r?.version===4&&r.expires>now&&r.snapshot?.ready&&r.snapshot.days<=62)return r;
  }catch{}clearOffline(storage);return null;
}
