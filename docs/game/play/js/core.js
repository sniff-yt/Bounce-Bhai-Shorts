"use strict";
/* =========================================================
   Bounce Bhai: Bhai Drive — core, audio, music manager
   ========================================================= */
const AND = window.Android || {vibrate(){}, share(t){ if(navigator.share) navigator.share({text:t}).catch(()=>{}); }, open(u){ window.open(u); }, yt:null};
const $ = id => document.getElementById(id);
const TAU = Math.PI*2, rnd = (a,b)=>a+Math.random()*(b-a), clamp=(v,a,b)=>Math.max(a,Math.min(b,v)), lerp=(a,b,t)=>a+(b-a)*t;
const dayKey = (o=0) => { const d = new Date(); d.setDate(d.getDate()+o); return d.getFullYear()+'-'+(d.getMonth()+1)+'-'+d.getDate(); };
const cv = $('c'), cx = cv.getContext('2d');
let W=0, H=0, DPR=1;
function resize(){ DPR = Math.min(window.devicePixelRatio||1, 2); W = innerWidth; H = innerHeight; cv.width = W*DPR|0; cv.height = H*DPR|0; cx.setTransform(DPR,0,0,DPR,0,0); }
addEventListener('resize', resize); resize();

// ---------------- SAVE ----------------
const DEF = {coins:0, xp:0, bestDrift:0, bestRing:0, car:'bhai', ownedCars:['bhai'], ball:'classic', ownedBalls:['classic'],
  streak:0, claimedDay:'', missions:null, misDay:'', runs:0, vol:80, sfx:true, vib:true, auto:true, mode:'drift',
  liked:[], hits:null, hitsAt:0, newest:null, newAt:0, lastSong:null, totalDrift:0, totalRings:0,
  stars:{}, ctrl:'wheel', sens:100, camRot:true, km:0, jobsT:0, bestJobs:0, tutDone:false};
let S; try{ S = Object.assign({}, DEF, JSON.parse(localStorage.getItem('bbpd')||'{}')); }catch(e){ S = Object.assign({}, DEF); }
if(!CARS_OK()) { S.car='bhai'; S.ownedCars=['bhai']; }
function CARS_OK(){ return ['bhai','mint','tomato','sky','taxi','police','forest','plum'].includes(S.car); }
let saveT = 0; function save(){ clearTimeout(saveT); saveT = setTimeout(()=>{ try{ localStorage.setItem('bbpd', JSON.stringify(S)); }catch(e){} }, 120); }
function vib(ms){ if(S.vib) try{ AND.vibrate(ms|0); }catch(e){} }
function toast(t){ const e=$('toast'); e.textContent=t; e.classList.add('on'); clearTimeout(e._t); e._t=setTimeout(()=>e.classList.remove('on'),1900); }
function banner(t, sub, col){ const b=$('banner'); b.innerHTML = (sub?`<small>${sub}</small>`:'') + t; b.style.color = col||'#f2b134'; b.classList.add('on'); clearTimeout(b._t); b._t=setTimeout(()=>b.classList.remove('on'),1100); }
function addCoins(n){ S.coins = Math.max(0, S.coins + n); save(); $('coins').textContent = S.coins; }
const level = () => 1 + Math.floor(Math.sqrt(S.xp/120));

