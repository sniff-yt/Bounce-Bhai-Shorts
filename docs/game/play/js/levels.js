"use strict";
/* Hand-made parking puzzles. Units: metres. Angles in degrees: 0 = east, 90 = south, -90 = north, 180 = west.
   walls:[x,y,w,h,style]  style c=concrete p=planter b=building
   cars:[x,y,a,colour]  cones:[x,y]  coins:[x,y]  flags:[[x,y]...] (in order)  trees:[x,y,r]
   bay:{x,y,a,w,l,any}  start:[x,y,a] */
const PARK_COLORS = ['#e8553e','#8ecae6','#7fd1b9','#f4f1ea','#7b4b8a','#4f7a4a','#ffd23f','#5b6b8c','#d98c5f'];
function rowCars(x0,y,a,step,n,skip){ const o=[]; for(let i=0;i<n;i++){ if(skip&&skip.includes(i)) continue; o.push([x0+i*step,y,a+(i%3===1?180:0),(i*5+3)%PARK_COLORS.length]); } return o; }
function colCars(x,y0,a,step,n,skip){ const o=[]; for(let i=0;i<n;i++){ if(skip&&skip.includes(i)) continue; o.push([x,y0+i*step,a+(i%3===2?180:0),(i*7+1)%PARK_COLORS.length]); } return o; }
function coneLine(x0,y0,x1,y1,n){ const o=[]; for(let i=0;i<n;i++){ const t=n>1?i/(n-1):0; o.push([x0+(x1-x0)*t, y0+(y1-y0)*t]); } return o; }

const LEVELS = [
  { name:'First Gear', hint:'Press the gas, roll into the yellow bay, stop, and shift to P.',
    w:20, h:40, start:[10,33,-90], bay:{x:10,y:8,a:-90},
    cars:[[6.9,8,-90,0],[13.1,8,90,1]], trees:[[3,22,1.6],[17,26,1.4]] },
  { name:'Easy Left', hint:'Steer the wheel left as you reach the row.',
    w:30, h:34, start:[23,28,-90], bay:{x:5,y:10,a:180},
    cars:[[5,6.9,180,2],[5,13.1,0,3],[5,16.2,180,4]], cones:[[12,18],[13,18],[14,18]], trees:[[25,6,1.8]] },
  { name:'Back It Up', hint:'Shift to R and reverse straight in. Small wheel moves only.',
    w:20, h:38, start:[10,13,-90], bay:{x:10,y:31,a:-90},
    cars:[[6.9,31,-90,5],[13.1,31,-90,6],[3.8,31,90,1]], trees:[[16,6,1.5],[4,6,1.3]] },
  { name:'One Spot Left', hint:'The row is full except for one bay. Find it and nose in.',
    w:34, h:36, start:[6,29,0], bay:{x:19,y:5.5,a:-90},
    cars:rowCars(4,5.5,-90,3,10,[5]), walls:[[0,12,10,2,'p'],[24,12,10,2,'p']], trees:[[5,13,1.4],[29,13,1.4]] },
  { name:'Cone Alley', hint:'Weave through the gaps. Knocking cones costs stars, not the level.',
    w:24, h:52, start:[12,46,-90], bay:{x:12,y:6,a:-90},
    cones:[...coneLine(1.5,37,14,37,10), ...coneLine(10,27,22.5,27,10), ...coneLine(1.5,17,14,17,10)],
    cars:[[8.9,6,-90,7],[15.1,6,-90,8]] },
  { name:'Parallel Pro', hint:'Pull up beside the front car, full lock, then reverse in at an angle.',
    w:20, h:46, start:[8.5,39,-90], bay:{x:2.4,y:20,a:-90,w:2.6,l:6.8},
    cars:[[2.3,13.2,-90,1],[2.3,26.8,-90,4],[2.3,33.5,-90,2],[2.3,6.5,-90,6]], walls:[[17,0,3,46,'p']], trees:[[18.5,10,1.3],[18.5,24,1.3],[18.5,38,1.3]] },
  { name:'Three-Point Turn', hint:'The street is narrow. Forward, reverse, forward. Park facing back west.',
    w:46, h:11, start:[6,6,0], bay:{x:38,y:2.3,a:180,w:2.6,l:6.6},
    cars:[[31.2,2.3,180,3],[14,8.7,0,5],[20,8.7,0,7]], trees:[] },
  { name:'Coin Loop', hint:'Grab every coin to open the bay.',
    w:36, h:36, start:[6,29,-90], bay:{x:30,y:6,a:-90}, needCoins:true,
    walls:[[12,12,12,12,'p']], coins:[[6,18],[6,8],[18,6],[30,18],[30,30],[18,30],[10,30],[22,6]],
    cars:[[26.9,6,-90,2],[33.1,6,90,4]], trees:[[18,18,2.6]] },
  { name:'Checkpoints', hint:'Drive through the numbered pads in order, then park.',
    w:40, h:40, start:[20,35,-90], bay:{x:20,y:20,a:0},
    flags:[[6,34],[6,6],[34,6],[34,34]], walls:[[8,10,8,8,'p'],[24,10,8,8,'p'],[8,24,8,8,'p'],[24,24,8,8,'p']],
    cars:[[20,16.9,0,1],[20,23.1,180,6]], trees:[[12,14,1.8],[28,14,1.8],[12,28,1.8],[28,28,1.8]] },
  { name:'The Garage', hint:'Reverse into the garage so the car faces out.',
    w:24, h:34, start:[12,26,-90], bay:{x:12,y:3.4,a:90,w:2.7,l:5.6},
    walls:[[9.7,0,0.6,7,'c'],[13.7,0,0.6,7,'c'],[0,0,9.7,3,'b'],[14.3,0,9.7,3,'b']], cones:[[8,10],[16,10]], trees:[[3,20,1.6],[21,18,1.5]] },
  { name:'Busy Lot', hint:'Two packed rows and one free bay. Take it slow.',
    w:40, h:46, start:[5,41,-90], bay:{x:25,y:24.5,a:90},
    cars:[...rowCars(10,5.5,-90,3,10), ...rowCars(10,18.5,90,3,10), ...rowCars(10,24.5,-90,3,10,[5]), ...rowCars(16,37.5,90,3,8)],
    walls:[[8.6,21.4,29.8,0.5,'c']], trees:[[4,6,1.5]] },
  { name:'Final Exam', hint:'Pads in order, then a parallel park by the kerb. You have got this.',
    w:30, h:62, start:[15,56,-90], bay:{x:2.4,y:12,a:-90,w:2.6,l:6.8},
    flags:[[24,44],[6,32],[24,22]], cones:[...coneLine(10,40,20,40,6), ...coneLine(10,28,20,28,6)],
    cars:[[2.3,5.2,-90,0],[2.3,18.8,-90,3],[2.3,25.5,-90,5]], walls:[[26,0,4,62,'p']], trees:[[28,10,1.4],[28,30,1.4],[28,50,1.4]] },
];

