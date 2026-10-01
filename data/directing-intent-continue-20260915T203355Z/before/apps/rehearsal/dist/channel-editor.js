// Shared Shot Studio / Director editor. The server owns channel names and bounds.
const el=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
export const keyRamp=(a,b)=>[{at:0,value:a,ease:'smooth'},{at:1,value:b,ease:'smooth'}];
export function channelDefault(settings,name) {
  const target=settings.camera_target?.kind==='point'?settings.camera_target.position_m:[0,0,(settings.subject_height_m??1.72)*.925];
  const value={camera_height_m:settings.height_start_m??1.5,light_height_m:settings.light_height_start_m??1.6,
    pace_m_s:settings.speed_m_s??.17,camera_target_m:target,light_target_m:target,
    actor_position_m:[0,0,0],actor_heading_rad:settings.scene?.actor_heading_rad??0}[name]??0;
  const end={camera_height_m:settings.height_end_m,light_height_m:settings.light_height_end_m}[name]??value;
  return keyRamp(structuredClone(value),structuredClone(end));
}
export class ChannelEditor {
  constructor(container,settings,catalog,onChange,{moving=true}={}) {
    Object.assign(this,{container,settings,catalog,onChange,moving});
    settings.channels??={};settings.texture??={enabled:false,amplitude_rad:Math.PI/120,frequency_hz:.45};
    settings.breath??={pre_hold_s:0,post_hold_s:0,entry_s:0,exit_s:0};this.render();
  }
  number(parent,label,value,low,high,step,change) {
    const row=el('label',label),input=el('input');input.type='number';input.value=value;input.min=low;input.max=high;input.step=step;
    input.setAttribute('aria-label',label);input.onchange=()=>{if(input.value!==''&&input.checkValidity()){change(Number(input.value));this.onChange();}};
    row.append(input);parent.append(row);return input;
  }
  render() {
    this.container.replaceChildren();this.container.classList.add('channel-editor');
    const help=el('p','Each row has its own timing. Camera and light use filming time; pace uses route progress. Lens timing is in Camera & lens.');help.className='field-help';this.container.append(help);
    const texture=el('label','Organic drift on this movement '),toggle=el('input');toggle.type='checkbox';toggle.checked=this.settings.texture.enabled;
    toggle.setAttribute('aria-label','Organic drift on this movement');toggle.onchange=()=>{this.settings.texture.enabled=toggle.checked;this.onChange();};texture.append(toggle);this.container.append(texture);
    const amount=el('div');amount.className='channel-row';
    this.number(amount,'Drift amount · °',+(this.settings.texture.amplitude_rad*180/Math.PI).toFixed(3),0,5,.1,v=>this.settings.texture.amplitude_rad=v*Math.PI/180);
    this.number(amount,'Drift pace · Hz',this.settings.texture.frequency_hz,.1,1,.05,v=>this.settings.texture.frequency_hz=v);this.container.append(amount);
    const addRow=el('div');addRow.className='channel-row';const selector=el('select');selector.setAttribute('aria-label','Add independent channel');
    for(const [name,spec] of Object.entries(this.catalog||{}))if(!this.settings.channels[name]&&(this.moving||name!=='pace_m_s')){const option=el('option',spec.label);option.value=name;selector.append(option);}
    const add=el('button','Add channel');add.type='button';add.disabled=!selector.options.length;
    add.onclick=()=>{this.settings.channels[selector.value]=channelDefault(this.settings,selector.value);this.render();this.onChange();};addRow.append(selector,add);this.container.append(addRow);
    for(const [name,keys] of Object.entries(this.settings.channels))this.track(name,keys);
    if(this.moving){const breath=el('fieldset'),legend=el('legend','Cart breath');breath.append(legend);
      for(const [key,label] of Object.entries({pre_hold_s:'Opening hold · s',entry_s:'Ease into travel · s',exit_s:'Ease out of travel · s',post_hold_s:'Closing hold · s'}))this.number(breath,label,this.settings.breath[key]||0,0,10,.2,v=>this.settings.breath[key]=v);
      breath.append(el('p','The preview integrates quantized wheel commands. The motor deadband still produces a finite start and stop.'));this.container.append(breath);}
    this.container.append(el('p','Light position and aim are simulated. BR60 brightness and colour are set manually.'));
  }
  track(name,keys) {
    const spec=this.catalog?.[name];if(!spec)return;
    const track=el('fieldset'),legend=el('legend',spec.label),remove=el('button','Remove track');remove.type='button';remove.onclick=()=>{delete this.settings.channels[name];this.render();this.onChange();};legend.append(' ',remove);track.append(legend);
    const rail=el('div');rail.className='channel-rail';rail.setAttribute('aria-label',`${spec.label} key times`);
    for(const key of keys){const marker=el('span');marker.style.left=`${key.at*100}%`;marker.title=`${Math.round(key.at*100)}%`;rail.append(marker);}track.append(rail);
    const scale=spec.unit==='rad'?180/Math.PI:1,unit=spec.unit==='rad'?'°':spec.unit;
    keys.forEach((key,index)=>{
      const row=el('div');row.className='channel-key';const time=this.number(row,`${spec.label} key ${index+1} · %`,+(key.at*100).toFixed(3),0,100,.1,v=>{key.at=v/100;this.render();});time.disabled=index===0||index===keys.length-1;
      const values=Array.isArray(key.value)?key.value:[key.value];
      values.forEach((v,j)=>this.number(row,`${spec.dimensions===3?['X','Y','Z'][j]+' ':''}${spec.label} · ${unit}`,+(v*scale).toFixed(4),spec.minimum*scale,spec.maximum*scale,spec.unit==='rad'?.1:.01,n=>{if(spec.dimensions===3)key.value[j]=n/scale;else key.value=n/scale;}));
      const timing=el('select');timing.setAttribute('aria-label',`${spec.label} key ${index+1} easing`);
      for(const [value,label] of [['smooth','Ease smoothly'],['linear','Even change'],['hold','Hold until next key']]){const o=el('option',label);o.value=value;timing.append(o);}timing.value=key.ease;timing.onchange=()=>{key.ease=timing.value;this.onChange();};row.append(timing);
      if(index>0&&index<keys.length-1){const del=el('button','Remove key');del.type='button';del.onclick=()=>{keys.splice(index,1);this.render();this.onChange();};row.append(del);}track.append(row);
    });
    const add=el('button','Add a beat');add.type='button';add.disabled=keys.length>=32;add.onclick=()=>{let index=0;for(let i=1;i<keys.length-1;i++)if(keys[i+1].at-keys[i].at>keys[index+1].at-keys[index].at)index=i;const a=keys[index],b=keys[index+1];keys.splice(index+1,0,{at:(a.at+b.at)/2,value:structuredClone(a.value),ease:'smooth'});this.render();this.onChange();};track.append(add);this.container.append(track);
  }
}