// ---------------- AUDIO (local) ----------------
const TRACKS = [
  {f:'music/t0.mp3', name:'Piano Fire', by:'Bounce Bhai x BudgetPixel', bpm:137.2, off:0.07, orig:'Eerie Night Phonk Bells', url:'https://budgetpixel.com/background-music/eerie-night-phonk-bells-f5ef1acb', remix:true},
  {f:'music/t1.mp3', name:'Funky Brazilian Phonk', by:'BudgetPixel', bpm:152, off:0.07, orig:'Funky Brazilian Phonk', url:'https://budgetpixel.com/background-music/funky-brazilian-phonk-54fb718d'},
  {f:'music/t2.mp3', name:'Copacabana Phonk Rush', by:'BudgetPixel', bpm:161.5, off:0.07, orig:'Copacabana Phonk Rush', url:'https://budgetpixel.com/background-music/copacabana-phonk-rush-a5476f0a'},
  {f:'music/t3.mp3', name:'Cowbell Phonk Rush', by:'BudgetPixel', bpm:136, off:0.07, orig:'Cowbell Phonk Rush', url:'https://budgetpixel.com/background-music/cowbell-phonk-rush-8cf90b90'},
  {f:'music/t4.mp3', name:'Gritty Street Phonk', by:'BudgetPixel', bpm:143.6, off:0.07, orig:'Gritty Street Phonk', url:'https://budgetpixel.com/background-music/gritty-street-phonk-ccc272ae'},
  {f:'music/t5.mp3', name:'Motivational Phonk Workout', by:'BudgetPixel', bpm:136, off:0.395, orig:'Motivational Phonk Workout', url:'https://budgetpixel.com/background-music/motivational-phonk-workout-2d2fcccf'},
];
let AC=null, comp, musicGain, filter, analyser, sfxGain, fdata, buffers={}, curSrc=null, localIdx=0, trackStart=0, localPlaying=false;
function initAudio(){
  if(AC){ if(AC.state==='suspended') AC.resume(); return; }
  try{ AC = new (window.AudioContext||window.webkitAudioContext)(); }catch(e){ return; }
  comp = AC.createDynamicsCompressor(); comp.threshold.value=-10; comp.ratio.value=4; comp.connect(AC.destination);
  filter = AC.createBiquadFilter(); filter.type='lowpass'; filter.frequency.value=20000; filter.Q.value=0.7;
  musicGain = AC.createGain(); musicGain.gain.value = S.vol/100;
  analyser = AC.createAnalyser(); analyser.fftSize=512; analyser.smoothingTimeConstant=0.5; fdata=new Uint8Array(analyser.frequencyBinCount);
  musicGain.connect(filter); filter.connect(analyser); analyser.connect(comp);
  sfxGain = AC.createGain(); sfxGain.gain.value = S.sfx?0.5:0; sfxGain.connect(comp);
}
function loadBuf(i){
  return new Promise((res, rej) => {
    if(buffers[i]) return res(buffers[i]);
    fetch(TRACKS[i].f).then(r=>r.arrayBuffer()).then(ab => AC.decodeAudioData(ab, b => { buffers[i]=b; res(b); }, rej)).catch(rej);
  });
}
function playLocal(i){
  initAudio(); if(!AC) return;
  localIdx = (i+TRACKS.length)%TRACKS.length; localPlaying = true;
  Music.onLocal(localIdx);
  loadBuf(localIdx).then(b => {
    if(!localPlaying || Music.src!=='local' || Music.localIdx!==localIdx) return;
    stopLocal(true);
    const t = AC.currentTime, g = AC.createGain(); g.gain.setValueAtTime(0.0001,t); g.gain.exponentialRampToValueAtTime(1,t+0.5); g.connect(musicGain);
    const s = AC.createBufferSource(); s.buffer=b; s.connect(g); s.start(t); s._g=g; curSrc=s; trackStart=t;
    s.onended = () => { if(curSrc===s && localPlaying) Music.next(); };
    loadBuf((localIdx+1)%TRACKS.length).catch(()=>{});
  }).catch(()=>{});
}
function stopLocal(keepFlag){
  if(curSrc){ const s=curSrc; curSrc=null; s.onended=null; try{ const t=AC.currentTime; s._g.gain.setValueAtTime(s._g.gain.value,t); s._g.gain.exponentialRampToValueAtTime(0.0001,t+0.35); s.stop(t+0.4); }catch(e){} }
  if(!keepFlag) localPlaying=false;
}
function setFilter(freq, time){ if(!AC) return; const t=AC.currentTime; filter.frequency.cancelScheduledValues(t); filter.frequency.setValueAtTime(Math.max(60,filter.frequency.value),t); filter.frequency.exponentialRampToValueAtTime(freq,t+(time||0.3)); }

