"use strict";
/* =========================================================
   UI, game flow, controls, missions, garage, main loop
   ========================================================= */
const MPOOL = [
  {k:'park',   t:'Finish {n} parking puzzles', n:[2,3,5], r:[50,80,120], ic:'p'},
  {k:'stars3', t:'Get 3 stars on {n} puzzles', n:[1,2,3], r:[60,90,130], ic:'star'},
  {k:'clean',  t:'Park {n} times without a bump', n:[1,3,5], r:[50,90,140], ic:'check'},
  {k:'jobs',   t:'Park in {n} free-drive bays', n:[2,4,7], r:[60,100,150], ic:'p'},
  {k:'km',     t:'Drive {n} km in Free Drive', n:[1,3,6], r:[50,90,140], ic:'road'},
  {k:'coinsRun',t:'Pick up {n} coins in one drive', n:[10,25,45], r:[40,80,120], ic:'coin'},
  {k:'runs',   t:'Go for {n} drives', n:[3,6,10], r:[30,50,80], ic:'play'},
];
const ICONS = {
  road:'<path d="M4 20L9 4M20 20L15 4M12 6v2M12 11v2M12 16v2"/>',
  p:'<rect x="4" y="3" width="16" height="18" rx="3"/><path d="M10 17V7h3a3 3 0 0 1 0 6h-3"/>',
  star:'<path d="M12 2l3 7h7l-5.5 4 2 7L12 16l-6.5 4 2-7L2 9h7z"/>',
  coin:'<circle cx="12" cy="12" r="8"/><path d="M12 8v8"/>',
  play:'<path d="M7 4l12 8-12 8z"/>',
  check:'<path d="M5 12l5 5 9-10"/>',
  lock:'<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  bump:'<path d="M12 2l2 6 6-2-3 5 5 3-6 1 1 6-5-4-4 5v-6l-6-1 5-3-3-5 6 2z"/>',
};
const Missions = {
  ensure(){ if(!S.missions || S.misDay!==dayKey() || S.missions.some(m=>!MPOOL.find(p=>p.k===m.k))) this.roll(); },
  roll(){
    const lv = Math.min(2, Math.floor(level()/4));
    const pool = MPOOL.slice().sort(()=>Math.random()-.5).slice(0,3);
    S.missions = pool.map(m=>({k:m.k, t:m.t.replace('{n}', m.n[lv].toLocaleString()), n:m.n[lv], r:m.r[lv], ic:m.ic, p:0, done:false, claimed:false}));
    S.misDay = dayKey(); save();
  },
  progress(k, v, mode){
    if(!S.missions) return; let ch=false;
    for(const m of S.missions){ if(m.k!==k||m.done) continue; const o=m.p; m.p = mode==='max'?Math.max(m.p,v):m.p+v; if(m.p>=m.n){ m.p=m.n; m.done=true; toast('Mission done: '+m.t); vib(30); } if(m.p!==o) ch=true; }
    if(ch){ save(); UI.dots(); }
  },
  render(){
    const Lst=$('misList');
    Lst.innerHTML = S.missions.map((m,i)=>`<div class="mis stk"><div class="ic"><svg viewBox="0 0 24 24">${ICONS[m.claimed?'check':m.ic]||ICONS.play}</svg></div><div class="tx"><div>${m.t}</div><small><i class="coin" style="width:12px;height:12px;vertical-align:-1px"></i> ${m.r} · ${(+Math.min(m.p,m.n).toFixed(1)).toLocaleString()} / ${m.n.toLocaleString()}</small><div class="bar"><i style="width:${m.p/m.n*100}%"></i></div></div>${m.done&&!m.claimed?`<button class="btn sm" data-claim="${i}">Claim</button>`:''}</div>`).join('') + '<div class="empty" style="padding:12px">Fresh missions every morning.</div>';
    Lst.querySelectorAll('[data-claim]').forEach(b=>b.onclick=()=>{ const m=S.missions[+b.dataset.claim]; m.claimed=true; addCoins(m.r); S.xp+=40; SFX.coin(); vib(30); save(); this.render(); UI.dots(); });
    const avail = S.claimedDay!==dayKey(), streak = S.claimedDay===dayKey(-1) ? S.streak : (avail?0:S.streak), day = avail ? (streak%7)+1 : ((S.streak-1)%7)+1;
    $('dayTxt').textContent = avail ? `Day ${day} · ${day*20} coins waiting` : `Streak ${S.streak} · see you tomorrow`;
    $('days').innerHTML = [1,2,3,4,5,6,7].map(i=>`<div class="${i<day||(!avail&&i<=day)?'done':''}${avail&&i===day?' today':''}">D${i}</div>`).join('');
    const b=$('claimDay'); b.disabled=!avail; b.textContent = avail?'Claim':'Claimed';
    b.onclick=()=>{ if(S.claimedDay===dayKey()) return; S.streak = streak+1; S.claimedDay=dayKey(); addCoins(day*20); SFX.bank(); vib(40); save(); this.render(); UI.dots(); UI.topbar(); };
  }
};

