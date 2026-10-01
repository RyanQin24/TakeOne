import * as THREE from 'three';
import {opticalKeysFromPreview} from './choreography-review.js';

// An authoring tool: dragging edits requested keys, never the film camera.
export function opticalPathEditor({container,canvas,scene,camera,controls,getPreview,getSettings,onChange,onMessage,searchPlacements,applyPlacement}) {
  const root=new THREE.Group();root.layers.set(1);scene.add(root);
  const geometry=new THREE.SphereGeometry(.045,12,8),material=new THREE.MeshBasicMaterial({color:'#dd53c8',depthTest:false});
  const handles=[];
  const ray=new THREE.Raycaster();ray.layers.set(1);
  const pointer=new THREE.Vector2(),point=new THREE.Vector3();
  const plane=new THREE.Plane(new THREE.Vector3(0,0,1));
  const details=document.createElement('details'),summary=document.createElement('summary');
  summary.textContent='Optical path · achieved and requested';details.append(summary);container.append(details);
  const help=document.createElement('p');help.className='field-help';
  help.textContent='Cyan is achieved lens travel; magenta is the requested optical path. Seed three handles from achieved FK, edit XYZ or drag horizontally, then re-solve. Scene/actor marks and lens stay unchanged.';
  details.append(help);
  const seed=document.createElement('button');seed.type='button';seed.textContent='Seed start / middle / end from achieved camera';details.append(seed);
  const dragLabel=document.createElement('label'),toggle=document.createElement('input');toggle.type='checkbox';
  dragLabel.append(toggle,' Drag optical handles on their height planes');details.append(dragLabel);
  const fields=document.createElement('div');details.append(fields);
  const search=document.createElement('button');search.type='button';search.textContent='Compare base placements · up to 8 cm';
  const choices=document.createElement('div');details.append(search,choices);
  search.onclick=async()=>{
    if(!getPreview()||!keys().length)return onMessage('Compile an authored optical path first.');
    const identity=JSON.stringify(getSettings());search.disabled=true;choices.replaceChildren();
    try {
      const result=await searchPlacements();
      if(JSON.stringify(getSettings())!==identity)throw new Error('The shot changed during search; candidates were discarded.');
      for(const candidate of result.candidates){
        const row=document.createElement('p'),button=document.createElement('button');button.type='button';
        const error=candidate.max_position_error_m;
        row.textContent=`Base offset [${candidate.offset_m.join(', ')}] m · ${candidate.status.replaceAll('_',' ')} · ${error===undefined?'no geometry':(error*100).toFixed(1)+' cm optical error'} `;
        button.textContent='Apply this explicit placement';button.disabled=candidate.status==='unavailable';
        button.onclick=()=>{if(JSON.stringify(getSettings())!==identity)return onMessage('Shot changed; search again.');applyPlacement(candidate.settings);choices.replaceChildren();};
        row.append(button);choices.append(row);
      }
    }catch(error){onMessage(error.message);}finally{search.disabled=false;}
  };

  let dragging=null;
  const keys=()=>getSettings()?.channels?.camera_position_m||[];
  function refresh() {
    const settings=getSettings(),preview=getPreview();
    details.hidden=!settings;seed.disabled=!preview;
    handles.forEach(h=>{h.visible=false;});fields.replaceChildren();
    const values=keys();
    values.forEach((key,index)=>{
      if(!handles[index]){const h=new THREE.Mesh(geometry,material);h.layers.set(1);h.renderOrder=20;h.userData.keyIndex=index;root.add(h);handles.push(h);}
      handles[index].visible=true;handles[index].position.fromArray(key.value);
      const row=document.createElement('fieldset'),legend=document.createElement('legend');
      legend.textContent=`Optical handle ${index+1} · ${(key.at*100).toFixed(1)}% filmed time`;row.append(legend);
      ['X','Y','Z'].forEach((axis,i)=>{
        const label=document.createElement('label'),input=document.createElement('input');
        label.textContent=axis+' · m';input.type='number';input.step='.01';input.min=i===2?.7:-100;input.max=i===2?1.8:100;
        input.value=key.value[i];input.setAttribute('aria-label',`Optical handle ${index+1} ${axis}`);
        input.onchange=()=>{if(input.value!==''&&input.checkValidity()){key.value[i]=Number(input.value);onChange();}};
        label.append(input);row.append(label);
      });fields.append(row);
    });
  }
  seed.onclick=()=>{
    const settings=getSettings(),preview=getPreview();if(!settings||!preview)return;
    if(settings.channels?.camera_height_m)return onMessage('Remove the separate camera-height track before authoring an XYZ optical path.');
    settings.channels??={};settings.channels.camera_position_m=opticalKeysFromPreview(preview);
    onChange();refresh();
  };
  function aim(event) {
    const r=canvas.getBoundingClientRect();pointer.set((event.clientX-r.left)/r.width*2-1,1-(event.clientY-r.top)/r.height*2);
    ray.setFromCamera(pointer,camera);
  }
  canvas.addEventListener('pointerdown',event=>{
    if(!toggle.checked||event.button!==0||!getSettings())return;
    aim(event);const hit=ray.intersectObjects(handles.filter(h=>h.visible),false)[0];if(!hit)return;
    dragging=hit.object.userData.keyIndex;plane.constant=-keys()[dragging].value[2];
    controls.enabled=false;canvas.setPointerCapture(event.pointerId);event.preventDefault();event.stopImmediatePropagation();
  },true);
  canvas.addEventListener('pointermove',event=>{
    if(dragging===null)return;aim(event);
    if(ray.ray.intersectPlane(plane,point)){
      const key=keys()[dragging];if(key){key.value[0]=THREE.MathUtils.clamp(point.x,-100,100);key.value[1]=THREE.MathUtils.clamp(point.y,-100,100);handles[dragging].position.fromArray(key.value);controls.dispatchEvent({type:'change'});}
    }event.preventDefault();event.stopImmediatePropagation();
  },true);
  function finish(event) {
    if(dragging===null)return;dragging=null;controls.enabled=true;
    if(canvas.hasPointerCapture(event.pointerId))canvas.releasePointerCapture(event.pointerId);
    event.stopImmediatePropagation();refresh();onChange();
  }
  canvas.addEventListener('pointerup',finish,true);canvas.addEventListener('pointercancel',finish,true);
  return {refresh,hide(){root.visible=false;details.hidden=true;},show(){root.visible=true;refresh();}};
}