// beat detection: analyser for local tracks, tempo clock for YouTube
let beatPulse=0, bassAvg=0, lastBeatIdx=-1, ytBeatT=0;
const onBeatFns = [];
function audioTick(dt){
  let hit=false;
  if(Music.src==='local' && localPlaying && AC){
    analyser.getByteFrequencyData(fdata); let b=0; for(let i=1;i<7;i++) b+=fdata[i]; b/=6*255;
    bassAvg += (b-bassAvg)*Math.min(1,dt*3);
    if(b>bassAvg*1.16 && b>0.42 && beatPulse<0.45) hit=true;
    const tr=TRACKS[localIdx], idx=Math.floor((AC.currentTime-trackStart-tr.off)/(60/tr.bpm));
    if(idx!==lastBeatIdx){ lastBeatIdx=idx; if(beatPulse<0.3 && Math.random()<0.5) hit=true; }
  } else if(Music.src==='yt' && Music.playing){
    ytBeatT += dt; if(ytBeatT >= 60/130){ ytBeatT -= 60/130; hit=true; }
  }
  if(hit){ beatPulse=1; onBeatFns.forEach(f=>f()); }
  beatPulse *= Math.pow(0.002, dt);
  document.documentElement.style.setProperty('--beat', beatPulse.toFixed(3));
}

// ---------------- SFX ----------------
function tone(f,dur,type,vol,slide,delay){ if(!AC||!S.sfx) return; const t=AC.currentTime+(delay||0); const o=AC.createOscillator(), g=AC.createGain(); o.type=type||'sine'; o.frequency.setValueAtTime(f,t); if(slide) o.frequency.exponentialRampToValueAtTime(f*slide,t+dur); g.gain.setValueAtTime(0.0001,t); g.gain.exponentialRampToValueAtTime(vol||0.2,t+0.008); g.gain.exponentialRampToValueAtTime(0.0001,t+dur); o.connect(g); g.connect(sfxGain); o.start(t); o.stop(t+dur+0.02); }
let noiseBuf=null;
function noise(dur,vol,type,freq,delay){ if(!AC||!S.sfx) return; if(!noiseBuf){ const n=AC.sampleRate*2; noiseBuf=AC.createBuffer(1,n,AC.sampleRate); const d=noiseBuf.getChannelData(0); for(let i=0;i<n;i++) d[i]=Math.random()*2-1; }
  const t=AC.currentTime+(delay||0), s=AC.createBufferSource(); s.buffer=noiseBuf; const f=AC.createBiquadFilter(); f.type=type||'highpass'; f.frequency.value=freq||1000; const g=AC.createGain(); g.gain.setValueAtTime(vol||0.2,t); g.gain.exponentialRampToValueAtTime(0.0001,t+dur); s.connect(f); f.connect(g); g.connect(sfxGain); s.start(t, Math.random()); s.stop(t+dur+0.05); }