// ---------------- GAME ----------------
const TOWN = makeTown(7);
const Game = {
  active:false, paused:false, ended:false, kind:'park', li:0, hintT:0,
  start(kind, li){
    initAudio(); ensureLoops();
    this.kind=kind; this.li = li|0; this.active=true; this.paused=false; this.ended=false; this.hintT=7;
    Drive.load(kind==='free' ? TOWN : LEVELS[this.li], false);
    wheelDeg=0; tiltBase=null;
    $('shell').classList.add('hide'); $('hud').classList.remove('hide'); $('overOv').classList.add('hide'); $('pauseOv').classList.add('hide');
    $('hTitle').textContent = kind==='free' ? 'Free Drive' : `${this.li+1}. ${LEVELS[this.li].name}`;
    $('endB').style.display = kind==='free' ? '' : 'none'; $('restartB').style.display = kind==='free' ? 'none' : '';
    if(!Music.playing && S.auto) autoMusic();
    placeYT(); Controls.sync();
    S.runs++; save(); Missions.progress('runs',1,'add');
  },
  finished(r){
    if(this.ended) return; this.ended=true; setLoops(0,0,false); hornOn(false);
    const prev = S.stars[this.li]||0; const better = r.stars>prev;
    if(better) S.stars[this.li]=r.stars;
    const reward = 10 + (better ? (r.stars-prev)*20 : 0) + r.coins;
    addCoins(reward); S.xp += 20+r.stars*10; save();
    Missions.progress('park',1,'add'); if(r.stars===3) Missions.progress('stars3',1,'add'); if(r.bumps+r.cones===0) Missions.progress('clean',1,'add');
    const titles = r.stars===3 ? ['Textbook!','Smooth operator','Clean as a whistle','Driving-test perfect'] : r.stars===2 ? ['Nicely done','Parked!','Not bad at all'] : ['Parked. Sort of.','A bit scratched, but in!','Home safe'];
    $('oTag').textContent = 'LEVEL '+(this.li+1)+' · PARKED'; $('oTitle').textContent = titles[Math.floor(Math.random()*titles.length)];
    $('oStars').style.display=''; const st=$('oStars').children; for(let i=0;i<3;i++){ st[i].classList.remove('on'); if(i<r.stars) setTimeout(()=>{ st[i].classList.add('on'); SFX.coin(); vib(20); }, 250+i*260); }
    $('oStats').innerHTML = [[fmtT(r.time),'time'],[r.bumps,'bumps'],[r.cones,'cones'],['+'+reward,'coins']].map(s=>`<div><b>${s[0]}</b>${s[1]}</div>`).join('');
    $('oNote').textContent = r.stars<3 ? 'Zero bumps and zero cones gets you all three stars.' : (this.li===LEVELS.length-1 ? 'You finished every lot. Free Drive is all yours.' : '');
    $('nextB').style.display = this.li<LEVELS.length-1 ? '' : 'none'; $('nextB').textContent='Next level';
    $('lvB').style.display='';
    $('overOv').classList.remove('hide'); $('hud').classList.add('hide'); UI.topbar();
  },
  endDrive(){
    const s=Drive.state; this.ended=true; this.paused=false; setLoops(0,0,false); hornOn(false);
    const km = s.odo/1000; addCoins(s.coins); S.km += km; S.jobsT += s.jobs; S.xp += Math.floor(km*30 + s.jobs*25); save();
    Missions.progress('km',+km.toFixed(2),'add'); Missions.progress('coinsRun',s.coins,'max');
    $('pauseOv').classList.add('hide');
    $('oTag').textContent='FREE DRIVE'; $('oTitle').textContent = s.jobs ? 'Good drive' : 'Nice cruise';
    $('oStars').style.display='none';
    $('oStats').innerHTML = [[km.toFixed(2)+' km','driven'],[s.jobs,'parked'],['+'+s.coins,'coins'],[fmtT(s.t),'time']].map(x=>`<div><b>${x[0]}</b>${x[1]}</div>`).join('');
    $('oNote').textContent = 'Parking money was paid as you went.';
    $('nextB').style.display=''; $('nextB').textContent='Drive again'; $('lvB').style.display='none';
    $('overOv').classList.remove('hide'); $('hud').classList.add('hide'); UI.topbar();
  },
  pause(){ if(!this.active||this.ended||this.paused) return; this.paused=true; $('pauseOv').classList.remove('hide'); setLoops(0,0,false); hornOn(false); setFilter(700,0.3); },
  resume(){ this.paused=false; $('pauseOv').classList.add('hide'); setFilter(20000,0.3); },
  quit(toLevels){ this.active=false; this.paused=false; setLoops(0,0,false); hornOn(false); $('overOv').classList.add('hide'); $('pauseOv').classList.add('hide'); $('hud').classList.add('hide'); $('shell').classList.remove('hide'); setFilter(20000,0.3); Drive.load(TOWN,true); placeYT(); UI.refresh(); if(toLevels) UI.go('levels'); }
};
Drive.onFinish = r => Game.finished(r);
function fmtT(s){ s=Math.floor(s); return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); }
function autoMusic(){
  if(Music.playing) return;
  if(S.hits && S.hits.length && AND.yt){ const i=Math.floor(Math.random()*Math.min(25,S.hits.length)); Music.playList(S.hits, i); }
  else Music.playList(Music.list('local'), 0);
}

