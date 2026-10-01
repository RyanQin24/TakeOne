import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {clamp,ease,createState,reset,seek,step,actorYaw,status,executionFrameAt} from './rehearsal.js';
import {createRobot,disposeRobot,animateDrive} from './robot-model.js';

const $=id=>document.getElementById(id);
const state=createState();let reviewedRobotPlan=null;let shot=null,model=null,dirty=false,busy=true,accepted=false,lastCue=-1;
state.mode='clock';state.motorReplay=true;
let bodyGroups=[],robotRoot,actor,head,helpers=new THREE.Group(),pathGroup=new THREE.Group(),obstacle;
const jointViews=[];const form={};let currentCameraPos=new THREE.Vector3();
const scene=new THREE.Scene();scene.background=new THREE.Color('#293b40');scene.fog=new THREE.Fog('#293b40',8,19);
THREE.Object3D.DEFAULT_UP.set(0,0,1);
const worldCamera=new THREE.PerspectiveCamera(43,1,.02,40);worldCamera.position.set(-3.8,-4.6,3.4);worldCamera.layers.enable(1);
const filmCamera=new THREE.PerspectiveCamera(49.6,16/9,.025,30);filmCamera.up.set(0,0,1);
const renderer=new THREE.WebGLRenderer({canvas:$('worldCanvas'),antialias:true});
const filmRenderer=new THREE.WebGLRenderer({canvas:$('cameraCanvas'),antialias:true});
for(const r of [renderer,filmRenderer]){r.setPixelRatio(Math.min(devicePixelRatio,1.7));r.shadowMap.enabled=true;r.shadowMap.type=THREE.PCFSoftShadowMap;r.toneMapping=THREE.ACESFilmicToneMapping;r.toneMappingExposure=1.1;r.outputColorSpace=THREE.SRGBColorSpace;}
const controls=new OrbitControls(worldCamera,renderer.domElement);controls.target.set(-.65,0,.7);controls.enableDamping=true;controls.dampingFactor=.07;controls.minDistance=.6;controls.maxDistance=10;controls.maxPolarAngle=Math.PI*.49;controls.update();
const studioLights=new THREE.Group();
scene.add(new THREE.HemisphereLight('#d5e8ec','#596452',2));
const key=new THREE.DirectionalLight('#fff0d5',3.2);key.position.set(-2,-3,6);key.castShadow=true;key.shadow.mapSize.set(2048,2048);Object.assign(key.shadow.camera,{left:-5,right:5,top:5,bottom:-5,near:.1,far:15});key.shadow.bias=-.0003;scene.add(key);
const rim=new THREE.DirectionalLight('#a4d7df',2);rim.position.set(2,3,4);scene.add(rim);
const lamp=new THREE.SpotLight('#ffdab0',8,8,28*Math.PI/180,.45,2);lamp.castShadow=true;lamp.shadow.mapSize.set(1024,1024);lamp.shadow.bias=-.0001;scene.add(lamp,lamp.target);
const mat=(color,roughness=.7,metalness=.05)=>new THREE.MeshStandardMaterial({color,roughness,metalness});
function mesh(geometry,material,parent=scene,pos=[0,0,0]){const m=new THREE.Mesh(geometry,material);m.position.fromArray(pos);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m;}
const floor=mesh(new THREE.PlaneGeometry(40,40),mat('#586967'));floor.position.z=-.012;
const platform=mesh(new THREE.BoxGeometry(5,4,.055),mat('#697b75'),scene,[-.45,0,-.04]);
const grid=new THREE.GridHelper(5,10,'#91a39b','#7e9089');grid.rotation.x=Math.PI/2;grid.position.set(-.45,0,.001);grid.material.transparent=true;grid.material.opacity=.38;scene.add(grid);
// One nominal set description is shared with the offline swept geometry screen.
const setProxies=new THREE.Group();scene.add(setProxies);
function buildSet(specification){
  while(setProxies.children.length){const child=setProxies.children[0];setProxies.remove(child);child.geometry.dispose();child.material.dispose();}
  for(const box of specification.boxes)mesh(new THREE.BoxGeometry(...box.size_m),mat(box.color),setProxies,box.center_m);
}
scene.add(helpers,pathGroup);
function makeLabel(text,color='#d5e9df',scale=.4){const c=document.createElement('canvas');c.width=512;c.height=128;const ctx=c.getContext('2d');ctx.font='600 46px Segoe UI';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle=color;ctx.fillText(text,256,64);const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;const sp=new THREE.Sprite(new THREE.SpriteMaterial({map:t,transparent:true,depthTest:false}));sp.scale.set(scale,scale/4,1);sp.layers.set(1);helpers.add(sp);return sp;}
const actorLabel=makeLabel('A / ACTOR','#b8f5dd',.56);actorLabel.position.set(0,0,1.95);
const robotLabel=makeLabel('TAKE ONE','#d6edff',.45);
const heightGuide=new THREE.Group();helpers.add(heightGuide);
const heightSegments=[-.42,-.3,0,-.42,-.3,1.8];
for(const z of [0,1.23,1.8])heightSegments.push(-.48,-.3,z,-.36,-.3,z);
const heightGeometry=new THREE.BufferGeometry();heightGeometry.setAttribute('position',new THREE.Float32BufferAttribute(heightSegments,3));
const heightLines=new THREE.LineSegments(heightGeometry,new THREE.LineBasicMaterial({color:'#b4d8e9',transparent:true,opacity:.8}));heightLines.layers.set(1);heightGuide.add(heightLines);
for(const [z,text] of [[1.23,'1.23 m / ARM PLATFORM'],[1.8,'1.80 m / MEASURED MAX']]){const label=makeLabel(text,'#d6edff',.8);heightGuide.add(label);label.position.set(-.82,-.3,z);}
function frameArrow(parent,direction,color,text,position){const arrow=new THREE.ArrowHelper(direction.clone().normalize(),position,.32,color,.08,.045);parent.add(arrow);const label=makeLabel(text,'#ffffff',.46);parent.add(label);label.position.copy(position).add(direction.clone().normalize().multiplyScalar(.42));return arrow;}
const worldAxes=new THREE.Group();helpers.add(worldAxes);frameArrow(worldAxes,new THREE.Vector3(1,0,0),0xe46f61,'WORLD +X',new THREE.Vector3(0,0,.03));frameArrow(worldAxes,new THREE.Vector3(0,1,0),0x72c78e,'WORLD +Y',new THREE.Vector3(0,0,.03));frameArrow(worldAxes,new THREE.Vector3(0,0,1),0x72a9e8,'WORLD +Z',new THREE.Vector3(0,0,.03));
const cartAxes=new THREE.Group();helpers.add(cartAxes);frameArrow(cartAxes,new THREE.Vector3(0,1,0),0x78d7eb,'PHONE / CART +Y',new THREE.Vector3(0,0,.03));frameArrow(cartAxes,new THREE.Vector3(-1,0,0),0xf2a661,'WHEEL FRONT / CART -X',new THREE.Vector3(0,0,.03));
function capsule(radius,length,material,parent,pos){const m=mesh(new THREE.CapsuleGeometry(radius,length,6,12),material,parent,pos);m.rotation.x=Math.PI/2;return m;}
function buildActor(height){
  if(actor){scene.remove(actor);actor.traverse(o=>{if(o.geometry)o.geometry.dispose();});}
  actor=new THREE.Group();actor.scale.setScalar(height/1.72);scene.add(actor);
  const cloth=mat('#bd7754'),pants=mat('#263338'),skin=mat('#dab08f'),hair=mat('#3c302b');
  capsule(.105,.58,pants,actor,[0,-.115,.44]);capsule(.105,.58,pants,actor,[0,.115,.44]);
  const shoeMat=mat('#192628');mesh(new THREE.BoxGeometry(.29,.16,.1),shoeMat,actor,[.055,-.12,.05]);mesh(new THREE.BoxGeometry(.29,.16,.1),shoeMat,actor,[.055,.12,.05]);
  const torso=capsule(.22,.31,cloth,actor,[0,0,1.11]);torso.scale.set(.64,1,1);
  const pelvis=mesh(new THREE.SphereGeometry(.22,20,12),pants,actor,[0,0,.86]);pelvis.scale.set(.64,1,.64);
  for(const side of [-1,1]){const arm=capsule(.066,.47,cloth,actor,[.005,side*.265,1.025]);arm.rotation.x+=side*.13;capsule(.052,.075,skin,actor,[.02,side*.295,.73]);}
  capsule(.055,.05,skin,actor,[0,0,1.445]);
  head=new THREE.Group();head.position.set(0,0,1.59);actor.add(head);
  const skull=mesh(new THREE.SphereGeometry(.12,24,18),skin,head);skull.scale.set(.87,.82,1.14);
  const cap=mesh(new THREE.SphereGeometry(.121,24,12,0,Math.PI*2,0,Math.PI*.6),hair,head,[0,0,.017]);cap.rotation.x=Math.PI/2;cap.scale.set(.94,.94,1.05);
  const nose=mesh(new THREE.SphereGeometry(.022,12,10),skin,head,[.104,0,-.015]);nose.scale.set(1,.65,1.15);
  for(const y of [-.042,.042]){mesh(new THREE.SphereGeometry(.012,12,8),mat('#241c1c'),head,[.095,y,.015]);}
  actorLabel.position.z=height+.23;
}
buildActor(1.72);
const markMat=new THREE.MeshBasicMaterial({color:'#82d9b8',side:THREE.DoubleSide,transparent:true,opacity:.7});
const ring=mesh(new THREE.RingGeometry(.31,.323,72),markMat,scene,[0,0,.012]);ring.castShadow=false;
const arrow=mesh(new THREE.ConeGeometry(.045,.13,3),markMat,scene);arrow.rotation.x=Math.PI/2;arrow.layers.set(1);
const markB=makeLabel('B / EYELINE','#a9e5c8',.56);
const camVolume=new THREE.Group(),lightVolume=new THREE.Group();helpers.add(camVolume,lightVolume);
function volume(group,angle,aspect,length,color,round=false){
  while(group.children.length){const c=group.children[0];group.remove(c);c.geometry?.dispose();c.material?.dispose();}
  const h=Math.tan(angle*Math.PI/180)*length,w=h*aspect;let points=[];
  if(round){for(let i=0;i<40;i++){const a=i/40*Math.PI*2;points.push(new THREE.Vector3(h*Math.cos(a),h*Math.sin(a),length));}}
  else points=[new THREE.Vector3(-w,-h,length),new THREE.Vector3(w,-h,length),new THREE.Vector3(w,h,length),new THREE.Vector3(-w,h,length)];
  const lines=[],tris=[];
  for(let i=0;i<points.length;i++){const a=points[i],b=points[(i+1)%points.length];lines.push(...a.toArray(),...b.toArray());if(!round||i%10===0)lines.push(0,0,0,...a.toArray());tris.push(0,0,0,...a.toArray(),...b.toArray());}
  const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(tris,3));
  const surface=new THREE.Mesh(geo,new THREE.MeshBasicMaterial({color,transparent:true,opacity:.045,side:THREE.DoubleSide,depthWrite:false}));group.add(surface);
  const lg=new THREE.BufferGeometry();lg.setAttribute('position',new THREE.Float32BufferAttribute(lines,3));group.add(new THREE.LineSegments(lg,new THREE.LineBasicMaterial({color,transparent:true,opacity:.55,depthWrite:false})));
  group.traverse(o=>o.layers.set(1));
}
function updateVolumes(){volume(camVolume,+$('fov').value/2,16/9,2.1,'#80c4ff');volume(lightVolume,+$('beam').value,1,1.9,'#edbd72',true);lamp.angle=+$('beam').value*Math.PI/180;lamp.intensity=+$('brightness').value/10;filmCamera.fov=+$('fov').value;filmCamera.updateProjectionMatrix();$('fovValue').value=$('fov').value+'°';$('lensLabel').textContent=$('fov').value+'° · 16:9';$('beamValue').value=$('beam').value+'°';$('brightnessValue').value=$('brightness').value+'%';}
updateVolumes();