/* ---------- Free Drive town ---------- */
function makeTown(seed){
  let s = seed||7; const R = () => (s = (s*16807)%2147483647)/2147483647;
  const B=6, CELL=64, ROAD=12, N=B*CELL+ROAD;
  const walls=[], cars=[], trees=[], lots=[], marks=[], paves=[];
  const roofs=['#d9734e','#4a9d9c','#e8dcc0','#6b7a8f','#c9a227','#b5838d','#8d6e63'];
  for(let bi=0;bi<B;bi++) for(let bj=0;bj<B;bj++){
    const x0=bi*CELL+ROAD, y0=bj*CELL+ROAD, S=CELL-ROAD; // block 52x52
    const r=R();
    paves.push([x0,y0,S,S]);
    if(r<0.22){ // park with trees
      for(let k=0;k<9;k++) trees.push([x0+6+R()*(S-12), y0+6+R()*(S-12), 1.4+R()*1.4]);
      walls.push([x0+S/2-3,y0+S/2-3,6,6,'f']);
    } else if(r<0.42){ // parking lot: open on the road side (south)
      const lot={x:x0+3,y:y0+3,w:S-6,h:S-3,bays:[]};
      walls.push([x0,y0,S,3,'b',roofs[(bi+bj)%roofs.length]]);
      for(let k=0;k<15;k++){ const bx=x0+5+k*3+1.5, by=y0+6.2; lot.bays.push({x:bx,y:by,a:-90}); marks.push([bx,by,-90]); if(R()<0.55) cars.push([bx,by,R()<0.5?-90:90,Math.floor(R()*PARK_COLORS.length)]); }
      for(let k=0;k<15;k++){ const bx=x0+5+k*3+1.5, by=y0+S-14; lot.bays.push({x:bx,y:by,a:90}); marks.push([bx,by,90]); if(R()<0.4) cars.push([bx,by,R()<0.5?90:-90,Math.floor(R()*PARK_COLORS.length)]); }
      lot.bays = lot.bays.filter(b=>!cars.some(c=>Math.abs(c[0]-b.x)<0.5&&Math.abs(c[1]-b.y)<0.5));
      lots.push(lot);
    } else { // buildings
      const n = 1+Math.floor(R()*3);
      if(n===1) walls.push([x0+4,y0+4,S-8,S-8,'b',roofs[Math.floor(R()*roofs.length)]]);
      else if(n===2){ const sp=10+R()*(S-28); walls.push([x0+4,y0+4,sp,S-8,'b',roofs[Math.floor(R()*roofs.length)]]); walls.push([x0+8+sp,y0+4,S-12-sp,S-8,'b',roofs[Math.floor(R()*roofs.length)]]); }
      else { const h2=(S-12)/2; walls.push([x0+4,y0+4,S-8,h2,'b',roofs[Math.floor(R()*roofs.length)]]); walls.push([x0+4,y0+8+h2,h2,h2,'b',roofs[Math.floor(R()*roofs.length)]]); walls.push([x0+8+h2,y0+8+h2,S-12-h2,h2,'b',roofs[Math.floor(R()*roofs.length)]]); }
      for(let k=0;k<3;k++) trees.push([x0+2+R()*(S-4), y0+S-1.5, 1.1]);
    }
  }
  // kerbside parked cars on some roads
  for(let i=0;i<=B;i++) for(let j=0;j<B;j++){ if(R()<0.5){ const x=i*CELL+ROAD-1.4-0.0, y=j*CELL+ROAD+8+R()*30; if(i>0) cars.push([x,y,-90,Math.floor(R()*PARK_COLORS.length)]); } }
  // outer hedge ring trees
  for(let k=0;k<70;k++){ const t=k/70*4, side=Math.floor(t), f=t-side; const p = side===0?[f*N,-4]:side===1?[N+4,f*N]:side===2?[N-f*N,N+4]:[-4,N-f*N]; trees.push([p[0],p[1],2+R()*1.5]); }
  return { name:'Free Drive', town:true, w:N, h:N, start:[ROAD/2+3, N-CELL*1.5, -90], walls, cars, trees, lots, marks, paves, CELL, ROAD, B };
}
