// The backend catalog owns template defaults and units. This is only its editor.
export class ShotLibrary {
  constructor({select, container, focal, onChange, onChoose=()=>{}}) {
    Object.assign(this,{select,container,focal,onChange,onChoose});
    this.entries = new Map();this.edits = new Map();this.settings = null;
  }
  install(catalog) {
    this.fields = catalog.fields;
    this.select.querySelector('option[value="template"]')?.remove();
    const groups = new Map();
    for (const entry of catalog.templates) {
      this.entries.set(entry.id,entry);
      if (!groups.has(entry.family)) {
        const group = document.createElement('optgroup');group.label = entry.family;
        this.select.append(group);groups.set(entry.family,group);
      }
      const option = document.createElement('option');option.value = 'template:'+entry.id;option.textContent = entry.name;
      groups.get(entry.family).append(option);
    }
    document.getElementById('libraryCount').textContent = `${catalog.templates.length} movement templates · 6 families`;
  }
  get entry() {return this.entries.get(this.settings?.template_id);}
  choose(id, values=null) {
    const entry = this.entries.get(id);
    if (!entry) throw new Error('Choose a movement from the library.');
    if (this.settings) this.edits.set(this.settings.template_id,structuredClone(this.settings));
    this.settings = {...structuredClone(entry.defaults),...(values || this.edits.get(id) || {})};
    this.select.value = 'template:'+id;this.focal.value = this.settings.focal_mm;this.render();
    this.onChoose(this.settings);
  }
  read() {return {...this.settings,focal_mm:+this.focal.value};}
  render() {
    const expanded=this.container.querySelector('.template-advanced')?.open ?? this.settings.subject_motion==='walk';
    this.container.replaceChildren();
    const intent = document.createElement('div');intent.className='shot-intent';
    const family = document.createElement('span');family.className='eyebrow';family.textContent=this.entry.family;
    const description=document.createElement('p');description.textContent=this.entry.intent;
    intent.append(family,description);this.container.append(intent);
    const main=document.createElement('div');main.className='template-fields';
    const advanced=document.createElement('details');advanced.className='template-advanced';
    advanced.open=expanded;
    const title=document.createElement('summary');title.textContent='Actor & light';advanced.append(title);
    const extras=document.createElement('div');extras.className='template-fields';advanced.append(extras);
    const motionLabel=document.createElement('label');motionLabel.className='template-subject';motionLabel.textContent='Actor movement';
    const motion=document.createElement('select');motion.id='subjectMotion';motion.setAttribute('aria-label','Actor movement');
    for (const [value,text] of [['hold','Stand still'],['walk','Walk along a path']]) {
      const option=document.createElement('option');option.value=value;option.textContent=text;motion.append(option);
    }
    motion.value=this.settings.subject_motion;motionLabel.append(motion);extras.append(motionLabel);
    motion.onchange=()=>{this.settings.subject_motion=motion.value;this.render();this.onChange();};
    for (const key of this.entry.parameters) {
      if (key.startsWith('actor_') && this.settings.subject_motion!=='walk') continue;
      const meta=this.fields[key];
      const label=document.createElement('label');label.textContent=`${meta.label}${meta.unit ? ' · '+meta.unit : ''}`;
      const input=document.createElement('input');input.type='number';input.id='template-'+key;input.dataset.parameter=key;
      input.min=meta.min;input.max=meta.max;input.step=meta.step;
      input.value=+(this.settings[key]*meta.scale).toFixed(5);input.setAttribute('aria-label',meta.label);
      input.oninput=()=>{this.settings[key]=+input.value/meta.scale;this.onChange();};
      label.append(input);
      (key.startsWith('actor_') || key.startsWith('light_') || key==='subject_height_m' ? extras : main).append(label);
    }
    this.container.append(main,advanced);
    const buttons=document.createElement('div');buttons.className='template-buttons';
    const reset=document.createElement('button');reset.type='button';reset.textContent='Reset preset';
    reset.onclick=()=>{this.choose(this.entry.id,this.entry.defaults);this.onChange();};
    const eyes=document.createElement('button');eyes.type='button';eyes.textContent='End at eye level';
    eyes.onclick=()=>{this.settings.height_end_m=Math.min(1.8,this.settings.subject_height_m*.925);this.render();this.onChange();};
    buttons.append(reset,eyes);this.container.append(buttons);
    const note=document.createElement('p');note.className='template-note';
    note.textContent=this.entry.route==='hold' ? 'Cart stays at its mark. Duration excludes calibrated arm setup. Begin / Finish set the change interval.' : 'Powered wheels lead along the ground route. Travel time follows the motor commands. Begin / Finish refer to the movement after setup.';
    this.container.append(note);
  }
}