function buildRobot(data){
  if(robotRoot)disposeRobot(robotRoot);
  const robot=createRobot(data);robotRoot=robot.root;bodyGroups=robot.bodyGroups;scene.add(robotRoot);
  jointViews.length=0;
  $('jointList').replaceChildren();
  data.jointNames.forEach((name,i)=>{if(i%5===0){const title=document.createElement('div');title.className='joint-title';title.textContent=i===0?'CAMERA ARM':'LIGHT ARM';$('jointList').append(title);}const row=document.createElement('div');row.className='joint-row';const label=document.createElement('span');label.textContent=['Pan','Shoulder','Elbow','Wrist pitch','Wrist roll'][i%5];const meter=document.createElement('meter');meter.min=data.jointLimits[i][0];meter.max=data.jointLimits[i][1];const number=document.createElement('b');row.append(label,meter,number);$('jointList').append(row);jointViews.push({meter,number});});
}
function rebuildPath(){
  pathGroup.traverse(o=>{o.geometry?.dispose();o.material?.dispose();});pathGroup.clear();
  const frames=shot.executionPreview.frames;
  const points=frames.map(f=>new THREE.Vector3(f.q[0],f.q[1],.018));
  const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color:'#f6aa6b'}));line.layers.set(1);pathGroup.add(line);
  const requested=frames.map(f=>new THREE.Vector3(f.drive.referenceCart[0],f.drive.referenceCart[1],.02));
  const planned=new THREE.Line(new THREE.BufferGeometry().setFromPoints(requested),new THREE.LineDashedMaterial({color:'#91c8ec',dashSize:.055,gapSize:.035}));planned.computeLineDistances();planned.layers.set(1);pathGroup.add(planned);
  for(const index of [0,frames.length-1]){const f=frames[index];const dot=mesh(new THREE.RingGeometry(.07,.09,32),new THREE.MeshBasicMaterial({color:'#8cc4ed',side:THREE.DoubleSide}),pathGroup,[f.q[0],f.q[1],.017]);dot.layers.set(1);}
  if(obstacle)scene.remove(obstacle);
  const f=frames[Math.floor(frames.length/2)];obstacle=mesh(new THREE.BoxGeometry(.48,.48,.58),mat('#a7543d'),scene,[f.q[0],f.q[1],.29]);obstacle.visible=state.obstacle;
  const yaw=actorYaw(shot.settings,1);markB.position.set(Math.cos(yaw)*.58,Math.sin(yaw)*.58,.05);
}
const tempA=new THREE.Quaternion(),tempB=new THREE.Quaternion();
function interpolateQuat(out,a,b,t){tempA.fromArray(a);tempB.fromArray(b);out.copy(tempA).slerp(tempB,t);}
const opticalToCamera=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0),Math.PI);
let projectedError=0,beatMismatch=0;
function shotPhase(progress){return clamp((progress*state.duration-(reviewedRobotPlan?.revision.transition_s||0))/shot.settings.duration);}
function updateScene(){
  if(!shot)return;
  // A held motor pose owns the robot until playback resumes, so the shot frames
  // do not fight the sliders for the same body groups.
  if(motorPose){poseFromMotors(motorPose);return;}
  const a=executionFrameAt(shot.executionPreview.frames,state.robot*state.duration),b=a,t=0;
  bodyGroups.forEach((g,j)=>{const aa=a.bodies[j],bb=b.bodies[j];g.position.set(THREE.MathUtils.lerp(aa[0],bb[0],t),THREE.MathUtils.lerp(aa[1],bb[1],t),THREE.MathUtils.lerp(aa[2],bb[2],t));interpolateQuat(g.quaternion,aa.slice(3),bb.slice(3),t);});
  const driveFrame={drive:{...a.drive,wheelAngles:a.drive.wheelAngles.map((v,j)=>THREE.MathUtils.lerp(v,b.drive.wheelAngles[j],t))}};
  animateDrive(bodyGroups,driveFrame);
  $('motorWire').textContent=a.drive.wire.trim();
  $('wheelSpeed').textContent=a.drive.wheelSpeeds.map(v=>(v*100).toFixed(1)).join(' / ')+' cm/s';
  $('driveError').textContent=(a.drive.pathError*100).toFixed(1)+' cm';
  filmCamera.position.fromArray(a.camera.pos).lerp(new THREE.Vector3().fromArray(b.camera.pos),t);interpolateQuat(filmCamera.quaternion,a.camera.quat,b.camera.quat,t);camVolume.position.copy(filmCamera.position);camVolume.quaternion.copy(filmCamera.quaternion);filmCamera.quaternion.multiply(opticalToCamera);filmCamera.updateMatrixWorld();
  lightVolume.position.fromArray(a.light.pos).lerp(new THREE.Vector3().fromArray(b.light.pos),t);interpolateQuat(lightVolume.quaternion,a.light.quat,b.light.quat,t);lamp.position.copy(lightVolume.position);lamp.target.position.set(0,0,1).applyQuaternion(lightVolume.quaternion).add(lamp.position);
  actor.rotation.z=actorYaw(shot.settings,shotPhase(state.actor));const face=new THREE.Vector3(.085*Math.cos(actor.rotation.z),.085*Math.sin(actor.rotation.z),1.6).multiplyScalar(shot.settings.actorHeight/1.72);const projection=face.clone().project(filmCamera);projectedError=Math.hypot(projection.x/2,projection.y/2)*100;
  beatMismatch=Math.abs(shot.settings.turn*(ease(shotPhase(state.robot))-ease(shotPhase(state.actor))));
  arrow.position.set(.37*Math.cos(actor.rotation.z),.37*Math.sin(actor.rotation.z),.023);arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),new THREE.Vector3(Math.cos(actor.rotation.z),Math.sin(actor.rotation.z),0));
  robotLabel.position.set(a.q[0],a.q[1],1.95);heightGuide.position.set(a.q[0],a.q[1],0);cartAxes.position.set(a.q[0],a.q[1],.54);cartAxes.rotation.z=a.q[2];currentCameraPos.copy(filmCamera.position);
  camVolume.visible=$('showCamera').checked;lightVolume.visible=$('showLight').checked;
  for(let j=0;j<10;j++){const value=THREE.MathUtils.lerp(a.q[j+3],b.q[j+3],t);jointViews[j].meter.value=value;const raw=a.rawPositions?.[j];jointViews[j].number.textContent=(value*180/Math.PI).toFixed(1)+'°'+(Number.isInteger(raw)?` · raw ${raw}`:'');}
}
function clock(seconds){const s=Math.max(0,seconds);return `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;}
function cueFor(){if(state.obstacle)return {id:5,name:'PATH BLOCKED',text:'Hold position. Clear the marked robot path.'};if(state.lost)return {id:4,name:'TRACKING LOST',text:'Hold your position. Waiting for actor tracking.'};if(state.actorPaused)return {id:6,name:'ACTOR PAUSED',text:'Hold your turn. Resume when you’re ready.'};const p=shotPhase(state.actor);return p>=1&&state.robot>=1?{id:3,name:'COMPLETE',text:shot.actorCues[3].text}:p>.8?{id:2,name:'FINISH + HOLD',text:shot.actorCues[2].text}:p>.02?{id:1,name:'TURN + TRACK',text:shot.actorCues[1].text}:{id:0,name:'READY',text:shot.actorCues[0].text};}
function updateUI(){
  if(!shot)return;
  $('actorProgress').style.width=(state.actor*100)+'%';$('robotProgress').style.width=(state.robot*100)+'%';$('actorPct').textContent=Math.round(state.actor*100)+'%';$('robotPct').textContent=Math.round(state.robot*100)+'%';$('scrub').value=state.robot;
  $('clock').innerHTML=`${clock(state.wall)} <small>/ ${clock(state.duration)} planned</small>`;$('monitorTime').textContent=clock(state.wall);
  $('playBtn').textContent=state.playing?'Ⅱ Pause preview':'▶ Preview prediction';$('runStatus').textContent=dirty?'Settings changed':state.playing?'Replaying motor prediction':state.robot>=1?'End of command window':!shot.drive.reproducesRequestedPath?'Requested path not achieved':'Prediction ready';$('runStatus').classList.toggle('warn',dirty||!shot.playable);
  $('frameError').textContent=projectedError.toFixed(1)+'%';$('beatError').textContent=beatMismatch.toFixed(1)+'°';$('beatError').style.color=beatMismatch>5?'#ffac80':'';$('cameraHeightValue').textContent=currentCameraPos.z.toFixed(2)+' m';
  const cue=cueFor();$('cue').textContent=cue.text;$('beatName').textContent=cue.name;
  if(cue.id!==lastCue){lastCue=cue.id;if($('voice').checked&&state.playing&&'speechSynthesis'in window){speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(cue.text);utterance.rate=.92;speechSynthesis.speak(utterance);}}
  $('pauseActorBtn').textContent=state.actorPaused?'Resume actor':'Pause actor';$('lostBtn').textContent=state.lost?'Restore tracking':'Test tracking loss';
}
function resize(){const r=$('stage').getBoundingClientRect();renderer.setSize(r.width,r.height,false);worldCamera.aspect=r.width/r.height;worldCamera.updateProjectionMatrix();const f=$('cameraCanvas').parentElement.getBoundingClientRect();filmRenderer.setSize(f.width,f.height,false);}
new ResizeObserver(resize).observe($('stage'));new ResizeObserver(resize).observe($('cameraCanvas').parentElement);

// ---- Motor test: ten real encoder sliders, calibration-bounded, FK only ----
let motorTable=null,motorPose=null,motorBusy=false,motorQueued=null;
const motorValues={phone:{},light:{}};
function poseFromMotors(pose){
  const f=pose.frame;
  bodyGroups.forEach((g,j)=>{const b=f.bodies[j];g.position.set(b[0],b[1],b[2]);g.quaternion.set(b[3],b[4],b[5],b[6]);});
  filmCamera.position.fromArray(f.camera.pos);filmCamera.quaternion.fromArray(f.camera.quat);
  camVolume.position.copy(filmCamera.position);camVolume.quaternion.copy(filmCamera.quaternion);
  filmCamera.quaternion.multiply(opticalToCamera);filmCamera.updateMatrixWorld();
  lightVolume.position.fromArray(f.light.pos);lightVolume.quaternion.fromArray(f.light.quat);
  lamp.position.copy(lightVolume.position);lamp.target.position.set(0,0,1).applyQuaternion(lightVolume.quaternion).add(lamp.position);
  camVolume.visible=$('showCamera').checked;lightVolume.visible=$('showLight').checked;
  for(let j=0;j<10;j++){const value=f.q[j+3];jointViews[j].meter.value=value;
    const raw=f.rawPositions?.[j]??Object.values(pose.motors[j<5?'phone':'light'])[j%5];
    jointViews[j].number.textContent=(value*180/Math.PI).toFixed(1)+'°'+(Number.isInteger(raw)?` · raw ${raw}`:'');}
}
async function requestMotorPose(){
  if(motorBusy){motorQueued=true;return;}
  motorBusy=true;
  try{
    const body={lightType:$('lightType')?.value||'ring',motors:{phone:{...motorValues.phone},light:{...motorValues.light}}};
    const r=await fetch('/api/pose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await r.json();
    if(!r.ok)throw new Error(data.error||'Pose failed');
    motorPose=data;
    state.playing=false;
    const hit=data.contacts;
    const box=$('motorStatus');
    if(hit?.colliding){
      // Real MuJoCo interpenetration, not a proximity guess: these poses exist
      // on the sliders but the hardware would jam or break reaching them.
      const worst=hit.pairs[0];
      box.textContent=`COLLISION · ${hit.pair_count} contact${hit.pair_count>1?'s':''} · worst ${worst.penetration_mm} mm · ${worst.geoms}`;
      box.style.color='#ff9d7a';
    }else{
      box.textContent='Clear · no self-collision · nothing sent to the robot';
      box.style.color='';
    }
  }catch(err){$('motorStatus').textContent='Pose failed: '+err.message;}
  finally{motorBusy=false;if(motorQueued){motorQueued=false;requestMotorPose();}}
}
function buildMotorSliders(table){
  const host=$('motorSliders');host.textContent='';
  for(const role of ['phone','light']){
    const info=table.roles[role];
    const heading=document.createElement('div');heading.className='section-title';
    heading.textContent=(role==='phone'?'PHONE ARM · COM9':'LIGHT ARM · COM8');
    host.appendChild(heading);
    for(const name of table.joint_order){
      const j=info.joints[name];
      motorValues[role][name]=j.midpoint;
      const label=document.createElement('label');label.className='field-label';
      label.htmlFor=`motor-${role}-${name}`;
      const out=document.createElement('output');
      out.textContent=`${j.midpoint} · 0.0°`;
      label.textContent=`ID ${j.id} ${name.replace('_',' ')} `;label.appendChild(out);
      const input=document.createElement('input');
      input.type='range';input.id=`motor-${role}-${name}`;
      input.min=j.min;input.max=j.max;input.step=1;input.value=j.midpoint;
      input.addEventListener('input',()=>{
        const v=Number(input.value);motorValues[role][name]=v;
        out.textContent=`${v} · ${((v-j.midpoint)*360/4095).toFixed(1)}°`;
        requestMotorPose();
      });
      const captions=document.createElement('div');captions.className='range-captions';
      captions.innerHTML=`<span>${j.min}</span><span>mid ${j.midpoint}</span><span>${j.max}</span>`;
      host.append(label,input,captions);
      info.joints[name].output=out;info.joints[name].input=input;
    }
  }
}
function resetMotorsToMidpoint(){
  if(!motorTable)return;
  for(const role of ['phone','light'])for(const name of motorTable.joint_order){
    const j=motorTable.roles[role].joints[name];
    motorValues[role][name]=j.midpoint;
    if(j.input){j.input.value=j.midpoint;j.output.textContent=`${j.midpoint} · 0.0°`;}
  }
  requestMotorPose();
}
async function loadMotorTable(){
  try{
    const r=await fetch('/api/motors');const data=await r.json();
    if(!r.ok)throw new Error(data.error||'Calibration unavailable');
    motorTable=data;buildMotorSliders(data);
    $('motorStatus').textContent='Ranges are the installed calibration. Move a motor to pose the arm.';
  }catch(err){$('motorStatus').textContent='Calibration unavailable: '+err.message;}
}
$('motorsMid')?.addEventListener('click',resetMotorsToMidpoint);
$('motorPanel')?.addEventListener('toggle',()=>{if($('motorPanel').open&&!motorTable)loadMotorTable();});
// Playing the shot hands the robot back to the timeline.
const releaseMotorPose=()=>{if(motorPose){motorPose=null;$('motorStatus').textContent='Released: the shot timeline owns the robot again.';}};
for(const [id,event] of [['playBtn','click'],['resetBtn','click'],['scrub','input']])$(id)?.addEventListener(event,releaseMotorPose);

let last=performance.now();function loop(now){requestAnimationFrame(loop);let dt=Math.min((now-last)/1000,.1);last=now;while(dt>0){const tick=Math.min(dt,.02);step(state,tick);dt-=tick;}updateScene();updateUI();controls.update();renderer.render(scene,worldCamera);filmRenderer.render(scene,filmCamera);}requestAnimationFrame(loop);

const fields=[['lightTravel','Light raw-range amplitude',0,1,.01,' × half-range'],['armTravel','Camera raw-range amplitude',0,1,.01,' × half-range'],['duration','Direct test duration',.2,60,.01,' s']];
function buildFields(settings){for(const [key,label,min,max,step,unit]of fields){const row=document.createElement('div');const l=document.createElement('label');l.className='field-label';l.htmlFor='setting-'+key;l.textContent=label;const o=document.createElement('output');o.id='value-'+key;const input=document.createElement('input');Object.assign(input,{id:'setting-'+key,type:'range',min,max,step,value:settings[key]});const format=()=>Number(input.value).toFixed(step<.001?4:step<1?2:0)+unit;o.value=format();l.append(o);row.append(l,input);$('shotFields').append(row);form[key]=input;input.addEventListener('input',()=>{o.value=format();dirty=true;state.playing=false;$('playBtn').disabled=true;$('exportBtn').disabled=true;$('robotPlanBtn').disabled=true;$('planState').textContent='CHANGED';$('compileMessage').textContent='Recalculate to validate these settings.';});}}
function showChecks(){const list=$('checksList');list.replaceChildren();let count=0;for(const check of [...shot.checks,...(reviewedRobotPlan?.execution_preview.revision_checks||[])]){const row=document.createElement('div');row.className='check-row'+(check.passed?'':' fail');const name=document.createElement('span');name.textContent=check.name;const value=document.createElement('b');value.textContent=`${check.passed?'✓':'!'} ${check.value} ${check.unit}`;row.append(name,value);list.append(row);if(check.passed)count++;}$('checkCount').textContent=`${count} / ${shot.checks.length+(reviewedRobotPlan?.execution_preview.revision_checks.length||0)} screens`;}
function setShot(next,prepared=null){shot=next;reviewedRobotPlan=prepared;if(prepared)shot.executionPreview=prepared.execution_preview;state.duration=prepared?.duration_s||shot.settings.duration;reset(state);dirty=false;busy=false;accepted=true;buildSet(shot.scene);buildActor(shot.settings.actorHeight);rebuildPath();showChecks();$('planState').textContent=(prepared?.plan_id||shot.planId).slice(0,6).toUpperCase();$('compileBtn').disabled=false;$('playBtn').disabled=!shot.previewAvailable;$('exportBtn').disabled=!shot.previewAvailable;$('robotPlanBtn').disabled=!shot.previewAvailable;$('robotPlanBtn').textContent=shot.directJointMode?'Download exact raw motor test ↓':'Prepare robot motion ↓';$('acceptBtn').hidden=true;
  for(const [key, , , ,step,unit] of fields){form[key].value=shot.settings[key];$('value-'+key).value=Number(form[key].value).toFixed(step<.001?4:step<1?2:0)+unit;}
  const heights=shot.executionPreview.frames.map(f=>f.camera.pos[2]);const height=[Math.min(...heights),Math.max(...heights)].map(v=>v.toFixed(2)).join('–');$('compileMessage').textContent=shot.directJointMode?`Direct raw-joint preview. Starts at all ten calibrated midpoints; no IK or task-space restrictions. Camera height ${height} m.`:`Predicted camera ${height} m. ${shot.playable?'Motion screens pass under the stated assumptions.':'Some motion screens fail; preview shows the failure, not an approved shot.'}`;
  const report=shot.drive;
  $('motionOutline').replaceChildren(...shot.motionOutline.map(motion=>{const row=document.createElement('p');row.textContent=shot.directJointMode?(motion.sweep_m===0?`${motion.role==='phone'?'Camera':'Light'} arm: fixed at all five calibrated midpoint counts.`:`${motion.role==='phone'?'Camera':'Light'} arm: smooth direct shoulder-pan sweep at ${(motion.sweep_m*100).toFixed(0)}% of its calibrated half-range; four other joints fixed.`):`${motion.role==='phone'?'Camera':'Light'} tracks the actor with ${(motion.sweep_m*100).toFixed(0)} cm sweep and ${(motion.lift_m*100).toFixed(0)} cm lift. Sweep follows the planned dolly direction; lift peaks at mid-shot.`;return row;}));
  $('driveProfile').value=shot.settings.driveProfile;$('lightType').value=shot.settings.lightType;
  $('armSummary').textContent=`Base turn ${shot.movement.baseTurnDegrees.toFixed(1)}° · Camera arm pan ${shot.movement.cameraJointRangesDegrees[0].toFixed(1)}° · Light arm pan ${shot.movement.lightJointRangesDegrees[0].toFixed(1)}°`;
  $('motionHelp').textContent=shot.directJointMode?`Exact cart packet: ${shot.motorCommands[0].wire.trim()}. Raw motor values are shown beside every joint and included in the download. No inverse kinematics is run.`:shot.settings.driveProfile==='arms'?`Initial left / right commands: ${(prepared?.cart_schedule[0].wire||shot.motorCommands[0].wire).trim()}. The arms track, sweep and lift along a straight requested dolly. Actual heading depends on each wheel's response. Duration sets travel distance; the orbit angle does not steer the base in this mode.`:'The base follows an orbit. Arm sweep and lift add motion within the available reach.';
  $('driveSummary').textContent=report.reproducesRequestedPath?`Wheel commands reproduce the requested path within ${(report.maxPathError*100).toFixed(2)} cm under the model assumptions.`:`Requested path fails: ${(report.maxPathError*100).toFixed(1)} cm maximum position error; ${report.maxYawErrorDegrees.toFixed(1)}° heading error. A wheel stalls in ${(report.stalledFraction*100).toFixed(1)}% of command intervals.`;
  const responseStatus=report.responseModel?.mode==='measured_table'?'Independent wheel tables; values between measurements are interpolated.':'Assumed equal wheel responses. The real cart drifts with equal commands; this preview does not correct that drift.';
  $('driveAssumptions').textContent=shot.directJointMode?`Direct joint-space mode. The simulator uses calibration min/mid/max counts and constant forward packet ${shot.motorCommands[0].wire.trim()}; it does not aim, solve IK, or reject poses for scene geometry.`:`19 cm × 6 cm tires · ${(report.trackWidth*100).toFixed(1)} cm wheel spacing (estimated). ${responseStatus} No wheel or heading feedback. Physical wiring direction still needs verification. Response/braking: ${report.responseTime.toFixed(2)} / ${report.brakeTime.toFixed(2)} s (assumed; zero = instantaneous). Coast after the command window: ${(report.predictedStopTravel*100).toFixed(1)} cm under the assumed braking model.`;
  if(!report.responseModel){$('robotPlanBtn').disabled=true;$('compileMessage').textContent='Restart the simulator to load the current wheel-response model before preparing robot motion.';}
  const load=shot.checks.find(c=>c.name==='Assumed payload margin');$('loadWarning').hidden=!!load?.passed;$('loadWarning').textContent=load&&!load.passed?`Visual rehearsal only: estimated arm demand ${load.value} N·m exceeds the assumed 0.800 N·m margin. Cart stability is unvalidated.`:'';
  $('loading').classList.add('hidden');lastCue=-1;updateScene();updateUI();resize();}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,3500);}