// ---------------- CONTROLS ----------------
const WHEEL_MAX = 450; // degrees each way
let wheelDeg = 0, wheelHeld = false, tiltBase = null, tiltGamma = null, tiltSeen = false;
const pedal = { gas:0, brake:0 };
const keys = {};
const Controls = {
  sync(){
    const tilt = S.ctrl==='tilt';
    $('tiltTag').classList.toggle('hide', !tilt);
    document.querySelectorAll('#gearbox button').forEach(b=>b.classList.toggle('on', b.dataset.g===CTRL.gear));
    $('hbBtn').classList.toggle('on', CTRL.hand); $('blL').classList.toggle('on', CTRL.blinkL); $('blR').classList.toggle('on', CTRL.blinkR);
    if(tilt && !tiltSeen) setTimeout(()=>{ if(!tiltSeen && Game.active) toast('No tilt sensor found. Switch to Wheel in Settings.'); }, 2500);
  },
  shift(g){
    if(g===CTRL.gear) return;
    const v = Drive.state.v;
    if(CTRL.gear==='P' && pedal.brake<0.2 && !keys.ArrowDown){ toast('Foot on the brake to shift out of P'); vib(20); return; }
    if(g==='P' && Math.abs(v)>1){ toast('Stop the car before Park'); vib(20); return; }
    if((g==='R' && v>1.5) || (g==='D' && v<-1.5)){ toast('Stop first, then change direction'); vib(20); return; }
    CTRL.gear=g; SFX.shift(); vib(12); this.sync();
  },
  tick(dt){
    // pedals ease like a real foot
    const gT = Math.max(pedal.gas, keys.ArrowUp?1:0), bT = Math.max(pedal.brake, keys.ArrowDown?1:0);
    CTRL.gas += (gT-CTRL.gas)*Math.min(1, dt*(gT>CTRL.gas?5:9));
    CTRL.brake += (bT-CTRL.brake)*Math.min(1, dt*(bT>CTRL.brake?9:12));
    // steering
    if(S.ctrl==='tilt' && tiltGamma!==null && !keys.ArrowLeft && !keys.ArrowRight){
      if(tiltBase===null) tiltBase=tiltGamma;
      const range = 32*100/S.sens; let w = (tiltGamma-tiltBase)/range; if(Math.abs(w)<0.04) w=0;
      const target = clamp(w,-1,1)*WHEEL_MAX; wheelDeg += (target-wheelDeg)*Math.min(1,dt*10);
    } else if(keys.ArrowLeft || keys.ArrowRight){
      wheelDeg = clamp(wheelDeg + ((keys.ArrowRight?1:0)-(keys.ArrowLeft?1:0))*700*dt, -WHEEL_MAX, WHEEL_MAX);
    } else if(!wheelHeld){
      const v=Math.abs(Drive.state.v); wheelDeg *= Math.exp(-dt*(0.6+v*0.35)); if(Math.abs(wheelDeg)<0.5) wheelDeg=0;
    }
    CTRL.wheel = wheelDeg/WHEEL_MAX;
    drawWheel();
  }
};
// wheel canvas
const wc = $('wheel'), wg = wc.getContext('2d');
function drawWheel(){
  const sz = wc.clientWidth; if(!sz) return; if(wc.width!==sz*DPR){ wc.width=wc.height=sz*DPR; }
  const g=wg; g.setTransform(DPR,0,0,DPR,0,0); g.clearRect(0,0,sz,sz);
  const R=sz/2-4; g.save(); g.translate(sz/2,sz/2); g.rotate(wheelDeg*Math.PI/180);
  g.lineCap='round';
  // spokes
  g.strokeStyle='#221d2b'; g.lineWidth=R*0.2; g.beginPath(); g.moveTo(-R*0.85,R*0.08); g.lineTo(R*0.85,R*0.08); g.moveTo(0,R*0.1); g.lineTo(0,R*0.85); g.stroke();
  g.strokeStyle='#4a4356'; g.lineWidth=R*0.12; g.beginPath(); g.moveTo(-R*0.85,R*0.08); g.lineTo(R*0.85,R*0.08); g.moveTo(0,R*0.1); g.lineTo(0,R*0.85); g.stroke();
  // rim
  g.strokeStyle='#221d2b'; g.lineWidth=R*0.26; g.beginPath(); g.arc(0,0,R*0.84,0,TAU); g.stroke();
  g.strokeStyle='#3a3346'; g.lineWidth=R*0.18; g.beginPath(); g.arc(0,0,R*0.84,0,TAU); g.stroke();
  g.strokeStyle='rgba(255,255,255,.07)'; g.lineWidth=R*0.03; for(let i=0;i<36;i++){ const a=i/36*TAU; g.beginPath(); g.moveTo(Math.cos(a)*R*0.77,Math.sin(a)*R*0.77); g.lineTo(Math.cos(a)*R*0.91,Math.sin(a)*R*0.91); g.stroke(); }
  g.strokeStyle='#f2b134'; g.lineWidth=R*0.18; g.beginPath(); g.arc(0,0,R*0.84,-Math.PI/2-0.1,-Math.PI/2+0.1); g.stroke();
  // hub = horn
  g.fillStyle=hornHeld?'#e8553e':'#f2b134'; g.strokeStyle='#221d2b'; g.lineWidth=3; g.beginPath(); g.arc(0,0,R*0.3,0,TAU); g.fill(); g.stroke();
  g.fillStyle='#221d2b'; g.beginPath(); g.arc(-R*0.1,-R*0.06,R*0.04,0,TAU); g.arc(R*0.1,-R*0.06,R*0.04,0,TAU); g.fill();
  g.lineWidth=2.5; g.beginPath(); g.arc(0,R*0.02,R*0.13,0.3,Math.PI-0.3); g.stroke();
  g.restore();
}
let hornHeld=false, wheelPid=null, wheelLastA=0;
wc.addEventListener('pointerdown', e=>{
  e.preventDefault(); initAudio();
  const r=wc.getBoundingClientRect(), x=e.clientX-r.left-r.width/2, y=e.clientY-r.top-r.height/2, d=Math.hypot(x,y);
  if(S.ctrl==='tilt'){ if(d<r.width*0.17){ hornHeld=true; hornOn(true); } else { tiltBase=tiltGamma; toast('Steering centred'); } wc.setPointerCapture(e.pointerId); wheelPid=e.pointerId; return; }
  wc.setPointerCapture(e.pointerId); wheelPid=e.pointerId;
  if(d<r.width*0.17){ hornHeld=true; hornOn(true); return; }
  wheelHeld=true; wheelLastA=Math.atan2(y,x);
});
wc.addEventListener('pointermove', e=>{
  if(e.pointerId!==wheelPid || !wheelHeld) return;
  const r=wc.getBoundingClientRect(), x=e.clientX-r.left-r.width/2, y=e.clientY-r.top-r.height/2; if(Math.hypot(x,y)<6) return;
  const a=Math.atan2(y,x); let da=a-wheelLastA; while(da>Math.PI) da-=TAU; while(da<-Math.PI) da+=TAU; wheelLastA=a;
  wheelDeg = clamp(wheelDeg + da*180/Math.PI*1.15, -WHEEL_MAX, WHEEL_MAX);
});
['pointerup','pointercancel'].forEach(n=>wc.addEventListener(n, e=>{ if(e.pointerId!==wheelPid) return; wheelHeld=false; wheelPid=null; if(hornHeld){ hornHeld=false; hornOn(false); } }));
// pedals
function bindPedal(el, key){
  let pid=null;
  const set=e=>{ const r=el.getBoundingClientRect(); pedal[key] = clamp(0.45 + 0.6*(e.clientY-r.top)/r.height, 0.45, 1); };
  el.addEventListener('pointerdown', e=>{ e.preventDefault(); initAudio(); pid=e.pointerId; el.setPointerCapture(pid); el.classList.add('down'); set(e); vib(6); });
  el.addEventListener('pointermove', e=>{ if(e.pointerId===pid) set(e); });
  ['pointerup','pointercancel'].forEach(n=>el.addEventListener(n, e=>{ if(e.pointerId!==pid) return; pid=null; pedal[key]=0; el.classList.remove('down'); }));
}
bindPedal($('gasP'),'gas'); bindPedal($('brakeP'),'brake');
document.querySelectorAll('#gearbox button').forEach(b=>b.addEventListener('pointerdown', e=>{ e.preventDefault(); Controls.shift(b.dataset.g); }));
$('hbBtn').addEventListener('pointerdown', e=>{ e.preventDefault(); CTRL.hand=!CTRL.hand; SFX.shift(); vib(15); Controls.sync(); });
let blinkTimer=0;
$('blL').addEventListener('pointerdown', e=>{ e.preventDefault(); CTRL.blinkL=!CTRL.blinkL; CTRL.blinkR=false; Controls.sync(); SFX.tick(); });
$('blR').addEventListener('pointerdown', e=>{ e.preventDefault(); CTRL.blinkR=!CTRL.blinkR; CTRL.blinkL=false; Controls.sync(); SFX.tick(); });
addEventListener('deviceorientation', e=>{ if(e.gamma===null||e.gamma===undefined) return; tiltSeen=true; tiltGamma=e.gamma; });
addEventListener('keydown', e=>{ keys[e.key]=true; if(!Game.active) return; const k=e.key.toUpperCase(); if('PRND'.includes(k)&&k.length===1) Controls.shift(k); if(e.key===' '){ CTRL.hand=!CTRL.hand; Controls.sync(); } if(k==='H') hornOn(true); });
addEventListener('keyup', e=>{ keys[e.key]=false; if(e.key.toUpperCase()==='H') hornOn(false); });

