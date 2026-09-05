export function swipeAction(dx,dy,elapsed){
  return elapsed<=900&&Math.abs(dx)>=60&&Math.abs(dx)>Math.abs(dy)*1.5?(dx<0?3:0):null;
}
export function setupDisplay(navigate,say){
  const canvas=document.getElementById('calendar'),menu=document.getElementById('display-menu');
  let start=null;
  canvas.addEventListener('pointerdown',e=>{
    if(!e.isPrimary){start=null;return;}
    if(e.pointerType==='mouse'||document.querySelector('dialog[open]'))return;
    start={x:e.clientX,y:e.clientY,time:e.timeStamp,id:e.pointerId};
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointercancel',()=>{start=null;});
  canvas.addEventListener('pointerup',e=>{
    const from=start;start=null;if(!from||from.id!==e.pointerId)return;
    const action=swipeAction(e.clientX-from.x,e.clientY-from.y,e.timeStamp-from.time);
    if(action!==null)navigate(action);
  });
  const button=document.getElementById('fullscreen');
  const update=()=>{button.textContent=document.fullscreenElement?'Exit full screen':'Full screen';button.title=button.textContent;};
  button.onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();menu.open=false;}catch{say('Full screen is unavailable in this browser. Try adding Paperweek to your home screen.');}};
  document.addEventListener('fullscreenchange',update);update();
  menu.addEventListener('click',e=>{if(e.target.closest('#refresh'))menu.open=false;});
  document.addEventListener('click',e=>{if(!menu.contains(e.target))menu.open=false;});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')menu.open=false;});
}
export async function showBuild(){
  try{
    const response=await fetch('./build-info.json');if(!response.ok)return;
    const info=await response.json();
    document.querySelectorAll('[data-build]').forEach(el=>{el.textContent=`Paperweek ${info.version} · build ${info.build||info.backend}`;});
  }catch{/* The calendar reports startup/offline errors separately. */}
}
