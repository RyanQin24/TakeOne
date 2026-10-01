import * as THREE from 'three';

// One geometry path for the simulator and downloadable GLB models.
export function createRobot(data) {
  const root=new THREE.Group();root.name='TAKE_ONE_front_phone_rear_'+data.lightType;
  root.userData={source:data.source,dimensions:data.dimensions,layout:data.layout,modelHash:data.modelHash};
  const bodyGroups=data.bodyNames.map(name=>{const group=new THREE.Group();group.name=name||'world';root.add(group);return group;});
  const geometries={};
  for(const [id,m] of Object.entries(data.meshes)){
    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(m.vertices,3));g.setIndex(m.faces);g.computeVertexNormals();geometries[id]=g;
  }
  for(const g of data.geoms){
    let geometry;
    if(g.kind===7)geometry=geometries[g.mesh];
    else if(g.kind===6)geometry=new THREE.BoxGeometry(...g.size.map(x=>2*x));
    else if(g.kind===5){geometry=new THREE.CylinderGeometry(g.size[0],g.size[0],2*g.size[1],32);geometry.rotateX(Math.PI/2);}
    else if(g.kind===2)geometry=new THREE.SphereGeometry(g.size[0],24,16);
    else continue;
    const color=new THREE.Color().setRGB(...g.color.slice(0,3));
    const emitter=g.name==='light_emitter'||g.name==='status_led';
    const material=new THREE.MeshStandardMaterial({color,roughness:.58,metalness:.16,
      transparent:g.color[3]<1,opacity:g.color[3],depthWrite:g.color[3]>=1,
      emissive:emitter?color:0,emissiveIntensity:emitter?1.8:0});
    const object=new THREE.Mesh(geometry,material);object.name=g.name;
    object.position.fromArray(g.pos);object.quaternion.fromArray(g.quat);
    object.castShadow=!emitter&&g.color[3]>=1;object.receiveShadow=true;
    bodyGroups[g.body].add(object);
  }
  return {root,bodyGroups};
}

export function poseRobot(bodyGroups,frame) {
  bodyGroups.forEach((group,i)=>{
    group.position.fromArray(frame.bodies[i]);group.quaternion.fromArray(frame.bodies[i].slice(3));
  });
}

export function animateDrive(bodyGroups,frame) {
  if(!frame.drive)return;
  const {wheelAngles,wheelAxisSign}=frame.drive;
  for(const [i,side] of ['left','right'].entries()){
    const wheel=bodyGroups.find(g=>g.name==='drive_'+side);
    // The wheel's local axle and drive-forward frame determine the rolling sign.
    wheel?.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(wheelAxisSign,0,0),wheelAngles[i]));
    const caster=bodyGroups.find(g=>g.name==='caster_'+side);
    if(caster)caster.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),frame.drive.casterYaw[i]));
  }
}

export function disposeRobot(root) {
  const geometries=new Set(),materials=new Set();
  root.traverse(o=>{if(o.geometry)geometries.add(o.geometry);if(o.material)materials.add(o.material);});
  geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());
  root.removeFromParent();
}
