"use strict";
/* =========================================================
   DRIVE: realistic-feel top-down car sim, parking puzzles + free drive
   ========================================================= */
const CTRL = { wheel:0, gas:0, brake:0, gear:'P', hand:false, blinkL:false, blinkR:false };
const Drive = (function(){
  const WB = 2.6, MAXSTEER = 0.58;
  let L, world, car, cam, t, bumps, coneHits, bumpCd, nextFlag, coinsGot, coinsNeed, done, readyT, parkedOk, skids, puffs, shake, odo, jobs, job, jobCount, coinRun, demo, dayT, lastHint, finishCb, startT;
  const P = { accel:3.6, rev:2.2, vmax:26, vrev:5.5, creep:1.3, brake:8.5, hand:5.5, roll:0.35, drag:0.0045 };

  function obb(x,y,a,hx,hy){ return {x,y,a,c:Math.cos(a),s:Math.sin(a),hx,hy}; }
  function load(level, isDemo){
    L = level; demo=!!isDemo; ap=null; t=0; bumps=0; coneHits=0; bumpCd=0; nextFlag=0; coinsGot=0; done=false; readyT=0; parkedOk=false; skids=[]; puffs=[]; shake=0; odo=0; jobCount=0; coinRun=0; dayT=0.18; lastHint=''; startT=0;
    const D=Math.PI/180;
    world = { w:L.w, h:L.h, town:!!L.town, solids:[], trees:(L.trees||[]).map(a=>({x:a[0],y:a[1],r:a[2]})), cones:(L.cones||[]).map(a=>({x:a[0],y:a[1],vx:0,vy:0,hit:false,a:0})),
      coins:(L.coins||[]).map(a=>({x:a[0],y:a[1],got:false})), flags:(L.flags||[]).map(a=>({x:a[0],y:a[1]})), marks:(L.marks||[]).slice(), paves:L.paves||[], lots:L.lots||[] };
    (L.walls||[]).forEach(w=>{ const o=obb(w[0]+w[2]/2, w[1]+w[3]/2, 0, w[2]/2, w[3]/2); o.style=w[4]||'c'; o.col=w[5]; o.rect=w; world.solids.push(o); });
    (L.cars||[]).forEach(c=>{ const o=obb(c[0],c[1],c[2]*D,CAR_L/2,CAR_W/2); o.style='car'; o.col=PARK_COLORS[c[3]%PARK_COLORS.length]; world.solids.push(o); if(!L.town) world.marks.push([c[0],c[1],c[2]]); });
    // boundary
    const T=2; [[-T,-T,L.w+2*T,T],[-T,L.h,L.w+2*T,T],[-T,0,T,L.h],[L.w,0,T,L.h]].forEach(w=>{ const o=obb(w[0]+w[2]/2,w[1]+w[3]/2,0,w[2]/2,w[3]/2); o.style='edge'; o.rect=w; world.solids.push(o); });
    if(L.bay){ const b=L.bay; world.bay={x:b.x,y:b.y,a:b.a*D,w:b.w||2.8,l:b.l||5.6,any:!!b.any}; if(!L.town) world.marks.push([b.x,b.y,b.a,b.w||2.8,b.l||5.6]); }
    coinsNeed = L.needCoins ? world.coins.length : 0;
    car = {x:L.start[0], y:L.start[1], a:L.start[2]*D, v:0, steer:0, yawR:0};
    cam = {x:car.x, y:car.y, a: S.camRot ? -car.a-Math.PI/2 : 0, z:1};
    if(world.town){ newJob(); for(let i=0;i<30;i++) spawnCoin(true); }
    CTRL.gear = demo ? 'D' : 'P'; CTRL.gas=0; CTRL.brake=0; CTRL.hand=false; CTRL.wheel=0; CTRL.blinkL=CTRL.blinkR=false;
  }
  // ---------- free drive helpers ----------
  function roadPoint(){ const {CELL,ROAD,B}=L; const i=Math.floor(Math.random()*(B+1)), along=ROAD+Math.random()*(B*CELL-ROAD), lane=(Math.random()<0.5?-1:1)*2.8;
    return Math.random()<0.5 ? {x:i*CELL+ROAD/2+lane, y:along} : {x:along, y:i*CELL+ROAD/2+lane}; }
  function spawnCoin(any){ for(let k=0;k<20;k++){ const p=roadPoint(), d=Math.hypot(p.x-car.x,p.y-car.y); if(any ? d<220 : (d>50&&d<200)){ world.coins.push({x:p.x,y:p.y,got:false}); return; } } }
  function newJob(){
    const cands=[]; world.lots.forEach(l=>l.bays.forEach(b=>{ const d=Math.hypot(b.x-car.x,b.y-car.y); if(d>60&&d<260) cands.push(b); }));
    if(!cands.length) world.lots.forEach(l=>l.bays.forEach(b=>cands.push(b)));
    const b=cands[Math.floor(Math.random()*cands.length)]; if(!b) return;
    world.bay={x:b.x,y:b.y,a:b.a*Math.PI/180,w:2.8,l:5.6,any:true}; job={reward: 20+Math.round(Math.hypot(b.x-car.x,b.y-car.y)/8), t:0};
  }
  // ---------- collision ----------
  function sat(A,B){
    let best=1e9,nx=0,ny=0; const dx=B.x-A.x, dy=B.y-A.y;
    const ax=[[A.c,A.s],[-A.s,A.c],[B.c,B.s],[-B.s,B.c]];
    for(let i=0;i<4;i++){ const X=ax[i][0], Y=ax[i][1];
      const ra=A.hx*Math.abs(A.c*X+A.s*Y)+A.hy*Math.abs(-A.s*X+A.c*Y), rb=B.hx*Math.abs(B.c*X+B.s*Y)+B.hy*Math.abs(-B.s*X+B.c*Y);
      const d=dx*X+dy*Y, o=ra+rb-Math.abs(d); if(o<=0) return null; if(o<best){ best=o; const sg=d>0?-1:1; nx=X*sg; ny=Y*sg; } }
    return {nx,ny,d:best};
  }
  function circ(A,px,py,r){ // push for A away from circle
    const dx=px-A.x, dy=py-A.y, lx=dx*A.c+dy*A.s, ly=-dx*A.s+dy*A.c;
    const cx_=clamp(lx,-A.hx,A.hx), cy_=clamp(ly,-A.hy,A.hy); let ex=lx-cx_, ey=ly-cy_, d=Math.hypot(ex,ey);
    if(d>=r) return null;
    let nlx, nly, depth;
    if(d<1e-6){ const ox=A.hx-Math.abs(lx), oy=A.hy-Math.abs(ly); if(ox<oy){ nlx=-Math.sign(lx)||1; nly=0; depth=ox+r; } else { nlx=0; nly=-Math.sign(ly)||1; depth=oy+r; } }
    else { nlx=-ex/d; nly=-ey/d; depth=r-d; }
    return {nx:nlx*A.c-nly*A.s, ny:nlx*A.s+nly*A.c, d:depth};
  }
  function hit(n, isCar){
    const hx=Math.cos(car.a), hy=Math.sin(car.a), vx=hx*car.v, vy=hy*car.v, vn=vx*n.nx+vy*n.ny;
    car.x+=n.nx*n.d; car.y+=n.ny*n.d;
    if(vn<0){
      const imp=-vn, head=Math.abs(hx*n.nx+hy*n.ny);
      car.v = head>0.35 ? -car.v*0.22 : car.v*0.8;
      if(imp>0.8 && bumpCd<=0 && !demo){ bumps++; bumpCd=0.7; SFX.bump(Math.min(1,imp/6)); vib(Math.min(90,20+imp*10)); shake=Math.min(0.5,imp*0.06); if(!done && !L.town) toast(imp>4?'Ouch. That one left a dent.':'Bump! Easy does it.'); }
    }
  }
  function carBox(){ return obb(car.x,car.y,car.a,CAR_L/2,CAR_W/2); }
  // ---------- step ----------
  function step(dt){
    t+=dt; if(bumpCd>0) bumpCd-=dt; if(shake>0) shake=Math.max(0,shake-dt*1.5);
    if(done){ car.v*=Math.pow(0.05,dt); camera(dt); fx(dt); return; }
    if(demo) autopilot();
    const C=CTRL;
    // steering: wheel -> front wheel angle, softened at speed like a real rack
    const target = C.wheel*MAXSTEER/(1+car.v*car.v/260);
    car.steer += (target-car.steer)*Math.min(1,dt*10);
    // longitudinal
    const sp=car.v; let acc=0;
    if(C.gear==='D'){ acc = C.gas*P.accel*Math.max(0,1-sp/P.vmax); if(C.gas<0.05 && C.brake<0.05 && !C.hand && sp<P.creep) acc += 1.2; }
    else if(C.gear==='R'){ acc = -(C.gas*P.rev*Math.max(0,1+sp/P.vrev)); if(C.gas<0.05 && C.brake<0.05 && !C.hand && sp>-P.creep*0.8) acc -= 1.0; }
    car.v += acc*dt;
    let fr = P.roll + P.drag*sp*sp + C.brake*P.brake + (C.hand?P.hand:0) + (C.gear==='P'?12:0);
    const dv=fr*dt; if(Math.abs(car.v)<=dv) car.v=0; else car.v -= Math.sign(car.v)*dv;
    // heading (bicycle model), handbrake loosens the rear
    let yaw = car.v/WB*Math.tan(car.steer); if(C.hand && Math.abs(car.v)>4) yaw*=1.35;
    car.yawR = yaw; car.a += yaw*dt;
    const ox=car.x, oy=car.y;
    car.x += Math.cos(car.a)*car.v*dt; car.y += Math.sin(car.a)*car.v*dt;
    odo += Math.hypot(car.x-ox, car.y-oy);
    // collisions
    let A=carBox();
    for(const s of world.solids){ if(Math.abs(s.x-car.x)>s.hx+s.hy+4 || Math.abs(s.y-car.y)>s.hx+s.hy+4) continue; const n=sat(A,s); if(n){ hit(n, s.style==='car'); A=carBox(); } }
    for(const tr of world.trees){ if(Math.abs(tr.x-car.x)>tr.r+4||Math.abs(tr.y-car.y)>tr.r+4) continue; const n=circ(A,tr.x,tr.y,tr.r*0.55); if(n){ hit(n); A=carBox(); } }
    const vx=Math.cos(car.a)*car.v, vy=Math.sin(car.a)*car.v;
    for(const c of world.cones){
      c.x+=c.vx*dt; c.y+=c.vy*dt; c.vx*=Math.pow(0.08,dt); c.vy*=Math.pow(0.08,dt); c.x=clamp(c.x,0.3,world.w-0.3); c.y=clamp(c.y,0.3,world.h-0.3);
      if(Math.abs(c.x-car.x)>4||Math.abs(c.y-car.y)>4) continue;
      const n=circ(A,c.x,c.y,0.32); if(n){ c.x-=n.nx*n.d*1.05; c.y-=n.ny*n.d*1.05; c.vx=vx*1.2-n.nx*1.5; c.vy=vy*1.2-n.ny*1.5; c.a+=1.5; if(!c.hit && !demo){ c.hit=true; coneHits++; SFX.cone(); vib(15); } }
    }
    // coins
    for(const c of world.coins){ if(!c.got && (c.x-car.x)**2+(c.y-car.y)**2<1.8*1.8){ c.got=true; coinsGot++; coinRun++; if(!demo){ SFX.coin(); vib(8); } if(coinsNeed && coinsGot===coinsNeed){ toast('Bay unlocked'); SFX.ding(); } } }
    if(world.town){ world.coins=world.coins.filter(c=>!c.got && Math.hypot(c.x-car.x,c.y-car.y)<320); while(world.coins.length<30) spawnCoin(false); dayT=(dayT+dt/360)%1; if(job) job.t+=dt; }
    // flags
    const f=world.flags[nextFlag]; if(f && (f.x-car.x)**2+(f.y-car.y)**2<2.6*2.6){ nextFlag++; SFX.ding(); vib(15); if(nextFlag===world.flags.length) toast('All pads done. Now park!'); }
    // parking check
    parkedOk = bayCheck();
    if(parkedOk && Math.abs(car.v)<0.25 && C.gear==='P'){ readyT+=dt; if(readyT>0.35) finish(); } else readyT=0;
    // skids + smoke
    const hard = (C.brake>0.6 && Math.abs(car.v)>6) || (C.hand && Math.abs(car.v)>3) || (Math.abs(car.yawR*car.v)>9);
    if(hard){ const hx=Math.cos(car.a), hy=Math.sin(car.a), bx=car.x-hx*1.3, by=car.y-hy*1.3, nx=-hy*0.75, ny=hx*0.75;
      if(car._lb) skids.push([car._lb[0],car._lb[1],bx+nx,by+ny],[car._lb[2],car._lb[3],bx-nx,by-ny]); car._lb=[bx+nx,by+ny,bx-nx,by-ny];
      if(Math.random()<0.5) puffs.push({x:bx+rnd(-.4,.4),y:by+rnd(-.4,.4),r:0.4,life:0.9}); } else car._lb=null;
    if(skids.length>900) skids.splice(0,skids.length-900);
    if(!demo){ const v=Math.abs(car.v); const gearBand=[0,5,10,16,22,40]; let gi=0; while(v>gearBand[gi+1]) gi++; const rpm = C.gear==='N'||C.gear==='P' ? 0.15+C.gas*0.7 : 0.2+0.75*(v-gearBand[gi])/(gearBand[gi+1]-gearBand[gi]); setLoops(hard?0.7:0, clamp(rpm,0,1), true); }
    fx(dt); camera(dt);
  }
  function bayCheck(){
    const b=world.bay; if(!b) return false;
    if(nextFlag<world.flags.length || coinsGot<coinsNeed) return false;
    const c=Math.cos(b.a), s=Math.sin(b.a), hc=Math.cos(car.a), hs=Math.sin(car.a);
    for(const [u,v] of [[1,1],[1,-1],[-1,1],[-1,-1]]){
      const px=car.x+hc*u*CAR_L/2-hs*v*CAR_W/2, py=car.y+hs*u*CAR_L/2+hc*v*CAR_W/2, dx=px-b.x, dy=py-b.y;
      if(Math.abs(dx*c+dy*s)>b.l/2 || Math.abs(-dx*s+dy*c)>b.w/2) return false; }
    let da=Math.abs(normA(car.a-b.a)); if(b.any) da=Math.min(da, Math.PI-da);
    return da < 0.26;
  }
  function finish(){
    if(world.town){ const r=job?job.reward:20; addCoins(r); jobCount++; SFX.park(); vib(50); banner('PARKED','+'+r+' coins','#2a9d8f'); Missions.progress('jobs',1,'add'); CTRL.gear='P'; readyT=-1.5; newJob(); return; }
    done=true; SFX.park(); vib(60); setLoops(0,0,false);
    const pen=bumps+coneHits, stars = pen===0?3:pen<=2?2:1;
    setTimeout(()=>finishCb && finishCb({stars, bumps, cones:coneHits, time:t, coins:coinRun}), 900);
  }
  function normA(a){ while(a>Math.PI) a-=TAU; while(a<-Math.PI) a+=TAU; return a; }
  // demo: slow loops around the menu map
  let ap=null;
  function autopilot(){
    const {CELL,ROAD,B}=L, D=[[1,0],[0,1],[-1,0],[0,-1]], half=ROAD/2;
    if(!ap){ const hx=Math.cos(car.a), hy=Math.sin(car.a); ap={dir: Math.abs(hx)>Math.abs(hy) ? (hx>0?0:2) : (hy>0?1:3), last:''}; }
    let [dx,dy]=D[ap.dir];
    const ci=Math.round((car.x-half)/CELL), cj=Math.round((car.y-half)/CELL), xc=ci*CELL+half, yc=cj*CELL+half;
    if(Math.abs(car.x-xc)<3 && Math.abs(car.y-yc)<3 && ap.last!==ci+','+cj){
      ap.last=ci+','+cj; const ok=d=>{ const ni=ci+D[d][0], nj=cj+D[d][1]; return ni>=0&&nj>=0&&ni<=B&&nj<=B; };
      const opts=[ap.dir,(ap.dir+1)%4,(ap.dir+3)%4].filter(ok); let nd = opts.includes(ap.dir)&&Math.random()<0.5 ? ap.dir : opts[Math.floor(Math.random()*opts.length)];
      if(nd===undefined) nd=(ap.dir+2)%4; ap.dir=nd; [dx,dy]=D[nd];
    }
    let tx, ty;
    if(dx){ const j=Math.round((car.y-half)/CELL); ty=j*CELL+half+2.8*dx; tx=car.x+dx*7; } else { const i=Math.round((car.x-half)/CELL); tx=i*CELL+half-2.8*dy; ty=car.y+dy*7; }
    const err=normA(Math.atan2(ty-car.y,tx-car.x)-car.a);
    CTRL.gear='D'; CTRL.wheel=clamp(err*2.2,-1,1);
    const vt = Math.abs(err)>0.35 ? 3.5 : 7; CTRL.gas = car.v<vt ? 0.5 : 0; CTRL.brake = car.v>vt+1.5 ? 0.4 : 0;
  }
  function fx(dt){ for(const p of puffs){ p.r+=dt*1.6; p.life-=dt; } puffs=puffs.filter(p=>p.life>0); }
  function camera(dt){
    const hx=Math.cos(car.a), hy=Math.sin(car.a), look=clamp(car.v,-6,30)*0.35;
    cam.x += (car.x+hx*look-cam.x)*Math.min(1,dt*4); cam.y += (car.y+hy*look-cam.y)*Math.min(1,dt*4);
    const ta = S.camRot ? -car.a-Math.PI/2 : 0; cam.a += normA(ta-cam.a)*Math.min(1,dt*(S.camRot?2.4:6));
    const tz = 1/(1+Math.abs(car.v)/45); cam.z += (tz-cam.z)*Math.min(1,dt*1.5);
  }
  // ---------- render ----------
  let grain=null;
  function grainPat(c){ if(grain) return grain; const g=document.createElement('canvas'); g.width=g.height=96; const k=g.getContext('2d'); k.fillStyle='#55545e'; k.fillRect(0,0,96,96);
    for(let i=0;i<900;i++){ k.fillStyle=Math.random()<0.5?'rgba(255,255,255,.05)':'rgba(0,0,0,.08)'; k.fillRect(Math.random()*96,Math.random()*96,1+Math.random()*1.5,1+Math.random()*1.5); } grain=c.createPattern(g,'repeat'); return grain; }
  function lineRect(c,x,y,a,w,l){ c.save(); c.translate(x,y); c.rotate(a); c.beginPath(); c.moveTo(-l/2,-w/2); c.lineTo(l/2,-w/2); c.moveTo(-l/2,w/2); c.lineTo(l/2,w/2); c.moveTo(-l/2,-w/2); c.lineTo(-l/2,w/2); c.stroke(); c.restore(); }
  function render(c, W, H, viewTop, viewH){
    const ppm = clamp(W/21, 14, 40)*cam.z;
    c.save();
    c.fillStyle='#86b86a'; c.fillRect(0,0,W,H);
    const sx = shake? rnd(-shake,shake)*ppm*0.3 : 0;
    c.translate(W/2+sx, viewTop+viewH*(S.camRot?0.64:0.52)); c.scale(ppm,ppm); c.rotate(cam.a); c.translate(-cam.x,-cam.y);
    const R = Math.hypot(W,H)/ppm*0.75; const vis=(x,y,r)=>Math.abs(x-cam.x)<R+r && Math.abs(y-cam.y)<R+r;
    const pat=grainPat(c); if(pat.setTransform) pat.setTransform(new DOMMatrix().scale(0.04));
    // ground
    c.fillStyle=pat; c.fillRect(0,0,world.w,world.h);
    c.lineWidth=0.08; c.strokeStyle=INK;
    if(world.town){
      for(const p of world.paves){ if(!vis(p[0]+p[2]/2,p[1]+p[3]/2,40)) continue; c.fillStyle='#d8cfbb'; c.fillRect(p[0],p[1],p[2],p[3]); c.strokeRect(p[0],p[1],p[2],p[3]);
        const lot=world.lots.find(l=>l.x>p[0]&&l.x<p[0]+p[2]&&l.y>p[1]&&l.y<p[1]+p[3]); if(lot){ c.fillStyle=pat; c.fillRect(lot.x,lot.y,lot.w,lot.h); } else { c.fillStyle='#8cc06e'; c.fillRect(p[0]+2.5,p[1]+2.5,p[2]-5,p[3]-5); } }
      // road paint
      const {CELL,ROAD,B}=L; c.strokeStyle='#f2c14e'; c.lineWidth=0.18; c.setLineDash([2.4,2.6]); c.beginPath();
      for(let i=0;i<=B;i++) for(let j=0;j<B;j++){ const m=i*CELL+ROAD/2, a=j*CELL+ROAD+1, b=(j+1)*CELL-1; if(vis(m,(a+b)/2,40)){ c.moveTo(m,a); c.lineTo(m,b); } if(vis((a+b)/2,m,40)){ c.moveTo(a,m); c.lineTo(b,m); } }
      c.stroke(); c.setLineDash([]);
      c.strokeStyle='rgba(255,255,255,.85)'; c.lineWidth=0.35; // zebra crossings
      for(let i=0;i<=B;i++) for(let j=0;j<=B;j++){ const x=i*CELL, y=j*CELL; if(!vis(x+ROAD/2,y+ROAD/2,20)) continue; c.beginPath(); for(let k=1;k<6;k++){ c.moveTo(x+k*2,y+ROAD+0.6); c.lineTo(x+k*2,y+ROAD+2.6); c.moveTo(x+ROAD+0.6,y+k*2); c.lineTo(x+ROAD+2.6,y+k*2); } c.stroke(); }
    }
    // painted bay lines
    c.strokeStyle='rgba(245,240,228,.9)'; c.lineWidth=0.13;
    for(const m of world.marks){ if(!vis(m[0],m[1],6)) continue; lineRect(c,m[0],m[1],m[2]*Math.PI/180,m[3]||3,m[4]||5.6); }
    // skids
    c.strokeStyle='rgba(25,20,30,.35)'; c.lineWidth=0.28; c.lineCap='round'; c.beginPath(); for(const s of skids){ c.moveTo(s[0],s[1]); c.lineTo(s[2],s[3]); } c.stroke();
    // target bay
    const b=world.bay;
    if(b && !done){ const locked = nextFlag<world.flags.length || coinsGot<coinsNeed;
      c.save(); c.translate(b.x,b.y); c.rotate(b.a);
      c.fillStyle = locked ? 'rgba(120,120,130,.25)' : parkedOk ? 'rgba(42,157,143,.45)' : `rgba(242,177,52,${0.22+0.12*Math.sin(t*4)})`; c.fillRect(-b.l/2,-b.w/2,b.l,b.w);
      c.strokeStyle = locked ? '#9a98a3' : parkedOk ? '#2a9d8f' : '#f2b134'; c.lineWidth=0.18; c.setLineDash([0.7,0.45]); c.strokeRect(-b.l/2,-b.w/2,b.l,b.w); c.setLineDash([]);
      c.fillStyle=c.strokeStyle; c.beginPath(); c.moveTo(b.l/2-0.5,0); c.lineTo(b.l/2-1.4,-0.6); c.lineTo(b.l/2-1.4,0.6); c.fill(); if(b.any){ c.beginPath(); c.moveTo(-b.l/2+0.5,0); c.lineTo(-b.l/2+1.4,-0.6); c.lineTo(-b.l/2+1.4,0.6); c.fill(); }
      c.rotate(-b.a-cam.a); c.font='bold 1.5px Lilita, sans-serif'; c.textAlign='center'; c.textBaseline='middle'; c.fillText(locked?'🔒':'P',0,0.05); c.restore(); }
    // flags
    world.flags.forEach((f,i)=>{ if(!vis(f.x,f.y,4)) return; const on=i===nextFlag, past=i<nextFlag; c.save(); c.translate(f.x,f.y);
      c.fillStyle= past?'rgba(42,157,143,.35)': on?`rgba(232,85,62,${0.5+0.2*Math.sin(t*5)})`:'rgba(255,255,255,.25)'; c.beginPath(); c.arc(0,0,2.4,0,TAU); c.fill(); c.strokeStyle=INK; c.lineWidth=0.1; c.stroke();
      c.rotate(-cam.a); c.fillStyle= past?'#2a9d8f':'#f4ecdc'; c.font='1.8px Lilita, sans-serif'; c.textAlign='center'; c.textBaseline='middle'; c.fillText(past?'✓':String(i+1),0,0.1); c.restore(); });
    // shadows pass (sun from top-left in world space)
    c.fillStyle='rgba(20,15,30,.22)';
    for(const s of world.solids){ if(s.style==='edge'||s.style==='car'||!vis(s.x,s.y,s.hx+s.hy)) continue; const k = s.style==='b'?1.6:0.5; c.fillRect(s.x-s.hx+k*0.6, s.y-s.hy+k, s.hx*2, s.hy*2); }
    for(const tr of world.trees){ if(!vis(tr.x,tr.y,tr.r)) continue; c.beginPath(); c.arc(tr.x+0.5,tr.y+0.8,tr.r,0,TAU); c.fill(); }
    // solids
    for(const s of world.solids){ if(!vis(s.x,s.y,s.hx+s.hy)) continue;
      if(s.style==='car'){ c.save(); c.translate(s.x,s.y); c.rotate(s.a); drawCar(c,{body:s.col,roof:shade(s.col),stripe:s.col},{t:0}); c.restore(); continue; }
      const r=s.rect; c.lineWidth=0.1; c.strokeStyle=INK;
      if(s.style==='edge'){ c.fillStyle='#5d8f4a'; c.fillRect(r[0],r[1],r[2],r[3]); continue; }
      if(s.style==='p'){ c.fillStyle='#d8cfbb'; c.fillRect(r[0],r[1],r[2],r[3]); c.strokeRect(r[0],r[1],r[2],r[3]); c.fillStyle='#6fa357'; c.fillRect(r[0]+0.4,r[1]+0.4,r[2]-0.8,r[3]-0.8);
        c.fillStyle='#5b8f46'; const n=Math.max(2,Math.floor((r[2]*r[3])/10)); for(let i=0;i<n;i++){ const hx=hash(i,r[0]*7+r[1]), hy=hash(i+9,r[1]*3+r[2]); c.beginPath(); c.arc(r[0]+0.9+hx*(r[2]-1.8), r[1]+0.9+hy*(r[3]-1.8), 0.6+hash(i,3)*0.5, 0, TAU); c.fill(); } continue; }
      if(s.style==='f'){ c.fillStyle='#d8cfbb'; c.fillRect(r[0],r[1],r[2],r[3]); c.strokeRect(r[0],r[1],r[2],r[3]); c.fillStyle='#6cb4d6'; c.beginPath(); c.arc(s.x,s.y,r[2]*0.36,0,TAU); c.fill(); c.stroke(); c.fillStyle='rgba(255,255,255,.6)'; c.beginPath(); c.arc(s.x,s.y,0.5+0.2*Math.sin(t*3),0,TAU); c.fill(); continue; }
      if(s.style==='b'){ const col=s.col||'#d9734e'; c.fillStyle=col; c.fillRect(r[0],r[1],r[2],r[3]); c.strokeRect(r[0],r[1],r[2],r[3]);
        c.strokeStyle='rgba(34,29,43,.18)'; c.lineWidth=0.12; c.strokeRect(r[0]+0.6,r[1]+0.6,r[2]-1.2,r[3]-1.2);
        if(r[2]>6 && r[3]>6){ c.fillStyle='rgba(255,255,255,.35)'; c.fillRect(r[0]+r[2]*0.2,r[1]+r[3]*0.25,1.6,1.2); c.fillStyle='#b9b4a8'; c.fillRect(r[0]+r[2]*0.62,r[1]+r[3]*0.55,2.2,1.6); c.strokeStyle=INK; c.lineWidth=0.08; c.strokeRect(r[0]+r[2]*0.62,r[1]+r[3]*0.55,2.2,1.6); }
        continue; }
      c.fillStyle='#cfc7b5'; c.fillRect(r[0],r[1],r[2],r[3]); c.strokeRect(r[0],r[1],r[2],r[3]);
    }
    // trees
    for(const tr of world.trees){ if(!vis(tr.x,tr.y,tr.r)) continue; c.fillStyle='#3f7a3a'; c.strokeStyle=INK; c.lineWidth=0.1; c.beginPath(); c.arc(tr.x,tr.y,tr.r,0,TAU); c.fill(); c.stroke();
      c.fillStyle='#5a9a4a'; c.beginPath(); c.arc(tr.x-tr.r*0.25,tr.y-tr.r*0.25,tr.r*0.6,0,TAU); c.fill(); c.fillStyle='rgba(255,255,255,.12)'; c.beginPath(); c.arc(tr.x-tr.r*0.35,tr.y-tr.r*0.4,tr.r*0.25,0,TAU); c.fill(); }
    // coins
    for(const o of world.coins){ if(o.got||!vis(o.x,o.y,1)) continue; const sq=Math.abs(Math.sin(t*3+o.x)); c.save(); c.translate(o.x,o.y); c.rotate(-cam.a); c.fillStyle='rgba(20,15,30,.2)'; c.beginPath(); c.ellipse(0.15,0.25,0.6,0.25,0,0,TAU); c.fill();
      c.fillStyle='#f2b134'; c.strokeStyle=INK; c.lineWidth=0.08; c.beginPath(); c.ellipse(0,-0.2,0.55*sq+0.08,0.55,0,0,TAU); c.fill(); c.stroke(); c.fillStyle='#ffe08a'; c.beginPath(); c.ellipse(-0.1*sq,-0.3,0.2*sq+0.03,0.25,0,0,TAU); c.fill(); c.restore(); }
    // cones
    for(const o of world.cones){ if(!vis(o.x,o.y,1)) continue; c.save(); c.translate(o.x,o.y); c.rotate(o.a); c.fillStyle='rgba(20,15,30,.25)'; c.fillRect(-0.3,-0.2,0.75,0.75);
      c.fillStyle='#f07b2c'; c.strokeStyle=INK; c.lineWidth=0.06; c.fillRect(-0.36,-0.36,0.72,0.72); c.strokeRect(-0.36,-0.36,0.72,0.72); c.beginPath(); c.arc(0,0,0.24,0,TAU); c.fillStyle='#f4ecdc'; c.fill(); c.stroke(); c.beginPath(); c.arc(0,0,0.1,0,TAU); c.fillStyle='#f07b2c'; c.fill(); c.restore(); }
    // puffs
    for(const p of puffs){ c.fillStyle=`rgba(240,236,228,${0.4*p.life})`; c.beginPath(); c.arc(p.x,p.y,p.r,0,TAU); c.fill(); }
    // player car
    const cd = CARS.find(x=>x.id===S.car)||CARS[0];
    const night = world.town ? nightK() : 0;
    c.save(); c.translate(car.x,car.y); c.rotate(car.a); drawCar(c, cd, {steer:car.steer, brake:CTRL.brake>0.1||CTRL.gear==='P', reverse:CTRL.gear==='R', blinkL:CTRL.blinkL, blinkR:CTRL.blinkR, t, lights:night>0.35}); c.restore();
    c.restore();
    if(night>0){ c.fillStyle=`rgba(28,24,60,${night*0.45})`; c.fillRect(0,0,W,H); }
    if(world.town && dayT>0.55 && dayT<0.72){ const k=1-Math.abs(dayT-0.635)/0.085; c.fillStyle=`rgba(255,140,60,${0.12*k})`; c.fillRect(0,0,W,H); }
  }
  function nightK(){ return dayT<0.68?0 : dayT<0.76 ? (dayT-0.68)/0.08 : dayT<0.94 ? 1 : 1-(dayT-0.94)/0.06; }
  function hash(i,j){ let h=(i*374761393+Math.floor(j*1000)*668265263)|0; h=(h^(h>>>13))*1274126177|0; return ((h^(h>>>16))>>>0)/4294967295; }
  function shade(hex){ const n=parseInt(hex.slice(1),16); const r=(n>>16)*0.82|0, g=((n>>8)&255)*0.82|0, b=(n&255)*0.82|0; return `rgb(${r},${g},${b})`; }
  // screen-space arrow toward the job bay (free drive) or locked hint
  function pointer(){
    const b=world.bay; if(!b) return null; const dx=b.x-car.x, dy=b.y-car.y, d=Math.hypot(dx,dy);
    const a=Math.atan2(dy,dx)+cam.a; return {a, d};
  }
  return {
    load, step, render, pointer, P,
    set onFinish(f){ finishCb=f; },
    get state(){ return {v:car.v, kmh:Math.abs(car.v)*3.6, bumps, cones:coneHits, t, nextFlag, flags:world.flags.length, coinsGot, coinsNeed, parkedOk, done, odo, jobs:jobCount, coins:coinRun, town:world.town, job, dayT}; },
    dbg(){ return {car, world, cam}; }
  };
})();