async function recalculate(){
  if(busy)return;busy=true;state.playing=false;window.speechSynthesis?.cancel();
  $('compileBtn').disabled=true;$('playBtn').disabled=true;$('exportBtn').disabled=true;$('robotPlanBtn').disabled=true;$('acceptBtn').hidden=true;$('lightType').disabled=true;$('driveProfile').disabled=true;$('steadyArc').disabled=true;$('armLed').disabled=true;
  Object.values(form).forEach(input=>input.disabled=true);$('compileMessage').textContent='Solving the cart path and both arms…';
  try{
    const settings={...Object.fromEntries(Object.entries(form).map(([k,v])=>[k,+v.value])),lightType:$('lightType').value,driveProfile:$('driveProfile').value};
    const res=await fetch(shot?.directJointMode?'/api/direct':'/api/compile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(settings)});
    const next=await res.json();if(!res.ok)throw Error(next.error);
    const modelResponse=await fetch('/api/model?lightType='+encodeURIComponent(settings.lightType)+'&trackWidth='+settings.trackWidth);
    if(!modelResponse.ok)throw Error('Unable to load selected light model');
    const nextModel=await modelResponse.json();if(nextModel.modelHash!==next.modelHash)throw Error('Model and shot do not match. Reload the simulator.');
    model=nextModel;buildRobot(model);setShot(next);$('downloadModel').href='/models/take-one-'+settings.lightType+'.glb';$('downloadModel').textContent='Download 3D robot (58 cm wheel spacing) ↓';
  }catch(e){busy=false;$('compileBtn').disabled=false;$('compileMessage').textContent=e.message;toast(e.message);}
  finally{Object.values(form).forEach(input=>input.disabled=false);$('lightType').disabled=false;$('driveProfile').disabled=false;$('steadyArc').disabled=false;$('armLed').disabled=false;}
}
$('lightType').onchange=()=>{dirty=true;state.playing=false;$('playBtn').disabled=true;$('exportBtn').disabled=true;$('robotPlanBtn').disabled=true;$('planState').textContent='CHANGED';recalculate();};
function play(){if(!shot||dirty||!shot.previewAvailable||busy)return;if(state.robot===1)reset(state);state.playing=!state.playing;if(state.playing)lastCue=-1;else window.speechSynthesis?.cancel();updateUI();}
function setMode(mode){if(mode==='follow')throw Error('Actor-follow retiming is unavailable for UART replay');if(!['follow','clock'].includes(mode))throw Error('Unknown coordination mode');if(mode!==state.mode){reset(state);lastCue=-1;window.speechSynthesis?.cancel();toast('Rehearsal reset to compare from the same starting pose.');}state.mode=mode;$('followBtn').classList.toggle('selected',mode==='follow');$('clockBtn').classList.toggle('selected',mode==='clock');$('followBtn').setAttribute('aria-pressed',mode==='follow');$('clockBtn').setAttribute('aria-pressed',mode==='clock');$('modeHelp').textContent=mode==='follow'?'Robot progress adapts to the simulated actor’s turn.':'Motor commands replay at their original timing. Actor pace changes the actor only.';}
$('compileBtn').onclick=recalculate;$('playBtn').onclick=play;$('resetBtn').onclick=()=>{reset(state);lastCue=-1;window.speechSynthesis?.cancel();};$('scrub').oninput=e=>{seek(state,+e.target.value);lastCue=-1;window.speechSynthesis?.cancel();};
$('actorSpeed').oninput=e=>{state.pace=+e.target.value;$('paceValue').value=Math.round(state.pace*100)+'%';};$('slowBtn').onclick=()=>{$('actorSpeed').value=.5;$('actorSpeed').dispatchEvent(new Event('input'));toast('Actor at half speed. Motor replay timing stays fixed.');};
$('followBtn').onclick=()=>setMode('follow');$('clockBtn').onclick=()=>setMode('clock');$('pauseActorBtn').onclick=()=>{state.actorPaused=!state.actorPaused;};$('lostBtn').onclick=()=>{state.lost=!state.lost;};
$('obstacle').onchange=e=>{state.obstacle=e.target.checked;if(obstacle)obstacle.visible=state.obstacle;};
$('acceptBtn').onclick=()=>{accepted=true;$('acceptBtn').hidden=true;$('playBtn').disabled=!shot.playable;$('exportBtn').disabled=!shot.playable;$('robotPlanBtn').disabled=!shot.previewAvailable;$('compileMessage').textContent='Revised height accepted for this simulated rehearsal. Hardware not approved.';};
for(const id of ['fov','beam','brightness'])$(id).addEventListener('input',updateVolumes);
$('voice').onchange=()=>{if(!$('voice').checked)window.speechSynthesis?.cancel();else if(!('speechSynthesis'in window)){toast('Speech is unavailable in this browser. Actor cues remain visible.');$('voice').checked=false;}else lastCue=-1;};
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-view]').forEach(x=>x.classList.toggle('selected',x===b));if(b.dataset.view==='top'){worldCamera.position.set(-.45,-.01,5.9);controls.target.set(-.45,0,0);}else if(b.dataset.view==='rig'&&shot){const f=executionFrameAt(shot.executionPreview.frames,state.robot*state.duration);controls.target.set(f.q[0],f.q[1],1.05);worldCamera.position.set(f.q[0]-1.8,f.q[1]-1.8,2.15);}else{worldCamera.position.set(-3.8,-4.6,3.4);controls.target.set(-.65,0,.9);}controls.update();});
function openReference(){state.playing=false;$('referenceDialog').showModal();$('referenceVideo').currentTime=1.5;}
$('referenceBtn').onclick=openReference;$('referenceCard').onclick=openReference;$('closeReference').onclick=()=>{$('referenceDialog').close();};$('referenceDialog').addEventListener('close',()=>$('referenceVideo').pause());
$('exportBtn').onclick=()=>{if(!shot||busy||dirty||!shot.previewAvailable)return;const exported=reviewedRobotPlan||{...shot,frames:shot.frames.map((f,i)=>({time:i*shot.settings.duration/(shot.frames.length-1),phase:i/(shot.frames.length-1),q:f.q,camera:f.camera,light:f.light,drive:f.drive})),modelHash:model.modelHash,revisionAccepted:accepted,view:{fov:+$('fov').value,beam:+$('beam').value,intensity:+$('brightness').value},rehearsal:{mode:state.mode,actorPace:state.pace},hardwareReady:false};const url=URL.createObjectURL(new Blob([JSON.stringify(exported,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=reviewedRobotPlan?`takeone-robot-${reviewedRobotPlan.plan_id.slice(0,12)}.json`:`take-one-orbit-${shot.planId}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast(reviewedRobotPlan?'Exported the exact reviewed robot plan, including its transitions.':'Exported shot settings, actor cues, and solved joint poses.');};
document.addEventListener('keydown',e=>{if(e.code==='Space'&&!['INPUT','BUTTON','SELECT','TEXTAREA'].includes(document.activeElement.tagName)&&!$('referenceDialog').open){e.preventDefault();play();}});
window.addEventListener('error',e=>{console.error(e.error);if(!shot){$('loading').classList.remove('hidden');$('loading').textContent='The scene could not start. '+e.message;}});
window.takeOne={read:()=>({ready:!!shot,playing:state.playing,progress:state.robot,actorProgress:state.actor,mode:state.mode,pace:state.pace,status:status(state),frameError:projectedError,beatMismatch,dirty,playable:shot?.playable,hardwareReady:false,planId:reviewedRobotPlan?.plan_id||shot?.planId}),state};
function registerTools(){if(!document.modelContext?.registerTool)return;const lifecycle=new AbortController();const register=t=>Promise.resolve(document.modelContext.registerTool(t,{signal:lifecycle.signal})).catch(console.warn);register({name:'read_rehearsal',description:'Read the current local simulated rehearsal state.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true},execute:()=>window.takeOne.read()});register({name:'configure_rehearsal_playback',description:'Set simulated actor pace and coordination mode, then seek both tracks to a shared progress. Does not command hardware or start playback.',inputSchema:{type:'object',properties:{pace:{type:'number',minimum:.25,maximum:1},mode:{type:'string',enum:['clock']},progress:{type:'number',minimum:0,maximum:1}},required:['pace','mode','progress'],additionalProperties:false},execute:input=>{if(!input||typeof input.pace!=='number'||!Number.isFinite(input.pace)||input.pace<.25||input.pace>1||!['follow','clock'].includes(input.mode)||typeof input.progress!=='number'||!Number.isFinite(input.progress)||input.progress<0||input.progress>1)throw Error('Invalid playback settings');setMode(input.mode);state.pace=input.pace;$('actorSpeed').value=input.pace;$('paceValue').value=Math.round(input.pace*100)+'%';seek(state,input.progress);updateScene();updateUI();return window.takeOne.read();}});window.addEventListener('pagehide',()=>lifecycle.abort(),{once:true});}
try{const [modelResponse,shotResponse]=await Promise.all([fetch('/api/model'),fetch('/api/shot')]);if(!modelResponse.ok||!shotResponse.ok)throw Error('Local simulator unavailable');model=await modelResponse.json();if(model.dimensions?.mountHeight!==1.23||model.dimensions?.measuredMaximumExtendedHeight!==1.8||!model.drive)throw Error('This server has an older robot model. Restart Start-Rehearsal.ps1 and reload.');const initial=await shotResponse.json();if(initial.modelHash!==model.modelHash)throw Error("Robot model and shot do not match. Restart the local simulator.");buildRobot(model);buildFields(initial.settings);setShot(initial);registerTools();}catch(e){busy=false;$('loading').textContent='Unable to prepare rehearsal: '+e.message;console.error(e);}


$('driveProfile').onchange=()=>{dirty=true;state.playing=false;recalculate();};
$('steadyArc').onclick=()=>{
  if(busy)return;
  const track=+form.trackWidth.value,minimum=+form.minimumSpeed.value;
  const radius=2.5*track,duration=(+form.orbit.value*Math.PI/180)*track/(minimum*.5);
  if(radius>2.5||duration<2||duration>60){toast('This calibration is outside the steady-arc preset range.');return;}
  for(const [key,value] of Object.entries({radius,duration,armTravel:0,armLift:0,lightTravel:0,lightLift:0})){
    form[key].value=value;form[key].dispatchEvent(new Event('input'));
  }
  $('driveProfile').value='constant';recalculate();
};

$('armLed').onclick=()=>{
  if(busy)return;
  for(const [key,value] of Object.entries({radius:1.6,duration:9,dollyOffset:.4,armTravel:.16,armLift:.04,lightTravel:.12,lightLift:.03})){
    form[key].value=value;form[key].dispatchEvent(new Event('input'));
  }
  $('driveProfile').value='arms';recalculate();
};

$('robotPlanBtn').onclick=async()=>{
  if(!shot||busy||dirty||!shot.previewAvailable)return;
  if(shot.directJointMode){
    const url=URL.createObjectURL(new Blob([JSON.stringify(shot,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download=`takeone-direct-raw-${shot.planId}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    $('robotPlanStatus').textContent=`Downloaded ${shot.planId}: exact raw values for both arms at every 40 ms frame plus the constant forward cart packet. No IK.`;
    toast('Exact direct motor values downloaded.');
    return;
  }
  const reviewedShot=shot;
  $('robotPlanBtn').disabled=true;
  $('robotPlanStatus').textContent='Preparing the cart and both arm trajectories…';
  try{
    const response=reviewedRobotPlan?null:await fetch('/api/robot-plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({settings:reviewedShot.settings,shotId:reviewedShot.planId})});
    const result=reviewedRobotPlan?{plan:reviewedRobotPlan,preflight:{live_execution_allowed:false,blockers:['Run the offline CLI preflight for this exact artifact.']}}:await response.json();
    if(response&&!response.ok)throw new Error(result.error||'Robot plan could not be prepared.');
    if(shot!==reviewedShot||dirty)throw new Error('The preview changed. Review it and prepare again.');
    const url=URL.createObjectURL(new Blob([JSON.stringify(result.plan,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download=`takeone-robot-${result.plan.plan_id.slice(0,12)}.json`;link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    $('robotPlanStatus').textContent=`Plan ${result.plan.plan_id}. ${result.plan.duration_s}s; FK display steps at ${result.plan.arm_period_s*1000} ms. `+result.preflight.blockers.join('; ');
    toast('Robot motion plan downloaded. No motors were connected.');
  }catch(error){$('robotPlanStatus').textContent=error.message;}
  finally{$('robotPlanBtn').disabled=busy||dirty||!shot?.previewAvailable;}
};
$('reviewPlanFile').onchange=async event=>{
  const file=event.target.files[0];if(!file||busy)return;
  busy=true;state.playing=false;
  try{
    const plan=JSON.parse(await file.text());
    const response=await fetch('/api/review-plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan})});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'Plan cannot be reviewed.');
    const modelResponse=await fetch('/api/model?lightType='+encodeURIComponent(result.shot.settings.lightType)+'&trackWidth='+result.shot.settings.trackWidth);
    if(!modelResponse.ok)throw new Error('Model unavailable');
    model=await modelResponse.json();buildRobot(model);setShot(result.shot,result.plan);
    $('robotPlanStatus').textContent='Reviewing '+result.plan.plan_id+' · '+result.plan.duration_s+' seconds. '+result.preflight.blockers.join('; ');
  }catch(error){$('robotPlanStatus').textContent=error.message;}
  finally{busy=false;event.target.value='';}
};
