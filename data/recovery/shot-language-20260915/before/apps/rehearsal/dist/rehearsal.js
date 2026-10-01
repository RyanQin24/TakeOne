// Shared progress controller for synthetic rehearsal. Not a hardware servo loop.
export const clamp=(v,a=0,b=1)=>Math.min(b,Math.max(a,v));
export const ease=u=>{u=clamp(u);return 10*u**3-15*u**4+6*u**5;};
export function createState(){return {playing:false,actor:0,robot:0,wall:0,velocity:0,pace:1,mode:'follow',actorPaused:false,lost:false,obstacle:false,duration:16};}
export function reset(s){Object.assign(s,{playing:false,actor:0,robot:0,wall:0,velocity:0,actorPaused:false,lost:false});}
export function seek(s,p){if(!Number.isFinite(p)||p<0||p>1)throw Error('Progress must be between 0 and 1');s.playing=false;s.actor=p;s.robot=p;s.wall=p*s.duration;s.velocity=0;}
export function step(s,dt){
  if(!Number.isFinite(dt)||dt<0||dt>.05)throw Error('Use a timestep of 0–50 ms');
  if(!s.playing)return;
  // Fault buttons model the supervisory HOLD decision. Physical braking is outside this MVP.
  if(s.lost||s.obstacle){s.velocity=0;return;}
  s.wall+=dt;
  const actorRate=s.actorPaused?0:s.pace/s.duration;
  s.actor=clamp(s.actor+dt*actorRate);
  if(s.mode==='clock'){
    s.robot=clamp(s.robot+dt/s.duration);s.velocity=1/s.duration;
  }else{
    const rate=(s.actor>=1?0:actorRate)+3*(s.actor-s.robot);
    const wanted=clamp(rate,0,1/s.duration);
    s.velocity+=clamp(wanted-s.velocity,-.18*dt,.18*dt);
    // Do not run ahead of an observed beat; this is a kinematic timeline constraint.
    s.robot=Math.min(s.actor,clamp(s.robot+dt*s.velocity));
    if(s.actor>=1&&1-s.robot<.0003){s.robot=1;s.velocity=0;}
  }
  if(s.actor>=1&&s.robot>=1){s.playing=false;s.velocity=0;}
  // Motor predictions end at the recorded command window, independent of actor pace.
  if(s.motorReplay&&s.robot>=1){s.playing=false;s.velocity=0;}
}
export function actorYaw(settings,progress){return Math.PI-settings.orbit*Math.PI/360+settings.turn*Math.PI/180*ease(progress);}
export function executionFrameAt(frames,timeSeconds){
  if(!Array.isArray(frames)||!frames.length||!Number.isFinite(timeSeconds))throw new Error('Invalid execution preview');
  let low=0,high=frames.length;
  while(low<high){const mid=(low+high)>>1;if(frames[mid].time_s<=timeSeconds)low=mid+1;else high=mid;}
  return frames[Math.max(0,low-1)];
}
export function status(s){
  if(s.obstacle)return 'Hold · path blocked';
  if(s.lost)return 'Hold · tracking lost';
  if(s.actor>=1&&s.robot>=1)return 'Take complete';
  if(!s.playing)return s.robot===0?'Ready to rehearse':'Paused';
  if(s.actorPaused)return s.mode==='follow'?'Holding for actor':'Clock continues';
  return s.mode==='follow'?'Following actor':'Fixed-clock replay';
}
