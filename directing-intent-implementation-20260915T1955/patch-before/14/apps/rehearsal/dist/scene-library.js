import * as THREE from 'three';
import {createActor} from './walking-actor.js?v=placement-01';
import {createImportedSet} from './asset-library/imported-set.js';

const palettes = {
  exterior_day:['#c6d4dc','#b7b9ad','#fff4d6'], exterior_dusk:['#727f9f','#88828b','#ffc28d'],
  interior_day:['#d0d8dc','#b8b8b1','#f6f1db'], interior_warm:['#aaa7a4','#8e8780','#ffdba5'],
  exterior_night:['#1c2a45','#424958','#94b5e5'], interior_cool:['#9baebc','#7a8893','#b5d9ec'],
  studio:['#c4ccbf','#a6b5a2','#f2f7ee']
};

export function createSceneLibrary(scene, ground, sun) {
  const root = new THREE.Group(); scene.add(root);
  const cast = new Map();
  const imported = createImportedSet(scene);
  const box = (parent,size,pos,color) => {
    const mesh=new THREE.Mesh(new THREE.BoxGeometry(...size),new THREE.MeshStandardMaterial({color,roughness:.78}));
    mesh.position.set(...pos);mesh.castShadow=true;mesh.receiveShadow=true;parent.add(mesh);return mesh;
  };
  function label(parent,text,width,height) {
    if (!text) return;
    const canvas=document.createElement('canvas');canvas.width=1024;canvas.height=256;
    const ctx=canvas.getContext('2d');ctx.fillStyle='#152b39';ctx.fillRect(0,0,1024,256);
    ctx.fillStyle='#fff4da';ctx.textAlign='center';ctx.textBaseline='middle';ctx.font='bold 82px sans-serif';
    ctx.fillText(text,512,128,960);
    const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;
    const panel=new THREE.Mesh(new THREE.PlaneGeometry(width,height),new THREE.MeshBasicMaterial({map:texture,side:THREE.DoubleSide}));
    panel.rotation.x=Math.PI/2;panel.position.y=-.075;parent.add(panel);
  }
  function clear() {
    imported.clear();
    root.traverse(o=>{o.geometry?.dispose();for(const m of [].concat(o.material||[])){m.map?.dispose();m.dispose();}});
    root.clear();cast.clear();
  }
  function load(definition, actors=[]) {
    clear();const env=definition||{atmosphere:'studio',objects:[],cast:[]};
    imported.load(env.objects||[]);
    const [sky,floor,key]=palettes[env.atmosphere]||palettes.studio;
    scene.background.set(sky);ground.material.color.set(floor);sun.color.set(key);
    sun.intensity=env.atmosphere?.startsWith('interior')?1.6:2.6;
    for(const object of env.objects||[]) {
      if(object.asset_id.startsWith('lib:'))continue;
      const group=new THREE.Group();group.position.fromArray(object.position_m);group.rotation.z=object.yaw_rad||0;root.add(group);
      const [w,d,h]=object.size_m, type=object.asset_id;
      if(type==='product') {
        const material=new THREE.MeshStandardMaterial({color:'#428b83',metalness:.55,roughness:.2});
        const bottle=new THREE.Mesh(new THREE.CylinderGeometry(w*.42,w*.5,h*.83,40),material);bottle.rotation.x=Math.PI/2;bottle.position.z=-h*.06;bottle.castShadow=true;group.add(bottle);
        const cap=new THREE.Mesh(new THREE.CylinderGeometry(w*.29,w*.29,h*.18,32),new THREE.MeshStandardMaterial({color:'#d9c9a5',metalness:.7,roughness:.24}));cap.rotation.x=Math.PI/2;cap.position.z=h*.41;group.add(cap);
        const band=box(group,[w*.55,d*.04,h*.28],[0,-d*.495,-h*.06],'#eee8d9');band.material.roughness=.4;
      } else if(type==='doorway'||type==='arch') {
        box(group,[w*.12,d,h],[-w*.44,0,0],'#49606b');box(group,[w*.12,d,h],[w*.44,0,0],'#49606b');
        box(group,[w,d,h*.1],[0,0,h*.45],'#49606b');
      } else if(type==='sofa') {
        box(group,[w,d,h*.45],[0,0,-h*.275],'#777383');
        box(group,[w,d*.22,h*.7],[0,d*.39,h*.15],'#777383');
        for(const x of [-.45,.45])box(group,[w*.1,d,h*.65],[x*w,0,-h*.05],'#676775');
      } else if(type==='shelf') {
        for(const x of [-.46,.46])box(group,[w*.08,d,h],[x*w,0,0],'#8b765c');
        for(const z of [-.46,-.15,.16,.46])box(group,[w,d,h*.04],[0,0,z*h],'#ab9477');
      } else if(type==='counter') {
        box(group,[w,d,h],[0,0,0],'#81755f');
        box(group,[w*1.04,d*1.08,.06],[0,0,h*.5],'#d1c4ac');
      } else if(type==='screen') {
        box(group,[w,d*.4,h],[0,0,0],'#677d80');
        for(const x of [-.35,.35])box(group,[w*.2,d*2,.04],[w*x,0,-h*.5],'#3d464c');
      } else if(type==='rock') {
        const mesh=new THREE.Mesh(new THREE.DodecahedronGeometry(1,0),new THREE.MeshStandardMaterial({color:'#8a887e',roughness:1}));
        mesh.scale.set(w*.5,d*.5,h*.5);mesh.castShadow=mesh.receiveShadow=true;group.add(mesh);
      } else if(type==='table'||type==='bench') {
        box(group,[w,d,.09],[0,0,h/2-.045],type==='table'?'#ae8058':'#806746');
        for(const x of [-.42,.42])for(const y of [-.38,.38])box(group,[.07,.07,h-.09],[x*w,y*d,-.045],'#38434a');
      } else if(type==='chair') {
        box(group,[w,d,.08],[0,0,0],'#4a7580');box(group,[w,.08,h*.5],[0,d*.45,h*.25],'#4a7580');
        for(const x of [-.4,.4])for(const y of [-.4,.4])box(group,[.04,.04,h*.5],[x*w,y*d,-h*.25],'#39424a');
      } else if(type==='tree'||type==='planter') {
        box(group,[w*.35,d*.35,h*.6],[0,0,-h*.2],type==='tree'?'#73614b':'#b39c80');
        const crown=new THREE.Mesh(new THREE.SphereGeometry(1,12,8),new THREE.MeshStandardMaterial({color:'#496a54'}));
        crown.scale.set(w/2,d/2,h*.32);crown.position.z=h*.18;group.add(crown);
      } else if(type==='laptop') {
        box(group,[w,d,.025],[0,0,-h/2+.013],'#555e68');box(group,[w,.02,h],[0,d*.4,0],'#283342');
        box(group,[w*.88,.023,h*.8],[0,d*.4-.015,0],'#80c6c8');
      } else if(type==='practical_light') {
        box(group,[.04,.04,h],[0,0,0],'#403d3c');box(group,[w,d,h*.2],[0,0,h*.4],'#ffe0a9');
      } else {
        const color=type==='sign'?'#193545':type==='window'?'#88acbe':type==='bollard'?'#555d64':'#c3bbaa';
        box(group,[w,d,h],[0,0,0],color);
        if(type==='facade')for(const x of [-.3,0,.3])box(group,[w*.18,d+.02,h*.43],[w*x,-.025,h*.1],'#6e98a9');
      }
      if(object.label&&(type==='sign'||type==='doorway')) {
        const holder=new THREE.Group();holder.position.set(0,-d/2-.01,type==='doorway'?h*.38:0);group.add(holder);
        label(holder,object.label,w*.9,type==='doorway'?h*.18:h*.9);
      }
    }
    for(const member of env.cast||[]) {
      const figure=createActor(root);figure.setHeight(1.72);
      figure.setAppearance(actors.find(a=>a.actor_id===member.actor_id)?.appearance);
      figure.root.userData.actorId=member.actor_id;cast.set(member.actor_id,{member,figure});
    }
  }
  function pose(a,b,mix,leadId,origin=[0,0]) {
    for(const [id,{member,figure}] of cast) {
      figure.root.visible=id!==leadId;
      const place=f=>({...f,position_m:member.offset_m.map((v,i)=>v+(member.motion==='with_lead'?(f?.position_m?.[i]||0):(i<2?origin[i]:0))),
        heading_rad:member.motion==='with_lead'?(f?.heading_rad||0):member.facing_rad,
        gaze_yaw_rad:0,gaze_pitch_rad:0,
        phase_rad:f?.phase_rad||0,gait_weight:member.motion==='with_lead'?(f?.gait_weight||0):0});
      figure.pose(place(a),place(b),mix);
    }
  }
  // The current scene contract shares one stature with the framing solver.
  function setHeight(height) {for(const {figure} of cast.values())figure.setHeight(height);}
  return {load,pose,setHeight,root,imported};
}
