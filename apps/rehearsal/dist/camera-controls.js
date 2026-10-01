import {timecode} from './orbit-player.js';

export const defaultCamera = () => ({horizon:'auto', zoom:'preset', keyframes:[]});

export class CameraControls {
  constructor({container, focal, onChange}) {
    Object.assign(this,{container,focal,onChange});this.settings=defaultCamera();this.duration=null;
    this.render();
  }
  read() {return structuredClone(this.settings);}
  load(value) {this.settings={...defaultCamera(),...structuredClone(value || {})};this.render();}
  startingLensChanged() {
    if (this.settings.zoom==='keyframes' && this.settings.keyframes.length) {
      this.settings.keyframes[0].focal_mm=+this.focal.value;
      const first=this.container.querySelector('[data-starting-lens]');
      if (first && document.activeElement!==first) first.value=this.focal.value;
    }
  }
  setDuration(duration) {
    this.duration=duration;
    for (const label of this.container.querySelectorAll('[data-zoom-time]')) {
      label.textContent=duration===null ? 'After setup' : timecode(+label.dataset.zoomTime*duration);
    }
  }
  select(label, key, options) {
    const wrapper=document.createElement('label');wrapper.textContent=label;
    const select=document.createElement('select');select.setAttribute('aria-label',label);
    for (const [value,text] of options) {const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);}
    select.value=this.settings[key];wrapper.append(select);
    select.onchange=()=>{
      this.settings[key]=select.value;
      if (key==='zoom' && select.value==='keyframes' && !this.settings.keyframes.length) {
        const start=+this.focal.value;
        this.settings.keyframes=[{at:0,focal_mm:start,ease:'smooth'},{at:1,focal_mm:Math.min(360,start*2),ease:'smooth'}];
      }
      this.render();this.onChange();
    };
    return wrapper;
  }
  render() {
    this.container.replaceChildren();
    const modes=document.createElement('div');modes.className='camera-options';
    modes.append(this.select('Horizon','horizon',[
      ['auto','Auto · upright, except roll shots'],['level','Keep horizon level'],['phone','Follow the phone’s roll']
    ]),this.select('Lens movement','zoom',[
      ['preset','Use the movement preset'],['fixed','Keep one focal length'],['keyframes','Zoom over time'],['dolly','Dolly Zoom · keep subject size']
    ]));
    this.container.append(modes);
    const hint=document.createElement('p');hint.className='camera-option-note';
    hint.textContent='Upright output is a framing preview. The world view keeps the phone’s physical pose.';
    this.container.append(hint);
    if (this.settings.zoom==='keyframes') {
      const table=document.createElement('div');table.className='zoom-points';
      const header=document.createElement('div');header.className='zoom-point zoom-header';
      for (const text of ['Shot %','Lens · mm','To next point','']) {const cell=document.createElement('span');cell.textContent=text;header.append(cell);}
      table.append(header);
      this.settings.keyframes.forEach((point,index)=>{
        const row=document.createElement('div');row.className='zoom-point';
        const timeCell=document.createElement('div');
        const at=document.createElement('input');at.type='number';at.min=0;at.max=100;at.step=.1;at.value=+(point.at*100).toFixed(3);
        at.setAttribute('aria-label',`Zoom point ${index+1} at percent`);at.disabled=index===0 || index===this.settings.keyframes.length-1;
        const seconds=document.createElement('small');seconds.dataset.zoomTime=point.at;
        timeCell.append(at,seconds);
        at.oninput=()=>{point.at=+at.value/100;seconds.dataset.zoomTime=point.at;this.setDuration(this.duration);this.onChange();};
        const focal=document.createElement('input');focal.type='number';focal.min=13;focal.max=360;focal.step=1;focal.value=point.focal_mm;
        focal.setAttribute('aria-label',`Zoom point ${index+1} focal length`);
        if(index===0) focal.dataset.startingLens='true';
        focal.oninput=()=>{point.focal_mm=+focal.value;if(index===0)this.focal.value=focal.value;this.onChange();};
        const ease=document.createElement('select');ease.setAttribute('aria-label',`Zoom point ${index+1} transition`);
        for(const [value,text] of [['smooth','Ease'],['linear','Linear'],['hold','Hold, then cut']]) {const option=document.createElement('option');option.value=value;option.textContent=text;ease.append(option);}
        ease.value=point.ease;ease.disabled=index===this.settings.keyframes.length-1;
        ease.onchange=()=>{point.ease=ease.value;this.onChange();};
        const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.setAttribute('aria-label',`Remove zoom point ${index+1}`);
        remove.disabled=index===0 || index===this.settings.keyframes.length-1;
        remove.onclick=()=>{this.settings.keyframes.splice(index,1);this.render();this.onChange();};
        row.append(timeCell,focal,ease,remove);table.append(row);
      });
      this.container.append(table);
      const add=document.createElement('button');add.type='button';add.textContent='+ Add zoom point';add.disabled=this.settings.keyframes.length>=32;
      add.onclick=()=>{
        const points=this.settings.keyframes;let index=0;
        for(let i=1;i<points.length-1;i++) if(points[i+1].at-points[i].at>points[index+1].at-points[index].at)index=i;
        const a=points[index],b=points[index+1];
        points.splice(index+1,0,{at:(a.at+b.at)/2,focal_mm:(a.focal_mm+b.focal_mm)/2,ease:'smooth'});
        this.render();this.onChange();
      };
      this.container.append(add);
      const note=document.createElement('p');note.className='camera-option-note';
      note.textContent='Times begin after arm setup. Equal lens values hold the zoom. Add points for zoom in → hold → zoom out.';
      this.container.append(note);
    } else if (this.settings.zoom==='dolly') {
      const note=document.createElement('p');note.className='camera-option-note';
      note.textContent='The lens follows camera-to-actor depth. Moving closer widens the lens; moving away tightens it.';
      this.container.append(note);
    }
    this.setDuration(this.duration);
  }
}