// ---------------- HUD ----------------
let lastInfo='', blinkClock=0;
function hud(dt){
  const s=Drive.state;
  $('spd').textContent = Math.round(s.kmh);
  let tip='';
  if(Game.kind==='free'){
    const p=Drive.pointer(); const ar=$('hArrow');
    if(p){ ar.classList.remove('hide'); $('hArrowIc').style.transform=`rotate(${p.a+Math.PI/2}rad)`; $('hArrowT').textContent = p.d<12 ? 'here!' : Math.round(p.d)+' m · +'+(s.job?s.job.reward:0); }
    $('hObj').textContent = 'Follow the arrow to a free bay, park, shift to P. Or just cruise.';
    const info = `<div class="pill stk"><i class="coin"></i>${s.coins}</div><div class="pill stk">${(s.odo/1000).toFixed(1)} km</div><div class="pill stk"><svg viewBox="0 0 24 24">${ICONS.p}</svg>${s.jobs}</div>`;
    if(info!==lastInfo){ $('hInfo').innerHTML=info; lastInfo=info; }
  } else {
    $('hArrow').classList.add('hide');
    const lv=LEVELS[Game.li];
    let obj = lv.hint;
    if(Game.hintT<=0){ obj = s.flags && s.nextFlag<s.flags ? `Drive through pad ${s.nextFlag+1} of ${s.flags}` : s.coinsNeed && s.coinsGot<s.coinsNeed ? `Coins ${s.coinsGot}/${s.coinsNeed} to open the bay` : 'Into the bay, nose toward the arrow, then P'; }
    $('hObj').textContent = obj;
    const info = `<div class="pill stk"><svg viewBox="0 0 24 24" style="color:var(--tom)">${ICONS.bump}</svg>${s.bumps+s.cones}</div><div class="pill stk">${fmtT(s.t)}</div>` + (s.flags?`<div class="pill stk">Pads ${s.nextFlag}/${s.flags}</div>`:'') + (s.coinsNeed?`<div class="pill stk"><i class="coin"></i>${s.coinsGot}/${s.coinsNeed}</div>`:'');
    if(info!==lastInfo){ $('hInfo').innerHTML=info; lastInfo=info; }
    if(Game.li===0 && s.t<40){ if(CTRL.gear==='P' && !s.parkedOk) tip = pedal.brake>0.2||keys.ArrowDown ? 'Now tap D' : 'Hold BRAKE, then tap D'; else if(CTRL.gear==='D' && Math.abs(s.v)<0.5 && s.odo<2) tip='Let go of the brake. Press GAS.'; }
  }
  if(s.parkedOk && CTRL.gear!=='P'){ tip = Math.abs(s.v)>0.3 ? 'In the bay. Brake to stop.' : 'Perfect. Shift to P.'; }
  if(Game.hintT>0) Game.hintT-=dt;
  const te=$('hTip'); if(tip){ te.textContent=tip; te.classList.remove('hide'); } else te.classList.add('hide');
  // indicator tick sound
  if(CTRL.blinkL||CTRL.blinkR){ blinkClock+=dt; if(blinkClock>0.385){ blinkClock=0; SFX.tick(); } }
}

