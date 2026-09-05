import {ascii,COLOURS} from './config.mjs';
import {validateEvents} from './events.mjs';
function rgb(value){return `#${value.toString(16).padStart(6,'0')}`;}
export function canvasImports(canvas,readString) {
  const ctx=canvas.getContext('2d',{alpha:false});
  return {
    begin(paper){ctx.fillStyle=paper?'#f5f3e9':'#ffffff';ctx.fillRect(0,0,canvas.width,canvas.height);},
    rect(x,y,w,h,colour){ctx.fillStyle=rgb(colour);ctx.fillRect(x,y,w,h);},
    text(x,y,w,h,pointer,size,colour,align){
      const text=readString(pointer);ctx.save();ctx.beginPath();ctx.rect(x,y,w,h);ctx.clip();
      ctx.font=`${size>=32?600:400} ${size}px Arial, sans-serif`;ctx.fillStyle=rgb(colour);ctx.textBaseline='top';ctx.textAlign='left';
      const height=size+3,maxLines=Math.max(1,Math.floor((h+3)/height));
      let lines=[],line='';
      for(const paragraph of text.split('\n')){
        for(const word of paragraph.split(' ')){
          const next=line?line+' '+word:word;
          if(line&&ctx.measureText(next).width>w){lines.push(line);line=word;}else line=next;
        }
        lines.push(line);line='';
      }
      const cut=lines.length>maxLines;lines=lines.slice(0,maxLines);
      if(cut)lines[lines.length-1]+='...';
      for(let i=0;i<lines.length;++i){
        let value=lines[i];
        if(ctx.measureText(value).width>w){while(value.length&&ctx.measureText(value+'...').width>w)value=value.slice(0,-1);value+='...';}
        const offset=align===1?(w-ctx.measureText(value).width)/2:align===2?w-ctx.measureText(value).width:0;
        ctx.fillText(value,x+offset,y+i*height);
      }
      ctx.restore();
    },
    end(){},
  };
}
export class Renderer {
  constructor(call,type,canvas){this.call=call;this.type=type;this.canvas=canvas;this.config=null;}
  configure(c){this.config=c;this.call('pw_configure',ascii(c.title,80),c.timezone,c.weekStart,c.members.findIndex(m=>m.key===c.rotaMember),Number(c.deduplicate));
    c.members.forEach((m,i)=>{if(!this.call('pw_person',i,ascii(m.label,40),m.badge,COLOURS[m.colour]))throw new Error('Invalid person configuration.');});
    this.call('pw_help_configure',Number(this.canvas?true:c.persistentLabels),c.helpSeconds);
  }
  clock(day,second){this.call('pw_clock',day,second);}
  select(day,month){this.call('pw_select',day,Number(month));}
  get anchor(){return this.call('pw_anchor');}
  get month(){return !!this.call('pw_is_month');}
  get range(){return {first:this.call('pw_first'),count:this.call('pw_day_count')};}
  navigate(index){this.call('pw_navigate',index);}
  events(events){validateEvents(events,this.config);this.call('pw_clear_events');
    for(const e of events){if(!this.call('pw_add_event',e.key,e.title,e.calendar,e.startDay,e.endDay,e.startSecond,e.endSecond,Number(e.allDay),e.kind,e.sortTime))throw new Error('Calendar capacity exceeded.');}
  }
  render(mode,status,stale=false){if(!this.call('pw_render',Number(this.config.paperPalette),mode,ascii(status,240),Number(stale)))throw new Error('The shared calendar model rejected the display data.');}
  prepare(mode,status,stale=false){const h=this.call('pw_prepare',mode,ascii(status,240),Number(stale));if(!h)throw new Error('Invalid display data.');return h;}
  draw(){this.call('pw_draw',Number(this.config.paperPalette));}
  placeholder(){this.call('pw_placeholder',Number(this.config.paperPalette));}
  press(now,busy){return this.call('pw_press',now>>>0,Number(busy));}
  visible(now){this.call('pw_visible',now>>>0);}
  expire(now,busy){return !!this.call('pw_expire',now>>>0,Number(busy));}
  get helpOpen(){return !!this.call('pw_help_open');}
}
export async function createRenderer(canvas) {
  const response=await fetch('./build-info.json',{cache:'no-cache'});if(!response.ok)throw new Error('Missing web build. Serve a packaged dist directory, not web/ source files.');
  const info=await response.json();
  if(info.backend==='lvgl'){
    const ctx=canvas.getContext('2d',{alpha:false});
    globalThis.PaperweekPaint={pixels(x,y,w,h,data){
      const image=ctx.createImageData(w,h);
      for(let i=0;i<w*h;++i){const p=i*4;image.data[p]=data[p+2];image.data[p+1]=data[p+1];image.data[p+2]=data[p];image.data[p+3]=255;}
      ctx.putImageData(image,x,y);
    }};
    const {default:createModule}=await import('./paperweek-lvgl.mjs');
    const module=await createModule();
    const call=(name,...args)=>module.ccall(name,'number',args.map(a=>typeof a==='string'?'string':'number'),args);
    call('pw_init');return webRenderer(call,'LVGL / WebAssembly',canvas,info);
  }
  if(info.backend!=='preview')throw new Error('Unknown renderer backend.');
  let instance;
  const decoder=new TextDecoder(),encoder=new TextEncoder();
  const readString=pointer=>{const heap=new Uint8Array(instance.exports.memory.buffer);let end=pointer;while(end<heap.length&&heap[end])++end;return decoder.decode(heap.subarray(pointer,end));};
  const imports={paperweek:canvasImports(canvas,readString)};
  const binary=await fetch('./paperweek-preview.wasm');if(!binary.ok)throw new Error('Missing WebAssembly module.');
  ({instance}=await WebAssembly.instantiate(await binary.arrayBuffer(),imports));
  const call=(name,...args)=>{
    const heap=new Uint8Array(instance.exports.memory.buffer);let pointer=instance.exports.pw_input_buffer();const end=pointer+instance.exports.pw_input_capacity();
    const values=args.map(value=>{if(typeof value!=='string')return value;const bytes=encoder.encode(value);if(pointer+bytes.length+1>end)throw new Error('Input string exceeds the WASM bridge limit.');const address=pointer;heap.set(bytes,pointer);pointer+=bytes.length;heap[pointer++]=0;return address;});
    return instance.exports[name](...values);
  };
  call('pw_init');return webRenderer(call,'C/WASM preview · browser fonts',canvas,info);
}

function webRenderer(call,type,canvas,info){
  const renderer=new Renderer(call,type,canvas);
  renderer.build=info;
  let sized=false;
  const resize=()=>{
    const bounds=canvas.parentElement.getBoundingClientRect();
    const height=Math.max(1125,Math.min(2600,Math.round(1600*bounds.height/bounds.width)));
    if(sized&&canvas.height===height)return;
    sized=true;
    canvas.height=height;call('pw_viewport',height);
    if(renderer.config)renderer.draw();
  };
  resize();new ResizeObserver(resize).observe(canvas.parentElement);
  return renderer;
}
