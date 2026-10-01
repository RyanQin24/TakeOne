import * as THREE from 'three';

// One reusable figure. Distance drives gait, so scrubbing is deterministic.
export function createActor(scene) {
  const root=new THREE.Group();root.name='Actor';scene.add(root);
  const materials=Object.fromEntries(Object.entries({cloth:'#c07b54',pants:'#334945',skin:'#cfa783',hair:'#382f27',shoe:'#e2dcc7',eye:'#252c29'}).map(([k,color])=>[k,new THREE.MeshStandardMaterial({color,roughness:.8})]));
  const sphere=new THREE.SphereGeometry(1,16,12), capsule=new THREE.CapsuleGeometry(1,1,4,12), box=new THREE.BoxGeometry(1,1,1);
  const part=(parent,geo,color,pos,scale)=>{const m=new THREE.Mesh(geo,materials[color]);m.position.set(...pos);m.scale.set(...scale);m.castShadow=m.receiveShadow=true;parent.add(m);return m;};
  // Capsules are Y-up; scaled spheres and cylinders avoid rebuilding geometry.
  const bone=(parent,color,r,length)=>{const m=part(parent,capsule,color,[0,0,-length/2],[r,length/3,r]);m.rotation.x=Math.PI/2;return m;};
  part(root,sphere,'pants',[0,0,.85],[.14,.20,.13]);
  part(root,capsule,'cloth',[0,0,1.13],[.15,.20,.20]).rotation.x=Math.PI/2;
  part(root,sphere,'skin',[0,0,1.47],[.055,.055,.09]);
  const head=new THREE.Group();head.position.z=1.59;root.add(head);
  part(head,sphere,'skin',[0,0,0],[.109,.101,.134]);
  const hair=new THREE.SphereGeometry(1,16,10,0,Math.PI*2,0,Math.PI*.43);
  part(head,hair,'hair',[0,0,.02],[.12,.12,.12]).rotation.x=Math.PI/2;
  part(head,sphere,'skin',[.105,0,-.012],[.023,.014,.023]);
  for (const y of [-.038,.038]) part(head,sphere,'eye',[.103,y,.02],[.009,.009,.009]);
  const legs=[],arms=[];
  for (const side of [-1,1]) {
    const hip=new THREE.Group();hip.position.set(0,side*.105,.78);root.add(hip);bone(hip,'pants',.075,.36);
    const knee=new THREE.Group();knee.position.z=-.36;hip.add(knee);bone(knee,'pants',.065,.39);
    const foot=part(knee,box,'shoe',[.055,0,-.39],[.25,.14,.085]);legs.push({hip,knee,foot,side});
    const shoulder=new THREE.Group();shoulder.position.set(0,side*.215,1.34);root.add(shoulder);
    shoulder.rotation.x=side*.1;bone(shoulder,'cloth',.065,.29);
    const elbow=new THREE.Group();elbow.position.z=-.29;shoulder.add(elbow);elbow.rotation.y=-.1;bone(elbow,'cloth',.052,.25);
    part(elbow,sphere,'skin',[0,0,-.29],[.048,.043,.065]);arms.push({shoulder,side});
  }
  let stagedHeading=0;const nextPosition=new THREE.Vector3();
  const resting={position_m:[0,0,0],heading_rad:0,phase_rad:0,gait_weight:0,walking:false};
  return {root,stage(heading){stagedHeading=heading;},setHeight(height){root.scale.setScalar(height/1.72);},
    pose(a,b,mix) {
      a=a||{...resting,heading_rad:stagedHeading};
      b=b||a;
      root.position.fromArray(a.position_m).lerp(nextPosition.fromArray(b.position_m),mix);
      const turn=Math.atan2(Math.sin(b.heading_rad-a.heading_rad),Math.cos(b.heading_rad-a.heading_rad));
      root.rotation.z=a.heading_rad+turn*mix;
      head.rotation.z=THREE.MathUtils.lerp(a.gaze_yaw_rad||0,b.gaze_yaw_rad||0,mix);
      head.rotation.y=-THREE.MathUtils.lerp(a.gaze_pitch_rad||0,b.gaze_pitch_rad||0,mix);
      const phase=THREE.MathUtils.lerp(a.phase_rad,b.phase_rad,mix),weight=THREE.MathUtils.lerp(a.gait_weight,b.gait_weight,mix);
      for (const {hip,knee,foot,side} of legs) {
        const cycle=((phase/(2*Math.PI)+(side>0?.5:0))%1+1)%1;
        const swing=cycle<.6 ? 0 : (cycle-.6)/.4;
        const x=weight*(cycle<.6 ? .27-.9*cycle : -.27+.54*(swing*swing*(3-2*swing)));
        const z=-.71+weight*Math.sin(Math.PI*swing)*.09;
        const d=Math.min(.749,Math.hypot(x,z)),l1=.36,l2=.39;
        hip.rotation.y=-Math.atan2(x,-z)-Math.acos(THREE.MathUtils.clamp((l1*l1+d*d-l2*l2)/(2*l1*d),-1,1));
        knee.rotation.y=Math.PI-Math.acos(THREE.MathUtils.clamp((l1*l1+l2*l2-d*d)/(2*l1*l2),-1,1));
        foot.rotation.y=-hip.rotation.y-knee.rotation.y;
      }
      for (const {shoulder,side} of arms) shoulder.rotation.y=side*Math.sin(phase)*.28*weight;
    }};
}
