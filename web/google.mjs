import {normaliseEvent, validateEvents, MAX_EVENTS} from './events.mjs';
import {googleBounds} from './dates.mjs';
export const SCOPES = ['https://www.googleapis.com/auth/calendar.events.readonly','https://www.googleapis.com/auth/calendar.calendarlist.readonly'];
const API='https://www.googleapis.com/calendar/v3/';
export class ReconnectError extends Error { constructor(){super('Google access has expired. Tap Connect Google to renew access.');this.name='ReconnectError';} }
let loading;
export function validGoogleOrigin(location) {
  return location.protocol==='https:' || (location.protocol==='http:' && ['localhost','127.0.0.1','[::1]'].includes(location.hostname));
}
export async function loadGoogleLibrary() {
  if(globalThis.google?.accounts?.oauth2)return;
  if(!validGoogleOrigin(globalThis.location))throw new Error('Google sign-in needs HTTPS, or localhost on this device. Plain HTTP at a Mac LAN address works for the demo only.');
  if(!loading)loading=new Promise((resolve,reject)=>{
    const script=document.createElement('script');script.src='https://accounts.google.com/gsi/client';script.async=true;
    const timer=setTimeout(()=>{loading=null;script.remove();reject(new Error('Google sign-in did not load. Check connectivity and content blockers.'));},20000);
    script.onload=()=>{clearTimeout(timer);resolve();};script.onerror=()=>{clearTimeout(timer);loading=null;script.remove();reject(new Error('Unable to load Google sign-in.'));};
    document.head.append(script);
  });
  await loading;
}
export class GoogleSource {
  #token=''; #expires=0; #fetch; #now;
  constructor(fetcher=globalThis.fetch.bind(globalThis),now=()=>Date.now()){this.#fetch=fetcher;this.#now=now;}
  get connected(){return !!this.#token&&this.#now()<this.#expires-30000;}
  // Call synchronously from a user action after loadGoogleLibrary(). Do not
  // invoke requestAccessToken automatically from a timer or after awaiting I/O.
  connect(clientId) {
    if(!globalThis.google?.accounts?.oauth2)throw new Error('Prepare Google sign-in first.');
    if(!clientId)throw new Error('Set a Web application OAuth client ID in Settings.');
    return new Promise((resolve,reject)=>{
      const client=globalThis.google.accounts.oauth2.initTokenClient({
        client_id:clientId,scope:SCOPES.join(' '),include_granted_scopes:true,
        error_callback:()=>reject(new Error('Google sign-in was cancelled or its popup was blocked.')),
        callback:response=>{
          if(response.error||!response.access_token)return reject(new Error('Google did not grant calendar access.'));
          if(!globalThis.google.accounts.oauth2.hasGrantedAllScopes(response,...SCOPES))return reject(new Error('Both read-only Calendar permissions are required.'));
          this.acceptToken(response.access_token,Number(response.expires_in));resolve();
        },
      });
      client.requestAccessToken({prompt:''});
    });
  }
  // Used by the OAuth callback and injectable tests. Tokens never enter storage.
  acceptToken(value,seconds){if(typeof value!=='string'||!value||!Number.isFinite(seconds)||seconds<=0)throw new Error('Invalid OAuth response.');this.#token=value;this.#expires=this.#now()+seconds*1000;}
  disconnect(){this.#token='';this.#expires=0;}
  async revoke(){const token=this.#token;this.disconnect();if(token&&globalThis.google?.accounts?.oauth2)await new Promise(resolve=>globalThis.google.accounts.oauth2.revoke(token,resolve));}
  async request(path,params={},signal) {
    if(!this.connected){this.disconnect();throw new ReconnectError();}
    const url=new URL(path,API);
    if(url.origin!==new URL(API).origin||!url.pathname.startsWith('/calendar/v3/'))throw new Error('Refusing a non-Calendar API endpoint.');
    for(const [k,v]of Object.entries(params))if(v!==undefined)url.searchParams.set(k,String(v));
    const token=this.#token;
    for(let attempt=0;attempt<3;++attempt){
      const local=new AbortController();const relay=()=>local.abort(signal?.reason);
      if(signal?.aborted)throw new DOMException('Request cancelled','AbortError');
      signal?.addEventListener('abort',relay,{once:true});
      const timer=setTimeout(()=>local.abort(),20000);
      let response, data;
      try{response=await this.#fetch(url,{headers:{Authorization:`Bearer ${token}`},cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer',signal:local.signal});if(response.ok)data=await response.json();}
      finally{clearTimeout(timer);signal?.removeEventListener('abort',relay);}
      if(response.status===401){this.disconnect();throw new ReconnectError();}
      if((response.status===429||response.status>=500)&&attempt<2){await new Promise(r=>setTimeout(r,250*2**attempt));continue;}
      if(!response.ok)throw new Error(response.status===403?'Google denied access. Check calendar sharing, API enablement and Workspace app policy.':`Calendar request failed (${response.status}). The previous display is retained.`);
      return data;
    }
    throw new Error('Calendar request failed.');
  }
  async calendars(signal) {
    let pageToken;const result=[],seen=new Set();
    do{
      const data=await this.request('users/me/calendarList',{maxResults:250,pageToken},signal);
      for(const c of data.items||[])if(['reader','writer','writerWithoutPrivateAccess','owner'].includes(c.accessRole))result.push({id:c.id,label:c.summaryOverride||c.summary||'Calendar'});
      pageToken=data.nextPageToken;
      if(pageToken){if(seen.has(pageToken)||seen.size>=40)throw new Error('Calendar pagination exceeded its safety limit.');seen.add(pageToken);}
    }while(pageToken);
    return result;
  }
  async events(config,first,count,signal) {
    const combined=[],bounds=googleBounds(first,count);
    // Sequential calendars keep quota use modest. No partial result is returned.
    for(let index=0;index<config.members.length;++index){
      const member=config.members[index];if(!member.calendarId)throw new Error(`Choose a Google calendar for ${member.label} in Settings.`);
      let pageToken;const seen=new Set();
      do{
        const data=await this.request(`calendars/${encodeURIComponent(member.calendarId)}/events`,{
          ...bounds,singleEvents:true,orderBy:'startTime',showDeleted:false,maxResults:250,
          timeZone:config.timezone,pageToken,
          fields:'nextPageToken,items(id,iCalUID,summary,status,visibility,start,end,attendees(self,responseStatus))',
        },signal);
        for(const raw of data.items||[]){
          const e=normaliseEvent(raw,member,index,config);if(e)combined.push(e);
          if(combined.length>MAX_EVENTS)throw new Error(`More than ${MAX_EVENTS} records in the requested range. No partial calendar is displayed.`);
        }
        pageToken=data.nextPageToken;
        if(pageToken){if(seen.has(pageToken)||seen.size>=40)throw new Error('Event pagination exceeded its safety limit.');seen.add(pageToken);}
      }while(pageToken);
    }
    return validateEvents(combined,config);
  }
}