// continuous tyre squeal + engine
let squeal=null, engine=null, horn=null;
function hornOn(on){ if(!AC||!S.sfx) return; if(on&&!horn){ const g=AC.createGain(); g.gain.value=0.07; g.connect(sfxGain); const lp=AC.createBiquadFilter(); lp.type='lowpass'; lp.frequency.value=1800; lp.connect(g); const os=[392,494].map(f=>{ const o=AC.createOscillator(); o.type='square'; o.frequency.value=f; o.connect(lp); o.start(); return o; }); horn={g,os}; } else if(!on&&horn){ const h=horn; horn=null; h.g.gain.setTargetAtTime(0,AC.currentTime,0.02); setTimeout(()=>h.os.forEach(o=>{ try{o.stop();}catch(e){} }),200); } }
function ensureLoops(){
  if(!AC||squeal) return;
  if(!noiseBuf) noise(0.01,0.0001);
  const s=AC.createBufferSource(); s.buffer=noiseBuf; s.loop=true; const f=AC.createBiquadFilter(); f.type='bandpass'; f.frequency.value=2400; f.Q.value=6; const g=AC.createGain(); g.gain.value=0; s.connect(f); f.connect(g); g.connect(sfxGain); s.start(); squeal={g,f};
  const o=AC.createOscillator(); o.type='sawtooth'; o.frequency.value=60; const lp=AC.createBiquadFilter(); lp.type='lowpass'; lp.frequency.value=400; const eg=AC.createGain(); eg.gain.value=0; o.connect(lp); lp.connect(eg); eg.connect(sfxGain); o.start(); engine={o,g:eg,lp};
}
function setLoops(sq, rpm, on){
  if(!squeal) return; const t=AC.currentTime;
  squeal.g.gain.setTargetAtTime(on? sq*0.09 : 0, t, 0.05); squeal.f.frequency.setTargetAtTime(1800+sq*1400, t, 0.1);
  engine.g.gain.setTargetAtTime(on? 0.05 : 0, t, 0.1); engine.o.frequency.setTargetAtTime(45+rpm*90, t, 0.08); engine.lp.frequency.setTargetAtTime(300+rpm*700, t, 0.1);
}
const SFX = {
  coin(){ tone(1046,0.07,'square',0.05); tone(1568,0.14,'square',0.05,1,0.06); },
  bank(n){ [0,4,7,12].forEach((s,i)=>tone(523*Math.pow(2,s/12),0.18,'triangle',0.09,1,i*0.05)); noise(0.2,0.12,'highpass',3000); },
  crash(){ noise(0.9,0.5,'lowpass',900); tone(90,0.8,'sawtooth',0.3,0.3); noise(0.4,0.3,'highpass',2500,0.05); },
  nitro(){ noise(1.2,0.35,'bandpass',600); tone(80,1,'sawtooth',0.18,3.5); },
  close(){ tone(1400,0.08,'sine',0.08); tone(1800,0.1,'sine',0.08,1,0.06); },
  sector(){ [0,7,12,19].forEach((s,i)=>tone(392*Math.pow(2,s/12),0.3,'sawtooth',0.05,1,i*0.07)); },
  ui(){ tone(880,0.05,'sine',0.06); },
  bounce(n){ tone(262*Math.pow(2,[0,3,5,7,10,12,15][n%7]/12),0.14,'triangle',0.1); },
  escape(c){ const b=392*Math.pow(2,Math.min(c,10)/12); [0,7,12].forEach((s,i)=>tone(b*Math.pow(2,s/12),0.22,'square',0.045,1,i*0.04)); noise(0.22,0.15,'highpass',2500); tone(90,0.22,'sine',0.3,0.5); },
  hurt(){ tone(140,0.4,'sawtooth',0.13,0.35); noise(0.3,0.2,'lowpass',400); },
  bump(k){ noise(0.18,0.25+k*0.35,'lowpass',500+k*600); tone(70+k*30,0.2,'sine',0.25+k*0.2,0.5); },
  cone(){ tone(320,0.09,'square',0.06,0.6); noise(0.08,0.1,'bandpass',1200); },
  ding(){ tone(1175,0.25,'sine',0.12); tone(1568,0.35,'sine',0.1,1,0.08); },
  park(){ [0,4,7,12,16].forEach((s,i)=>tone(523*Math.pow(2,s/12),0.3,'triangle',0.1,1,i*0.07)); },
  tick(){ tone(1800,0.02,'square',0.03); tone(1200,0.02,'square',0.025,1,0.09); },
  shift(){ noise(0.05,0.12,'bandpass',900); tone(180,0.05,'square',0.05,0.7); },
  pick(){ [0,4,7,12].forEach((s,i)=>tone(660*Math.pow(2,s/12),0.1,'sine',0.1,1,i*0.045)); },
};

/* =========================================================
   MUSIC MANAGER — YouTube sync + offline tracks
   ========================================================= */