// ---------------- UI ----------------
const UI = {
  page:'home',
  go(p){
    this.page=p; document.querySelectorAll('.page').forEach(e=>e.classList.toggle('off', e.id!==p));
    document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on', b.dataset.p===p || (p==='levels'&&b.dataset.p==='home')));
    $('np').style.display = p==='settings' ? 'none' : '';
    if(p==='garage') this.garage(); if(p==='missions') Missions.render(); if(p==='music') Music.render(); if(p==='settings') this.settings(); if(p==='levels') this.levels();
    placeYT(); SFX.ui();
  },
  topbar(){ $('coins').textContent=S.coins; $('streak').textContent=S.streak; },
  dots(){ $('misDot').classList.toggle('hide', !(S.missions.some(m=>m.done&&!m.claimed) || S.claimedDay!==dayKey())); const d=S.missions.filter(m=>m.done).length; $('chipMisN').textContent=d+'/3'; },
  totalStars(){ return Object.values(S.stars).reduce((a,b)=>a+b,0); },
  nextLevel(){ for(let i=0;i<LEVELS.length;i++) if(!S.stars[i]) return i; return LEVELS.length-1; },
  refresh(){
    this.topbar(); this.dots();
    const ts=this.totalStars(), done=Object.keys(S.stars).length;
    $('chipStars').textContent = ts+' / '+LEVELS.length*3;
    $('parkSub').textContent = done>=LEVELS.length ? 'All lots cleared · chase 3 stars' : `Next up: ${this.nextLevel()+1}. ${LEVELS[this.nextLevel()].name}`;
    $('parkProg').style.width = (ts/(LEVELS.length*3)*100)+'%';
    $('freeSub').textContent = S.km>0.05 ? `${S.km.toFixed(1)} km driven · ${S.jobsT} bays parked` : 'Cruise town, park for cash';
    drawPreviews();
  },
  levels(){
    const G=$('lvGrid'); G.innerHTML='';
    LEVELS.forEach((lv,i)=>{
      const st=S.stars[i]||0, open = i===0 || (S.stars[i-1]||0)>0, nxt = open && !st;
      const b=document.createElement('button'); b.className='lv stk press'+(open?'':' locked')+(nxt?' next':'');
      b.innerHTML = open ? `<b>${i+1}</b><span>${lv.name}</span><div class="st">${'★'.repeat(st)}<span style="color:var(--p2);-webkit-text-stroke:.6px #221d2b">${'★'.repeat(3-st)}</span></div>` : `<svg viewBox="0 0 24 24">${ICONS.lock}</svg><span>${lv.name}</span>`;
      b.onclick=()=>{ if(!open){ toast('Finish level '+i+' first'); return; } Game.start('park', i); };
      G.appendChild(b);
    });
  },
  garage(){
    const G=$('gGrid'); G.innerHTML='';
    CARS.forEach(it=>{
      const own=S.ownedCars.includes(it.id), d=document.createElement('div'); d.className='card stk'+(S.car===it.id?' sel':'');
      const c=document.createElement('canvas'); c.width=300; c.height=200; const k=c.getContext('2d'); k.scale(2,2); k.translate(75,52); k.rotate(-Math.PI/2+0.5); k.scale(17,17); drawCar(k,it,{t:1, steer:0.25});
      d.appendChild(c);
      d.insertAdjacentHTML('beforeend', `<div class="nm">${it.name}</div>${own?'':`<span class="lock"><svg viewBox="0 0 24 24">${ICONS.lock}</svg></span>`}`);
      const b=document.createElement('button'); b.className='btn sm'+(own?' gh':''); b.style.width='100%';
      b.innerHTML = S.car===it.id ? 'Driving' : own ? 'Drive this' : `<i class="coin" style="width:13px;height:13px;vertical-align:-2px"></i> ${it.price.toLocaleString()}`;
      if(!own && S.coins<it.price) b.disabled=true;
      b.onclick=()=>{ if(!own){ if(S.coins<it.price) return; addCoins(-it.price); S.ownedCars.push(it.id); SFX.bank(); vib(40); toast('New keys: '+it.name); }
        S.car=it.id; save(); this.garage(); this.topbar(); };
      d.appendChild(b); G.appendChild(d);
    });
  },
  settings(){
    $('vol').value=S.vol; $('sens').value=S.sens; $('tSfx').classList.toggle('on',S.sfx); $('tVib').classList.toggle('on',S.vib); $('tAuto').classList.toggle('on',S.auto); $('tCam').classList.toggle('on',S.camRot);
    document.querySelectorAll('#ctrlSeg button').forEach(b=>b.classList.toggle('on', b.dataset.c===S.ctrl));
    $('credits').innerHTML = '<b>Offline music (CC BY 4.0)</b><br>' + TRACKS.map(t=>`“${t.orig}” by BudgetPixel AI, ${t.url}${t.remix?' (remixed with piano as “Piano Fire”)':''}`).join('<br>') + '<br>creativecommons.org/licenses/by/4.0<br><br>Online songs stream from YouTube through the official YouTube player.<br>Fonts: Lilita One, Nunito (SIL OFL).';
  }
};
function drawPreviews(){
  const cd=CARS.find(x=>x.id===S.car)||CARS[0];
  for(const [id,free] of [['pvPark',false],['pvFree',true]]){
    const c=$(id), w=c.clientWidth||70, h=c.clientHeight||70; c.width=w*DPR; c.height=h*DPR; const g=c.getContext('2d'); g.setTransform(DPR,0,0,DPR,0,0);
    g.save(); g.translate(w/2,h/2); g.scale(w/9,w/9);
    if(!free){ g.strokeStyle='rgba(245,240,228,.9)'; g.lineWidth=0.12; for(const x of [-1.5,1.5]){ g.beginPath(); g.moveTo(x,-3); g.lineTo(x,3); g.stroke(); } g.strokeStyle='#f2b134'; g.setLineDash([0.5,0.35]); g.lineWidth=0.15; g.strokeRect(-1.4,-2.9,2.8,5.6); g.setLineDash([]); g.rotate(-Math.PI/2); g.translate(-0.4,0); drawCar(g,cd,{t:0}); }
    else { g.fillStyle='#55545e'; g.fillRect(-1.8,-6,3.6,12); g.strokeStyle='#f2c14e'; g.lineWidth=0.15; g.setLineDash([0.8,0.8]); g.beginPath(); g.moveTo(0,-6); g.lineTo(0,6); g.stroke(); g.setLineDash([]); g.fillStyle='#3f7a3a'; g.strokeStyle='#221d2b'; g.lineWidth=0.1; for(const p of [[-3.2,-2.5],[3.3,1.5],[-3,3.2]]){ g.beginPath(); g.arc(p[0],p[1],1,0,TAU); g.fill(); g.stroke(); } g.rotate(-Math.PI/2+0.15); g.scale(0.85,0.85); drawCar(g,cd,{t:0,steer:0.2}); }
    g.restore();
  }
}

