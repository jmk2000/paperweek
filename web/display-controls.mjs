export function swipeAction(dx,dy,elapsed){
  return elapsed<=900&&Math.abs(dx)>=60&&Math.abs(dx)>Math.abs(dy)*1.5?(dx<0?3:0):null;
}
export function setupDisplay(navigate,say,{animateNavigation=true}={}){
  const canvas=document.getElementById('calendar'),menu=document.getElementById('display-menu');
  let start=null,sliding=false,ghost=null,offset=0;
  const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
  const snapshot=()=>{
    ghost=document.createElement('canvas');ghost.width=canvas.width;ghost.height=canvas.height;
    ghost.className='swipe-copy';ghost.setAttribute('aria-hidden','true');
    ghost.getContext('2d').drawImage(canvas,0,0);canvas.parentElement.append(ghost);
  };
  const reset=()=>{ghost?.remove();ghost=null;canvas.style.visibility='';canvas.style.transform='';offset=0;};
  const animate=(el,from,to)=>el.animate([{transform:`translateX(${from}px)`},{transform:`translateX(${to}px)`}],
    {duration:reduced()?0:260,easing:'cubic-bezier(.2,.7,.25,1)',fill:'forwards'});
  const move=async(index)=>{
    if(!animateNavigation)return navigate(index);
    if(sliding||document.querySelector('[data-nav]:disabled'))return;
    if(index!==0&&index!==3){reset();return navigate(index);}
    sliding=true;
    try{
      if(!ghost)snapshot();
      canvas.style.visibility='hidden';
      const changed=await navigate(index);
      document.querySelectorAll('[data-nav]').forEach(b=>b.disabled=true);
      if(changed===false){
        const back=animate(ghost,offset,0);try{await back.finished;}finally{back.cancel();}return;
      }
      const width=canvas.getBoundingClientRect().width,sign=index===3?-1:1;
      canvas.style.visibility='';
      const outgoing=animate(ghost,offset,sign*width),incoming=animate(canvas,offset-sign*width,0);
      try{await Promise.all([outgoing.finished,incoming.finished]);}finally{outgoing.cancel();incoming.cancel();}
    }finally{reset();sliding=false;document.querySelectorAll('[data-nav]').forEach(b=>b.disabled=false);}
  };
  canvas.addEventListener('pointerdown',e=>{
    if(!e.isPrimary||sliding||document.querySelector('dialog[open]')||document.querySelector('[data-nav]:disabled'))return;
    if(e.pointerType==='mouse'&&e.button!==0)return;
    start={x:e.clientX,y:e.clientY,time:e.timeStamp,id:e.pointerId};
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove',e=>{
    if(!start||start.id!==e.pointerId||sliding)return;
    const dx=e.clientX-start.x,dy=e.clientY-start.y;
    if(!ghost&&Math.abs(dx)>8&&Math.abs(dx)>Math.abs(dy)*1.5){snapshot();canvas.style.visibility='hidden';}
    if(ghost){offset=reduced()?0:Math.max(-canvas.clientWidth,Math.min(canvas.clientWidth,dx));ghost.style.transform=`translateX(${offset}px)`;}
  });
  const finish=async(e,cancel=false)=>{
    const from=start;start=null;if(!from||from.id!==e.pointerId)return;
    const action=cancel?null:swipeAction(e.clientX-from.x,e.clientY-from.y,e.timeStamp-from.time);
    if(action!==null){await move(action);return;}
    if(ghost){sliding=true;const animation=animate(ghost,offset,0);try{await animation.finished;}finally{animation.cancel();reset();sliding=false;}}
  };
  canvas.addEventListener('pointercancel',e=>finish(e,true));
  canvas.addEventListener('pointerup',e=>finish(e));
  const install=document.createElement('button');install.textContent='Install app';menu.querySelector('.tools').append(install);
  let prompt=null;
  const installed=()=>{install.hidden=matchMedia('(display-mode: standalone)').matches;};installed();
  window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();prompt=e;});
  window.addEventListener('appinstalled',()=>{prompt=null;install.hidden=true;});
  install.onclick=async()=>{
    menu.open=false;
    if(prompt){await prompt.prompt();await prompt.userChoice;prompt=null;}
    else {
      const agenda=document.querySelector('.agenda');
      let guide=document.getElementById('install-guide');
      if(!guide){guide=document.createElement('p');guide.id='install-guide';agenda.querySelector('summary').after(guide);}
      guide.textContent='Install Paperweek from your browser menu: Install app or Add to Home Screen. On iPad, use Safari’s Share menu → Add to Home Screen. Use the HTTPS address for installation.';
      agenda.open=true;agenda.scrollTop=0;agenda.querySelector('summary').focus();
    }
  };
  const agenda=document.querySelector('.agenda'),health=document.createElement('p');
  agenda.querySelector('summary').after(health);
  agenda.addEventListener('toggle',()=>{if(agenda.open)health.textContent=document.getElementById('message').textContent;});
  const button=document.getElementById('fullscreen');
  const standalone=matchMedia('(display-mode: standalone)'),pwaFullscreen=matchMedia('(display-mode: fullscreen)');
  const toolbar=document.querySelector('.planner-toolbar'),toolbarHome=document.createComment('Display options');
  if(toolbar)toolbar.before(toolbarHome);
  const update=()=>{
    button.textContent=document.fullscreenElement?'Exit full screen':'Full screen';button.title=button.textContent;
    if(!toolbar)return;
    const compact=Boolean(document.fullscreenElement)||standalone.matches||pwaFullscreen.matches;
    document.body.classList.toggle('planner-fullscreen',compact);
    if(compact)menu.querySelector('.tools').prepend(toolbar);else toolbarHome.after(toolbar);
    document.querySelectorAll('.school-focus-wrap').forEach(n=>n.open=!compact);
  };
  standalone.addEventListener('change',update);pwaFullscreen.addEventListener('change',update);
  button.onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();menu.open=false;}catch{say('Full screen is unavailable in this browser. Try adding Paperweek to your home screen.');}};
  document.addEventListener('fullscreenchange',update);update();
  menu.addEventListener('click',e=>{if(e.target.closest('#refresh'))menu.open=false;});
  document.addEventListener('click',e=>{if(!menu.contains(e.target))menu.open=false;});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')menu.open=false;});
  return move;
}
export async function showBuild(){
  try{
    const response=await fetch('./build-info.json');if(!response.ok)return;
    const info=await response.json();
    document.querySelectorAll('[data-build]').forEach(el=>{el.textContent=`Paperweek ${info.version} · build ${info.build||info.backend}`;});
  }catch{/* The calendar reports startup/offline errors separately. */}
}
