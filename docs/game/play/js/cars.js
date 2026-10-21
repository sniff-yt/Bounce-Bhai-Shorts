"use strict";
/* Cars: garage list + top-down car drawing (car faces +x, units = metres) */
const CARS = [
  {id:'bhai',    name:'Bhai Hatch',   price:0,    body:'#f2b134', roof:'#e09a1a', stripe:'#221d2b', face:true},
  {id:'mint',    name:'Mint Coupe',   price:120,  body:'#7fd1b9', roof:'#5cb89e', stripe:'#f4ecdc'},
  {id:'tomato',  name:'Tomato GT',    price:250,  body:'#e8553e', roof:'#c9412c', stripe:'#f4ecdc'},
  {id:'sky',     name:'Sky Wagon',    price:400,  body:'#8ecae6', roof:'#6aaed0', stripe:'#221d2b', long:true},
  {id:'taxi',    name:'Old Taxi',     price:600,  body:'#ffd23f', roof:'#221d2b', stripe:'#221d2b', checker:true},
  {id:'police',  name:'Patrol',       price:900,  body:'#f4f1ea', roof:'#2b3a67', stripe:'#2b3a67', police:true},
  {id:'forest',  name:'Forest 4x4',   price:1300, body:'#4f7a4a', roof:'#3d6139', stripe:'#d8c99b', jeep:true},
  {id:'plum',    name:'Plum Classic', price:1800, body:'#7b4b8a', roof:'#5f3a6c', stripe:'#f2b134'},
];
const INK = '#221d2b';
const CAR_L = 4.4, CAR_W = 1.9;
function rr(c,x,y,w,h,r){ c.beginPath(); c.moveTo(x+r,y); c.arcTo(x+w,y,x+w,y+h,r); c.arcTo(x+w,y+h,x,y+h,r); c.arcTo(x,y+h,x,y,r); c.arcTo(x,y,x+w,y,r); c.closePath(); }
// o: {steer, brake, reverse, blinkL, blinkR, t, shadow, lights}
function drawCar(c, car, o={}){
  const L = car.long ? 4.7 : CAR_L, Wd = car.jeep ? 2.0 : CAR_W, hl=L/2, hw=Wd/2, lw = 0.07;
  c.save();
  if(o.shadow!==false){ c.fillStyle='rgba(20,15,30,.28)'; rr(c,-hl+0.25,-hw+0.3,L,Wd,0.45); c.fill(); }
  // wheels (front wheels turn)
  c.fillStyle=INK;
  const wl=0.78, ww=0.32, fx=hl-1.0, rx=-hl+1.0;
  for(const sy of [-1,1]){
    c.save(); c.translate(rx, sy*(hw-0.08)); rr(c,-wl/2,-ww/2,wl,ww,0.1); c.fill(); c.restore();
    c.save(); c.translate(fx, sy*(hw-0.08)); c.rotate(o.steer||0); rr(c,-wl/2,-ww/2,wl,ww,0.1); c.fill(); c.restore();
  }
  // body
  c.fillStyle=car.body; c.strokeStyle=INK; c.lineWidth=lw*1.6; c.lineJoin='round';
  c.beginPath();
  c.moveTo(-hl+0.35,-hw); c.lineTo(hl-0.6,-hw); c.quadraticCurveTo(hl,-hw+0.05,hl,-hw+0.55); c.lineTo(hl,hw-0.55); c.quadraticCurveTo(hl,hw-0.05,hl-0.6,hw);
  c.lineTo(-hl+0.35,hw); c.quadraticCurveTo(-hl,hw,-hl,hw-0.35); c.lineTo(-hl,-hw+0.35); c.quadraticCurveTo(-hl,-hw,-hl+0.35,-hw); c.closePath();
  c.fill(); c.stroke();
  // bonnet crease + stripe
  c.strokeStyle='rgba(34,29,43,.25)'; c.lineWidth=lw; c.beginPath(); c.moveTo(hl-0.35,-hw+0.4); c.lineTo(hl-1.1,-hw+0.45); c.moveTo(hl-0.35,hw-0.4); c.lineTo(hl-1.1,hw-0.45); c.stroke();
  if(car.checker){ for(let i=0;i<6;i++){ c.fillStyle=i%2?INK:'#f4ecdc'; c.fillRect(-0.9+i*0.3,-0.12,0.3,0.24); } }
  else if(!car.police){ c.fillStyle=car.stripe; c.fillRect(hl-1.25, -0.11, 1.0, 0.22); }
  // cabin: windshield, roof, rear window
  const cf = car.jeep ? 0.5 : 0.75, cr = car.long ? -1.75 : -1.25;
  c.fillStyle='#34405a'; c.strokeStyle=INK; c.lineWidth=lw;
  c.beginPath(); c.moveTo(cf, -hw+0.2); c.quadraticCurveTo(cf+0.45, 0, cf, hw-0.2); c.lineTo(cf-0.55, hw-0.28); c.lineTo(cf-0.55, -hw+0.28); c.closePath(); c.fill(); c.stroke();
  c.fillStyle='#9fc3d6'; c.globalAlpha=0.55; c.beginPath(); c.moveTo(cf-0.08,-hw+0.35); c.lineTo(cf+0.12,-hw+0.38); c.lineTo(cf-0.2,-0.1); c.lineTo(cf-0.38,-0.1); c.closePath(); c.fill(); c.globalAlpha=1;
  c.fillStyle=car.roof; rr(c, cr+0.35, -hw+0.25, cf-0.55-(cr+0.35), Wd-0.5, 0.18); c.fill(); c.stroke();
  c.fillStyle='#34405a'; c.beginPath(); c.moveTo(cr+0.35,-hw+0.28); c.lineTo(cr,-hw+0.33); c.quadraticCurveTo(cr-0.18,0,cr,hw-0.33); c.lineTo(cr+0.35,hw-0.28); c.closePath(); c.fill(); c.stroke();
  if(car.jeep){ c.fillStyle=INK; c.globalAlpha=0.35; for(let i=0;i<4;i++) c.fillRect(cr+0.5+i*0.4, -hw+0.35, 0.06, Wd-0.7); c.globalAlpha=1; }
  // mirrors
  c.fillStyle=car.body; c.strokeStyle=INK; for(const sy of [-1,1]){ rr(c, cf-0.65, sy*(hw+0.12)-0.09, 0.28, 0.18, 0.05); c.fill(); c.stroke(); }
  if(car.face){ // Bounce Bhai roof sticker
    const sx=(cr+cf)/2-0.25; c.fillStyle='#f4ecdc'; c.beginPath(); c.arc(sx,0,0.42,0,TAU); c.fill(); c.stroke();
    c.fillStyle=INK; c.beginPath(); c.arc(sx+0.13,-0.14,0.06,0,TAU); c.arc(sx+0.13,0.14,0.06,0,TAU); c.fill();
    c.lineWidth=0.05; c.beginPath(); c.arc(sx-0.02,0,0.22,-1.1,1.1); c.stroke();
  }
  if(car.police){ const on = Math.floor((o.t||0)*6)%2; c.fillStyle=on?'#e8553e':'#5b8def'; rr(c,(cr+cf)/2-0.45,-0.55,0.3,0.5,0.06); c.fill(); c.fillStyle=on?'#5b8def':'#e8553e'; rr(c,(cr+cf)/2-0.45,0.05,0.3,0.5,0.06); c.fill(); }
  // lights
  c.fillStyle='#fff6d6'; c.strokeStyle=INK; c.lineWidth=lw*0.8;
  for(const sy of [-1,1]){ rr(c, hl-0.22, sy*(hw-0.42)-0.17, 0.2, 0.34, 0.06); c.fill(); c.stroke(); }
  const tail = o.brake ? '#ff3b2f' : '#a3262a';
  for(const sy of [-1,1]){ c.fillStyle = tail; rr(c, -hl+0.02, sy*(hw-0.4)-0.17, 0.16, 0.34, 0.05); c.fill(); c.stroke(); }
  if(o.reverse){ c.fillStyle='#ffffff'; for(const sy of [-1,1]) c.fillRect(-hl+0.03, sy*(hw-0.75)-0.07, 0.12, 0.14); }
  const blink = Math.floor((o.t||0)*2.6)%2===0;
  if(blink){ c.fillStyle='#ffa31a'; if(o.blinkL){ c.beginPath(); c.arc(hl-0.12,-hw+0.12,0.13,0,TAU); c.arc(-hl+0.12,-hw+0.12,0.13,0,TAU); c.fill(); } if(o.blinkR){ c.beginPath(); c.arc(hl-0.12,hw-0.12,0.13,0,TAU); c.arc(-hl+0.12,hw-0.12,0.13,0,TAU); c.fill(); } }
  if(o.lights){ c.globalCompositeOperation='lighter'; const g=c.createLinearGradient(hl,0,hl+9,0); g.addColorStop(0,'rgba(255,240,190,.32)'); g.addColorStop(1,'rgba(255,240,190,0)'); c.fillStyle=g; c.beginPath(); c.moveTo(hl,-0.7); c.lineTo(hl+9,-3); c.lineTo(hl+9,3); c.lineTo(hl,0.7); c.fill(); c.globalCompositeOperation='source-over'; }
  c.restore();
}
