/* Decorative effects only. CRM remains usable without GSAP or WebGL. */
(() => {
  'use strict';
  const page=document.querySelector('#page');
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const contrast=matchMedia('(forced-colors: active)');
  const fine=matchMedia('(pointer: fine)');
  let contexts=[],seen=new WeakSet(),route=location.hash,entered=performance.now();
  let liquid=null,scheduled=false;
  const gs=window.gsap;
  if(gs)document.documentElement.classList.add('motion-ready');

  function createLiquid(host){
    const canvas=document.createElement('canvas');
    canvas.className='liquid-canvas';canvas.setAttribute('aria-hidden','true');
    const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:false,antialias:false,depth:false,powerPreference:'low-power'});
    if(!gl)return null;
    const shaders=[];
    let program,buffer,raf=0,visible=true,lost=false,last=0,time=0;
    const mouse={x:.78,y:.48},target={x:.78,y:.48};
    function compile(type,source){
      const shader=gl.createShader(type);shaders.push(shader);
      gl.shaderSource(shader,source);gl.compileShader(shader);
      if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw Error('Shader unavailable');
      return shader;
    }
    try{
      const vertex=compile(gl.VERTEX_SHADER,'attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}');
      const fragment=compile(gl.FRAGMENT_SHADER,`
        precision mediump float;
        uniform vec2 resolution;
        uniform vec2 pointer;
        uniform float time;
        void main(){
          vec2 uv=gl_FragCoord.xy/resolution;
          float aspect=resolution.x/resolution.y;
          vec2 p=(uv-vec2(.86,.48))*vec2(aspect,1.);
          p-=(pointer-vec2(.78,.48))*.045;
          float r=length(p);
          float angle=atan(p.y,p.x);
          float wave=sin(angle*3.+time*.48)*.012+sin(angle*5.-time*.32)*.006;
          float radius=.345+wave;
          float mask=1.-smoothstep(radius-.005,radius+.007,r);
          float z=sqrt(max(0.,1.-pow(r/radius,2.)));
          vec3 normal=normalize(vec3(p/radius,z));
          float fresnel=pow(1.-z,2.8);
          float light=pow(max(0.,dot(normal,normalize(vec3(-.5,.65,1.)))),35.);
          float flow=sin(p.x*15.+p.y*9.+sin(p.y*12.-time*.5)*1.4+time*.3);
          float caustic=pow(.5+.5*flow,9.)*.42;
          vec3 blue=mix(vec3(.38,.65,.97),vec3(.84,.94,1.),z*.72);
          blue+=caustic*vec3(.25,.3,.32)+light*.7;
          blue=mix(blue,vec3(.96,.99,1.),fresnel*.85);
          float ring=exp(-abs(r-radius)*220.);
          blue+=ring*.2;
          float shadow=exp(-length((p+vec2(-.015,.065))*vec2(1.,1.15))*10.)*.1;
          vec3 color=mix(vec3(.3,.53,.8),blue,mask);
          float alpha=max(mask*(.62+fresnel*.3),shadow);
          gl_FragColor=vec4(color,alpha);
        }
      `);
      program=gl.createProgram();gl.attachShader(program,vertex);gl.attachShader(program,fragment);gl.linkProgram(program);
      if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('Shader unavailable');
      gl.useProgram(program);buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
      gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);
      const pos=gl.getAttribLocation(program,'a');gl.enableVertexAttribArray(pos);gl.vertexAttribPointer(pos,2,gl.FLOAT,false,0,0);
    }catch{
      shaders.forEach(s=>gl.deleteShader(s));if(program)gl.deleteProgram(program);if(buffer)gl.deleteBuffer(buffer);
      return null;
    }
    const uniforms={resolution:gl.getUniformLocation(program,'resolution'),time:gl.getUniformLocation(program,'time'),pointer:gl.getUniformLocation(program,'pointer')};
    host.prepend(canvas);host.classList.add('has-liquid');
    function draw(){
      if(lost)return;
      gl.viewport(0,0,canvas.width,canvas.height);
      gl.uniform2f(uniforms.resolution,canvas.width,canvas.height);
      gl.uniform2f(uniforms.pointer,mouse.x,mouse.y);gl.uniform1f(uniforms.time,time);
      gl.drawArrays(gl.TRIANGLES,0,6);
    }
    function resize(){
      const rect=host.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,1.5);
      canvas.width=Math.max(1,Math.round(rect.width*dpr));canvas.height=Math.max(1,Math.round(rect.height*dpr));draw();
    }
    function frame(now){
      raf=0;
      if(document.hidden||!visible||lost||reduced.matches)return;
      if(now-last>=32){time+=Math.min((now-last)/1000,.05);last=now;mouse.x+=(target.x-mouse.x)*.08;mouse.y+=(target.y-mouse.y)*.08;draw();}
      raf=requestAnimationFrame(frame);
    }
    function sync(){cancelAnimationFrame(raf);raf=0;last=performance.now();if(!document.hidden&&visible&&!lost&&!reduced.matches)raf=requestAnimationFrame(frame);else draw();}
    function pointer(e){if(!fine.matches||reduced.matches)return;const r=host.getBoundingClientRect();target.x=(e.clientX-r.left)/r.width;target.y=1-(e.clientY-r.top)/r.height;}
    function leave(){target.x=.78;target.y=.48;}
    function contextLost(e){e.preventDefault();lost=true;cancelAnimationFrame(raf);host.classList.remove('has-liquid');canvas.style.display='none';}
    const ro=new ResizeObserver(resize);ro.observe(host);
    const io=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;sync();});io.observe(host);
    host.addEventListener('pointermove',pointer,{passive:true});host.addEventListener('pointerleave',leave);
    canvas.addEventListener('webglcontextlost',contextLost);
    document.addEventListener('visibilitychange',sync);reduced.addEventListener('change',sync);
    resize();sync();
    return {host,destroy(){cancelAnimationFrame(raf);ro.disconnect();io.disconnect();host.removeEventListener('pointermove',pointer);host.removeEventListener('pointerleave',leave);document.removeEventListener('visibilitychange',sync);reduced.removeEventListener('change',sync);canvas.removeEventListener('webglcontextlost',contextLost);gl.deleteBuffer(buffer);gl.deleteProgram(program);shaders.forEach(s=>gl.deleteShader(s));gl.getExtension('WEBGL_lose_context')?.loseContext();canvas.remove();host.classList.remove('has-liquid');}};
  }

  function refresh(){
    scheduled=false;
    if(route!==location.hash){contexts.forEach(c=>c.revert());contexts=[];seen=new WeakSet();route=location.hash;entered=performance.now();}
    const hero=page.querySelector('.hero');
    if(liquid && (liquid.host!==hero||contrast.matches)){delete liquid.host.dataset.shaderAttempt;liquid.destroy();liquid=null;}
    if(hero&&!liquid&&!contrast.matches&&!hero.dataset.shaderAttempt){hero.dataset.shaderAttempt='true';liquid=createLiquid(hero);}
    if(!gs||reduced.matches||performance.now()-entered>1800)return;
    const targets=[...page.querySelectorAll('.ph,.hero,.overview-card,.kpi,.g-main>.card,.g2>.card,#tbl,.kb')].filter(el=>!seen.has(el));
    targets.forEach(el=>seen.add(el));
    if(targets.length)contexts.push(gs.context(()=>{
      gs.from(targets,{y:14,autoAlpha:0,duration:.55,stagger:.045,ease:'power3.out',clearProps:'transform,opacity,visibility'});
      const bars=page.querySelectorAll('.mini-bars span');
      if(bars.length)gs.from(bars,{scaleY:0,transformOrigin:'bottom',duration:.7,stagger:.04,ease:'power3.out',clearProps:'transform'});
    },page));
  }
  function queue(){if(!scheduled){scheduled=true;queueMicrotask(refresh);}}
  const observer=new MutationObserver(queue);observer.observe(page,{childList:true,subtree:true});
  function preferences(){contexts.forEach(c=>c.revert());contexts=[];queue();}
  reduced.addEventListener('change',preferences);contrast.addEventListener('change',preferences);
  window.addEventListener('hashchange',queue);
  // A single delegated hover context; no listeners accumulated by table redraws.
  const mm=gs?.matchMedia();
  mm?.add('(prefers-reduced-motion: no-preference) and (pointer: fine)',context=>{
    context.add('hover',(el,up)=>gs.to(el,{y:up?-2:0,duration:.22,ease:'power2.out',overwrite:true}));
    const over=e=>{const b=e.target.closest('.btn');if(b&&!b.disabled&&!b.contains(e.relatedTarget))context.hover(b,true);};
    const out=e=>{const b=e.target.closest('.btn');if(b&&!b.contains(e.relatedTarget))context.hover(b,false);};
    document.addEventListener('pointerover',over);document.addEventListener('pointerout',out);
    return ()=>{document.removeEventListener('pointerover',over);document.removeEventListener('pointerout',out);};
  });
  window.addEventListener('pagehide',()=>{liquid?.destroy();liquid=null;contexts.forEach(c=>c.revert());contexts=[];mm?.revert();observer.disconnect();},{once:true});
  refresh();
})();