// ---------------- LOOP ----------------
let last = performance.now();
function frame(now){
  const dt = Math.min(0.033, (now-last)/1000); last = now;
  try{
    audioTick(dt);
    if(Game.active){
      const dashH = $('dash').offsetHeight || 230;
      if(!Game.paused && !Game.ended){ Controls.tick(dt); Drive.step(dt); hud(dt); }
      else if(Game.ended) Drive.step(dt);
      Drive.render(cx, W, H, 0, H-dashH);
    } else {
      Drive.step(dt); Drive.render(cx, W, H, 0, H);
      cx.fillStyle='rgba(244,236,220,.18)'; cx.fillRect(0,0,W,H);
    }
  }catch(err){ console.error(err); }
  requestAnimationFrame(frame);
}

// ---------------- WIRING ----------------
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>UI.go(b.dataset.p));
$('setB').onclick=()=>UI.go(UI.page==='settings'?'home':'settings');
$('mPark').onclick=()=>UI.go('levels');
$('mFree').onclick=()=>Game.start('free');
$('lvBack').onclick=()=>UI.go('home');
$('chipMis').onclick=()=>UI.go('missions');
$('hPause').onclick=e=>{ e.stopPropagation(); Game.pause(); };
$('resumeB').onclick=()=>Game.resume(); $('quitB').onclick=()=>Game.quit(Game.kind==='park'); $('restartB').onclick=()=>{ const l=Game.li; Game.quit(); Game.start('park', l); };
$('endB').onclick=()=>Game.endDrive();
$('nextB').onclick=()=>{ const k=Game.kind, l=Game.li; Game.quit(); if(k==='free') Game.start('free'); else Game.start('park', Math.min(LEVELS.length-1, l+1)); };
$('againB').onclick=()=>{ const k=Game.kind, l=Game.li; Game.quit(); Game.start(k, l); };
$('lvB').onclick=()=>Game.quit(true);
$('shareB').onclick=()=>{ const s = Game.kind==='free' ? `Just cruised ${(Drive.state.odo/1000).toFixed(1)} km in Bhai Drive 🚗` : `Parked level ${Game.li+1} in Bhai Drive with ${'⭐'.repeat(S.stars[Game.li]||1)} Can you do it cleaner?`; AND.share(s+' https://www.youtube.com/@bouncebhaiofficial'); };
document.querySelectorAll('#mSeg button').forEach(b=>b.onclick=()=>{ Music.tab=b.dataset.m; document.querySelectorAll('#mSeg button').forEach(x=>x.classList.toggle('on',x===b)); Music.render(); if(Music.tab==='search') setTimeout(()=>$('sIn').focus(),50); });
$('sGo').onclick=()=>{ Music.search($('sIn').value); $('sIn').blur(); };
$('sIn').addEventListener('keydown', e=>{ if(e.key==='Enter'){ Music.search($('sIn').value); $('sIn').blur(); } });
$('songs').addEventListener('click', e=>{
  const lk = e.target.closest('[data-like]'); const list = Music.list(Music.tab);
  if(lk){ e.stopPropagation(); Music.like(list[+lk.dataset.like]); return; }
  const row = e.target.closest('.song'); if(row){ initAudio(); Music.playList(list, +row.dataset.i); }
});
$('npPlay').onclick=()=>{ initAudio(); if(!Music.cur){ autoMusic(); return; } Music.toggle(); };
$('npNext').onclick=()=>{ initAudio(); Music.cur ? Music.next() : autoMusic(); };
$('npPrev').onclick=()=>{ initAudio(); Music.cur ? Music.prev() : autoMusic(); };
$('np').querySelector('.t').onclick=()=>UI.go('music');
$('vol').oninput=e=>Music.setVol(+e.target.value);
$('sens').oninput=e=>{ S.sens=+e.target.value; save(); };
document.querySelectorAll('#ctrlSeg button').forEach(b=>b.onclick=()=>{ S.ctrl=b.dataset.c; save(); UI.settings(); SFX.ui(); if(S.ctrl==='tilt' && !tiltSeen) toast('Tilt works once you start driving'); });
$('tCam').onclick=()=>{ S.camRot=!S.camRot; save(); UI.settings(); };
$('tSfx').onclick=()=>{ S.sfx=!S.sfx; if(sfxGain) sfxGain.gain.value=S.sfx?0.5:0; save(); UI.settings(); };
$('tVib').onclick=()=>{ S.vib=!S.vib; save(); UI.settings(); vib(30); };
$('tAuto').onclick=()=>{ S.auto=!S.auto; save(); UI.settings(); };
$('ytB').onclick=()=>AND.open('https://www.youtube.com/@bouncebhaiofficial');
window.onAppPause=()=>{ Game.pause(); hornOn(false); if(AC) AC.suspend(); };
window.onAppResume=()=>{ if(AC) AC.resume(); };
document.addEventListener('visibilitychange', ()=>{ if(document.hidden) window.onAppPause(); else window.onAppResume(); });
window.onBack=()=>{
  if(Game.active){ if(Game.ended||Game.paused){ Game.quit(Game.kind==='park'); } else Game.pause(); return 'stay'; }
  if(UI.page!=='home'){ UI.go('home'); return 'stay'; }
  return 'exit';
};
document.addEventListener('pointerup', ()=>{ initAudio(); if(S.auto && !Music.playing && !Music._started){ Music._started=true; setTimeout(autoMusic, 350); } }, {once:true});

// ---------------- BOOT ----------------
Missions.ensure();
Drive.load(TOWN, true);
Music.init(); Music.ui();
UI.refresh(); UI.go('home');
requestAnimationFrame(frame);
if(S.claimedDay!==dayKey()) setTimeout(()=>toast('Daily reward waiting in Missions'), 1200);
