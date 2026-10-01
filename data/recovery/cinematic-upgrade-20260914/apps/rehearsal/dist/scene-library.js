import * as THREE from 'three';
import {createActor} from './walking-actor.js?v=placement-01';

const palettes = {
  exterior_day:['#c6d4dc','#b7b9ad','#fff4d6'], exterior_dusk:['#727f9f','#88828b','#ffc28d'],
  interior_day:['#d0d8dc','#b8b8b1','#f6f1db'], interior_warm:['#aaa7a4','#8e8780','#ffdba5'],
  studio:['#c4ccbf','#a6b5a2','#f2f7ee']
};

export function createSceneLibrary(scene, ground, sun) {
  const root = new THREE.Group(); scene.add(root);
  const cast = new Map();
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
    root.traverse(o=>{o.geometry?.dispose();for(const m of [].concat(o.material||[])){m.map?.dispose();m.dispose();}});
    root.clear();cast.clear();
  }
  function load(definition) {
    clear();const env=definition||{atmosphere:'studio',objects:[],cast:[]};
    const [sky,floor,key]=palettes[env.atmosphere]||palettes.studio;
    scene.background.set(sky);ground.material.color.set(floor);sun.color.set(key);
    sun.intensity=env.atmosphere?.startsWith('interior')?1.6:2.6;
    for(const object of env.objects||[]) {
      const group=new THREE.Group();group.position.fromArray(object.position_m);group.rotation.z=object.yaw_rad||0;root.add(group);
      const [w,d,h]=object.size_m, type=object.asset_id;
      if(type==='doorway') {
        box(group,[w*.12,d,h],[-w*.44,0,0],'#49606b');box(group,[w*.12,d,h],[w*.44,0,0],'#49606b');
        box(group,[w,d,h*.1],[0,0,h*.45],'#49606b');
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
    for(const member of env.cast||[]) {const figure=createActor(root);figure.setHeight(1.72);cast.set(member.actor_id,{member,figure});}
  }
  function pose(a,b,mix,leadId,origin=[0,0]) {
    for(const [id,{member,figure}] of cast) {
      figure.root.visible=id!==leadId;
      const place=f=>({...f,position_m:member.offset_m.map((v,i)=>v+(member.motion==='with_lead'?(f?.position_m?.[i]||0):(i<2?origin[i]:0))),
        heading_rad:member.motion==='with_lead'?(f?.heading_rad||0):member.facing_rad,
        phase_rad:f?.phase_rad||0,gait_weight:member.motion==='with_lead'?(f?.gait_weight||0):0});
      figure.pose(place(a),place(b),mix);
    }
  }
  return {load,pose,root};
}