const HITS_PLAYLIST = 'PLFPDSa9XlTPB1U4xnJH0KZtCCwZ6nj__5';
const ytCallbacks = {}; let ytCbN = 0;
window.ytcb = (id, data) => { const f = ytCallbacks[id]; delete ytCallbacks[id]; if(f) f(data); };
function ytFetch(kind, q){
  return new Promise(res => {
    if(!AND.yt){ return res(null); }
    const id = 'c'+(++ytCbN); ytCallbacks[id] = res;
    try{ AND.yt(kind, q, id); }catch(e){ delete ytCallbacks[id]; res(null); }
    setTimeout(()=>{ if(ytCallbacks[id]){ delete ytCallbacks[id]; res(null); } }, 25000);
  });
}
let ytPlayer=null, ytReady=false, ytApiLoading=false, ytPending=null;
function loadYTApi(){
  if(ytApiLoading) return; ytApiLoading=true;
  window.onYouTubeIframeAPIReady = () => {
    ytPlayer = new YT.Player('yt', {width:'100%', height:'100%', playerVars:{autoplay:1, controls:1, playsinline:1, rel:0, modestbranding:1, fs:0, origin: location.origin},
      events:{
        onReady(){ ytReady=true; ytPlayer.setVolume(S.vol); if(ytPending){ const p=ytPending; ytPending=null; ytPlayer.loadVideoById(p); } },
        onStateChange(e){ if(e.data===0) Music.next(); if(e.data===1){ Music.playing=true; Music.ui(); } if(e.data===2){ Music.playing=false; Music.ui(); } },
        onError(){ toast('Can\'t play that one here, skipping'); setTimeout(()=>Music.next(), 400); }
      }});
  };
  const s=document.createElement('script'); s.src='https://www.youtube.com/iframe_api'; s.onerror=()=>{ ytApiLoading=false; }; document.head.appendChild(s);
}
const Music = {
  src:'local', localIdx:0, queue:[], qi:0, playing:false, tab:'hits', loading:{}, cur:null,
  init(){
    if(S.hits && S.hits.length) this.queue = S.hits.slice();
    this.syncHits(); this.syncNew();
    if(AND.yt) loadYTApi();
  },
  syncHits(force){
    if(!AND.yt){ return; }
    this.loading.hits = true; this.render();
    ytFetch('playlist', HITS_PLAYLIST).then(list => {
      this.loading.hits = false;
      if(list && list.length){ S.hits = list; S.hitsAt = Date.now(); save(); }
      this.render();
    });
  },
  syncNew(){
    if(!AND.yt) return;
    this.loading.new = true; this.render();
    Promise.all([ytFetch('latest','brazilian phonk'), ytFetch('latest','new phonk song'), ytFetch('latest','funk phonk montagem')]).then(rs => {
      this.loading.new = false; const seen = new Set(), out=[];
      rs.forEach(r => (r||[]).forEach(v => { if(!seen.has(v.id)){ seen.add(v.id); out.push(v); } }));
      if(out.length){ S.newest = out.slice(0,40); S.newAt = Date.now(); save(); }
      this.render();
    });
  },
  search(q){
    q = (q||'').trim(); if(!q) return;
    this.loading.search = true; this.results = null; this.render();
    ytFetch('search', q).then(r => { this.loading.search=false; this.results = r || []; if(!r) toast('No connection'); this.render(); });
  },
  list(tab){
    if(tab==='hits') return S.hits||[];
    if(tab==='new') return S.newest||[];
    if(tab==='search') return this.results||[];
    if(tab==='liked') return S.liked;
    return TRACKS.map((t,i)=>({local:i, t:t.name, a:t.by}));
  },
  playList(list, i){
    const it = list[i]; if(!it) return;
    if(it.local!==undefined){ this.src='local'; this.queue=list; this.qi=i; this.localIdx=it.local; this.stopYT(); playLocal(it.local); this.playing=true; this.cur=it; this.ui(); return; }
    this.queue = list.slice(); this.qi = i; this.playYT(it);
  },
  playYT(it){
    this.src='yt'; stopLocal(); this.cur=it; this.playing=true; S.lastSong = it; save();
    if(!ytReady){ ytPending = it.id; loadYTApi(); } else { ytPlayer.loadVideoById(it.id); ytPlayer.setVolume(S.vol); }
    placeYT(); this.ui(); this.render();
  },
  stopYT(){ if(ytReady) try{ ytPlayer.pauseVideo(); }catch(e){} },
  onLocal(i){ this.localIdx=i; this.cur={local:i, t:TRACKS[i].name, a:TRACKS[i].by}; this.ui(); this.render(); },
  next(){
    if(this.src==='local' && (!this.queue.length || this.queue[0].local===undefined)){ playLocal(this.localIdx+1); return; }
    if(!this.queue.length) return; this.qi = (this.qi+1)%this.queue.length; this.playList(this.queue, this.qi);
  },
  prev(){
    if(this.src==='local' && (!this.queue.length || this.queue[0].local===undefined)){ playLocal(this.localIdx-1); return; }
    if(!this.queue.length) return; this.qi = (this.qi-1+this.queue.length)%this.queue.length; this.playList(this.queue, this.qi);
  },
  toggle(){
    if(this.src==='yt' && ytReady){ if(this.playing) ytPlayer.pauseVideo(); else ytPlayer.playVideo(); return; }
    if(localPlaying){ stopLocal(); this.playing=false; } else { playLocal(this.localIdx); this.playing=true; }
    this.ui();
  },
  setVol(v){ S.vol=v; save(); if(musicGain) musicGain.gain.value=v/100; if(ytReady) ytPlayer.setVolume(v); },
  like(it){
    const i = S.liked.findIndex(x=>x.id===it.id);
    if(i>=0) S.liked.splice(i,1); else { S.liked.unshift({id:it.id,t:it.t,a:it.a,d:it.d}); toast('Added to Liked'); vib(15); }
    save(); this.render();
  },
  ui(){
    const c = this.cur;
    $('npT').textContent = c ? c.t : 'Piano Fire';
    $('npA').innerHTML = '<span class="eq"><i></i><i></i><i></i></span>' + (c ? (c.local!==undefined ? 'Offline · '+c.a : (c.a||'YouTube')) : 'Offline track');
    const img = $('npImg'); const src = c && c.id ? `https://i.ytimg.com/vi/${c.id}/mqdefault.jpg` : 'icon.png'; if(img.getAttribute('src')!==src) img.src = src;
    $('npPlayIc').innerHTML = this.playing ? '<path d="M6 4h4v16H6zM14 4h4v16h-4z"/>' : '<path d="M6 4l14 8-14 8z"/>';
  },
  render(){
    const box = $('songs'); if(!box || UI.page!=='music') return;
    const tab = this.tab, list = this.list(tab);
    const sl = $('syncLine');
    if(this.loading[tab]) sl.innerHTML = '<span class="spin"></span>Syncing with YouTube…';
    else if(tab==='hits') sl.textContent = S.hitsAt ? `Top phonk hits · synced ${ago(S.hitsAt)}` : (AND.yt?'':'YouTube sync works in the app');
    else if(tab==='new') sl.textContent = S.newAt ? `Fresh uploads · synced ${ago(S.newAt)}` : '';
    else if(tab==='liked') sl.textContent = S.liked.length ? `${S.liked.length} saved` : '';
    else if(tab==='local') sl.textContent = 'Built in, works offline, beat-synced visuals';
    else sl.textContent = '';
    $('sBox').style.display = tab==='search' ? 'flex' : 'none'; $('sBox').classList.toggle('hide', tab!=='search');
    if(!list.length){
      box.innerHTML = `<div class="empty">${tab==='liked' ? 'Tap ♥ on any song to keep it here.' : tab==='search' ? (this.loading.search?'':'Search any song, artist or vibe.') : this.loading[tab] ? '' : 'No songs yet. Check your connection.'}</div>`; return;
    }
    const cur = this.cur;
    box.innerHTML = list.map((s,i) => {
      const on = cur && ((s.id && cur.id===s.id) || (s.local!==undefined && cur.local===s.local));
      const liked = s.id && S.liked.some(x=>x.id===s.id);
      const img = s.id ? `https://i.ytimg.com/vi/${s.id}/mqdefault.jpg` : 'icon.png';
      return `<div class="song${on?' on':''}" data-i="${i}"><img loading="lazy" src="${img}"><div class="t"><b>${esc(s.t)}</b><span>${on?'<span class="eq"><i></i><i></i><i></i></span>':''}${esc(s.a||'')}${s.d?' · '+fmt(s.d):''}</span></div>${s.id?`<button class="ib${liked?' liked':''}" data-like="${i}"><svg viewBox="0 0 24 24"><path d="M12 21s-7-4.4-9.3-9A5.5 5.5 0 0 1 12 6a5.5 5.5 0 0 1 9.3 6c-2.3 4.6-9.3 9-9.3 9z"/></svg></button>`:''}</div>`;
    }).join('');
  }
};
function esc(s){ return String(s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function fmt(s){ return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); }
function ago(t){ const m=Math.round((Date.now()-t)/60000); return m<1?'just now':m<60?m+' min ago':m<1440?Math.round(m/60)+' h ago':Math.round(m/1440)+' d ago'; }
function placeYT(){
  const w = $('ytwrap');
  let cls = 'gone';
  if(Music.src==='yt'){
    if(Game.active) cls='game';
    else if(UI.page==='music') cls='big';
    else cls='mini';
  }
  w.className = cls; w.style.cssText='';
  if(cls==='mini'){ if(UI.page==='settings'){ w.className='gone'; return; } const r=$('npImg').getBoundingClientRect(); w.style.cssText=`left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px`; }
}
addEventListener('resize', ()=>{ if(typeof UI!=='undefined') placeYT(); });
