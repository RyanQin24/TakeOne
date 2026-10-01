/* TAKE ONE UX-01
   Vanilla adaptation of interaction behavior studied from Spectrum UI's public
   registry sources. See ../vendor/spectrum/*.json for exact upstream snapshots.
   We intentionally keep Three.js/robot/camera loops outside this layer. */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

function esc(value = '') {
  const node = document.createElement('span');
  node.textContent = String(value);
  return node.innerHTML;
}

function closeOverlay(node) {
  if (!node) return;
  const returnFocus = node.__returnFocus;
  node.remove();
  if (returnFocus?.focus) returnFocus.focus();
}

function installCommandPalette() {
  const items = () => {
    const base = [
      {group:'Workflow', label:'Director', run:()=>location.href='/director.html'},
      {group:'Workflow', label:'World', detail:'AI production design · semantic 3D scene', run:()=>location.href='/world.html'},
      {group:'Workflow', label:'Shot Studio', run:()=>location.href='/'},
      {group:'Workflow', label:'Record', run:()=>location.href='/record.html'},
      {group:'Tools', label:'Voice rehearsal', run:()=>location.href='/voice.html'},
      {group:'Tools', label:'Motor Lab', run:()=>location.href='/motor-test.html'},
      {group:'Tools', label:'Motion Proof', run:()=>location.href='/drive-proof.html'},
    ];
    if(document.body.dataset.t1Page==='world') base.push(
      {group:'Production design',label:'Generate world',detail:'Retrieve assets and solve a semantic layout',run:()=>document.dispatchEvent(new Event('takeone:generate-world'))},
      {group:'Production design',label:'Find 3D model',detail:'Search the complete installed local catalog',run:()=>$('#pdAddAsset')?.click()},
    );
    const shots = $$('.rail-row').filter(node => !node.disabled).map((node, index) => ({
      group:'Current film',
      label:(node.querySelector('strong')?.textContent || `Shot ${index + 1}`).trim(),
      detail:node.querySelector('small')?.textContent?.trim() || '',
      run:()=>node.click(),
    }));
    return [...base, ...shots];
  };
  const open = () => {
    if ($('.t1-command-backdrop')) return;
    const backdrop = document.createElement('div');
    backdrop.className = 't1-command-backdrop';
    backdrop.setAttribute('role', 'presentation');
    backdrop.__returnFocus = document.activeElement;
    backdrop.innerHTML = `<section class="t1-command" role="dialog" aria-modal="true" aria-label="Take One command search">
      <div class="t1-command__head"><span aria-hidden="true">⌕</span><input aria-label="Search Take One" placeholder="Search scenes, shots, tools…"><span class="t1-command__key">ESC</span></div>
      <div class="t1-command__results" role="listbox"></div></section>`;
    document.body.append(backdrop);
    const input = $('input', backdrop), results = $('.t1-command__results', backdrop);
    let active = 0, visible = [];
    const render = () => {
      const q = input.value.trim().toLowerCase();
      visible = items().filter(item => `${item.label} ${item.detail || ''}`.toLowerCase().includes(q));
      active = Math.min(active, Math.max(0, visible.length - 1));
      let lastGroup = '';
      results.innerHTML = visible.map((item, i) => {
        const group = item.group !== lastGroup ? `<div class="t1-command__group">${esc(item.group)}</div>` : '';
        lastGroup = item.group;
        return `${group}<button class="t1-command__item" role="option" aria-selected="${i === active}" data-index="${i}"><span><b>${esc(item.label)}</b>${item.detail ? `<small>${esc(item.detail)}</small>` : ''}</span></button>`;
      }).join('') || `<div class="t1-command__empty">No matching command</div>`;
      $$('.t1-command__item', results).forEach(btn => btn.onclick = () => { const item=visible[Number(btn.dataset.index)]; closeOverlay(backdrop); item?.run(); });
    };
    input.oninput = render;
    input.onkeydown = (event) => {
      if (event.key === 'ArrowDown') { event.preventDefault(); active = Math.min(active + 1, visible.length - 1); render(); }
      if (event.key === 'ArrowUp') { event.preventDefault(); active = Math.max(active - 1, 0); render(); }
      if (event.key === 'Enter' && visible[active]) { event.preventDefault(); const item=visible[active]; closeOverlay(backdrop); item.run(); }
    };
    backdrop.onmousedown = event => { if (event.target === backdrop) closeOverlay(backdrop); };
    render(); input.focus();
  };
  document.addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); open(); }
    if (event.key === 'Escape') closeOverlay($('.t1-command-backdrop'));
  });
  document.addEventListener('takeone:open-command', open);
}

function openDetailsDrawer(source) {
  if (!source || $('.t1-drawer-backdrop')) return;
  const backdrop = document.createElement('div');
  backdrop.className = 't1-drawer-backdrop';
  backdrop.__returnFocus = document.activeElement;
  backdrop.innerHTML = `<aside class="t1-drawer" role="dialog" aria-modal="true" aria-label="Production details">
    <div class="t1-drawer__head"><h2>Production details</h2><button class="t1-drawer__close" aria-label="Close production details">×</button></div>
    <div class="t1-drawer__body"></div></aside>`;
  $('.t1-drawer__body', backdrop).append(source.cloneNode(true));
  document.body.append(backdrop);
  $('.t1-drawer__close', backdrop).onclick = () => closeOverlay(backdrop);
  backdrop.onmousedown = event => { if (event.target === backdrop) closeOverlay(backdrop); };
  $('.t1-drawer__close', backdrop).focus();
}

/* The Director film engine — an animated camera, parallax reels and a kinetic
 * headline — was removed with the rest of the costume in the design-system
 * pass. Nothing in it carried information. */

function humanTitle(value='') {
  return String(value).replace(/\s+-\s+\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\s*$/, '').trim();
}

function installDirectorDisplayPolish() {
  if (document.body.dataset.t1Page !== 'director') return;
  const applyTitles = () => {
    for (const node of $$('#projectTitle,#breadcrumb,.session-item strong')) {
      const next = humanTitle(node.textContent);
      if (next && next !== node.textContent) node.textContent = next;
    }
  };
  applyTitles();
  for (const root of [$('#projectTitle'), $('#breadcrumb'), $('#sessionList')].filter(Boolean)) {
    new MutationObserver(applyTitles).observe(root, {childList:true,subtree:true,characterData:true});
  }

  const blocks = [$('.starters-heading'), $('.starters'), $('.t1-rail'), $('.home-footer')].filter(Boolean);
  blocks.forEach((node,index)=>{node.classList.add('t1-story-block');node.style.setProperty('--story-index',String(index));});
  document.body.classList.add('t1-story-ready');
  if (reduceMotion || !('IntersectionObserver' in window)) {
    blocks.forEach(node=>node.dataset.storyVisible='1');
    return;
  }
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.dataset.storyVisible='1';
      observer.unobserve(entry.target);
    }
  }, {threshold:.12, rootMargin:'0px 0px -8% 0px'});
  blocks.forEach(node=>observer.observe(node));
}

function installDirectorProgressiveDisclosure() {
  if (document.body.dataset.t1Page !== 'director') return;
  const tabs = ['brief', 'script', 'shots'];
  const sync = () => {
    const active = tabs.find(name => $(`#${name}Tab`)?.getAttribute('aria-selected') === 'true') || 'brief';
    document.body.dataset.directorTab = active;
  };
  tabs.forEach(name => {
    const tab = $(`#${name}Tab`);
    tab?.addEventListener('click', () => requestAnimationFrame(sync));
    if (tab) new MutationObserver(sync).observe(tab, {attributes:true, attributeFilter:['aria-selected']});
  });
  const nav = $('.document-actions');
  const inspector = $('.editor-layout > .inspector');
  if (nav && inspector && !$('.t1-details-trigger', nav)) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'quiet-button t1-details-trigger';
    button.textContent = 'Details';
    button.onclick = () => openDetailsDrawer(inspector);
    nav.prepend(button);
  }
  sync();
}

let studioDrawerApi = null;
function createStudioDrawer() {
  if (studioDrawerApi || document.body.dataset.t1Page !== 'studio') return studioDrawerApi;
  const scene = $('#sceneContext');
  const cameraColumn = $('.camera-column');
  if (!scene || !cameraColumn) return null;
  const backdrop = document.createElement('div');
  backdrop.className = 't1-studio-drawer-backdrop';
  backdrop.hidden = true;
  backdrop.innerHTML = `<aside class="t1-studio-drawer" role="dialog" aria-modal="true" aria-labelledby="t1StudioDrawerTitle">
    <div class="t1-studio-drawer__head"><div><span class="t1-eyebrow">SHOT STUDIO</span><h2 id="t1StudioDrawerTitle">Inspector</h2></div><button type="button" class="t1-studio-drawer__close" aria-label="Close inspector">×</button></div>
    <div class="t1-studio-drawer__panel" data-panel="scene"></div><div class="t1-studio-drawer__panel" data-panel="inspect"></div><div class="t1-studio-drawer__panel" data-panel="library"></div></aside>`;
  document.body.append(backdrop);
  const scenePanel = $('[data-panel="scene"]', backdrop), inspectPanel = $('[data-panel="inspect"]', backdrop), libraryPanel = $('[data-panel="library"]', backdrop);
  scenePanel.append(scene);
  const technical = [
    $('.shot-readings'), $('.tracking-card'), $('#notes'), $('#choreographyReadout'),
    $('.joint-details'), $('.grid-toggle'), $('#cameraControls'), $('.phone-scope'), $('#outputView')?.closest('label')
  ].filter(Boolean);
  technical.forEach(node => inspectPanel.append(node));
  let returnFocus = null;
  const close = () => {
    backdrop.hidden = true;
    document.body.classList.remove('t1-drawer-open');
    if (returnFocus?.focus) returnFocus.focus();
  };
  const open = (mode='inspect') => {
    returnFocus = document.activeElement;
    scenePanel.hidden = mode !== 'scene'; inspectPanel.hidden = mode !== 'inspect'; libraryPanel.hidden = mode !== 'library';
    $('#t1StudioDrawerTitle', backdrop).textContent = mode === 'scene' ? 'Scene & performance' : mode === 'library' ? 'Shot types' : 'Shot inspector';
    backdrop.hidden = false; document.body.classList.add('t1-drawer-open');
    $('.t1-studio-drawer__close', backdrop).focus();
  };
  $('.t1-studio-drawer__close', backdrop).onclick = close;
  backdrop.onmousedown = event => { if (event.target === backdrop) close(); };
  backdrop.addEventListener('keydown', event => {
    if (event.key === 'Escape') { close(); return; }
    if (event.key !== 'Tab') return;
    const nodes = $$('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary', backdrop).filter(node => node.offsetParent !== null);
    if (!nodes.length) return;
    const first=nodes[0],last=nodes.at(-1);
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
  });
  studioDrawerApi = {open, close, backdrop};
  return studioDrawerApi;
}

async function installMovementLibrary(drawer) {
  if (document.body.dataset.t1Page !== 'studio' || !drawer) return;
  const panel = $('[data-panel="library"]', drawer.backdrop);
  if (!panel || panel.dataset.ready) return;
  panel.dataset.ready = 'loading';
  panel.innerHTML = `<div class="t1-library-intro"><p>Explore every camera move the rig can rehearse. Choosing a shot type opens it as a temporary movement study; your Director film is not rewritten.</p><label><span>Find a shot type</span><input type="search" data-shot-search placeholder="Orbit, tracking, product, dolly…" autocomplete="off"></label><button type="button" class="secondary" data-return-film hidden>← Return to Director film</button></div><div class="t1-movement-groups" role="list" aria-label="Camera movement library"><p class="t1-library-loading">Reading movement library…</p></div>`;
  const hasScript = new URLSearchParams(location.search).has('script');
  const returnFilm = $('[data-return-film]', panel);
  const syncReturn = () => { returnFilm.hidden = !hasScript || $('#moveMode')?.value === 'sequence'; };
  returnFilm.onclick = () => {
    const mode=$('#moveMode'); if(!mode?.querySelector('option[value="sequence"]')) return;
    mode.disabled=false; mode.value='sequence'; mode.dispatchEvent(new Event('change',{bubbles:true})); drawer.close();
  };
  try {
    const response=await fetch('/api/previs/templates',{cache:'no-store'});
    if(!response.ok) throw new Error(`Movement library ${response.status}`);
    const catalog=await response.json();
    const groups=new Map();
    for(const item of catalog.templates||[]){if(!groups.has(item.family))groups.set(item.family,[]);groups.get(item.family).push(item);}
    const root=$('.t1-movement-groups',panel);root.replaceChildren();
    for(const [family,items] of groups){
      const section=document.createElement('section');section.className='t1-movement-family';section.dataset.family=family.toLowerCase();
      section.innerHTML=`<div class="t1-movement-family__head"><h3>${esc(family)}</h3><span>${items.length}</span></div><div class="t1-movement-family__list"></div>`;
      const list=$('.t1-movement-family__list',section);
      for(const item of items){
        const button=document.createElement('button');button.type='button';button.className='t1-movement-choice';button.dataset.template=item.id;button.dataset.search=`${family} ${item.name} ${item.intent}`.toLowerCase();
        button.innerHTML=`<span><strong>${esc(item.name)}</strong><small>${esc(item.intent)}</small></span><em>Preview move</em>`;
        button.onclick=()=>{
          const mode=$('#moveMode'); if(!mode)return;
          mode.disabled=false; mode.value=`template:${item.id}`; mode.dispatchEvent(new Event('change',{bubbles:true}));
          drawer.close(); requestAnimationFrame(()=>$('#worldPanel')?.scrollIntoView({block:'nearest'}));
        };
        list.append(button);
      }
      root.append(section);
    }
    const search=$('[data-shot-search]',panel);
    search.oninput=()=>{
      const q=search.value.trim().toLowerCase();
      $$('.t1-movement-choice',panel).forEach(button=>button.hidden=!!q&&!button.dataset.search.includes(q));
      $$('.t1-movement-family',panel).forEach(section=>section.hidden=!$$('.t1-movement-choice',section).some(button=>!button.hidden));
    };
    panel.dataset.ready='1';
    panel.dataset.count=String(catalog.templates?.length||0);
    const button=$('[data-t1-library]'); if(button) button.textContent=`Shot types · ${catalog.templates?.length||0}`;
    $('#moveMode')?.addEventListener('change',syncReturn);
    new MutationObserver(syncReturn).observe(document.body,{attributes:true,attributeFilter:['data-sequence']});
    syncReturn();
  } catch(error) {
    panel.dataset.ready='error';
    $('.t1-movement-groups',panel).innerHTML=`<p class="t1-library-error">${esc(error.message)}. Retry after the local rehearsal service is available.</p>`;
  }
}

function installStudioNavigator() {
  if (document.body.dataset.t1Page !== 'studio') return;
  const rail = $('#shotRail'), workspace = $('.workspace-body');
  if (!rail || !workspace || $('.t1-shot-navigator')) return;
  const nav = document.createElement('nav');
  nav.className = 't1-shot-navigator'; nav.setAttribute('aria-label','Scenes and shots');
  nav.innerHTML = `<div class="t1-shot-navigator__head"><span><small>FILM</small><strong>Scenes & shots</strong></span><button type="button" aria-expanded="true" aria-label="Collapse shot navigator">‹</button></div>`;
  nav.append(rail); workspace.append(nav);
  const button=$('button',nav);
  const setCollapsed = collapsed => {
    nav.classList.toggle('is-collapsed',collapsed);
    button.setAttribute('aria-expanded',String(!collapsed));
    button.setAttribute('aria-label',collapsed?'Expand shot navigator':'Collapse shot navigator');
    button.textContent=collapsed?'›':'‹';
  };
  button.onclick=()=>setCollapsed(!nav.classList.contains('is-collapsed'));
  const narrow=matchMedia('(max-width:950px)');
  setCollapsed(narrow.matches);
  narrow.addEventListener?.('change',event=>setCollapsed(event.matches));
}

function installStudioActionBar(drawer) {
  if (document.body.dataset.t1Page !== 'studio') return;
  const world = $('#worldPanel'); if (!world || $('.t1-action-bar', world)) return;
  const bar=document.createElement('div');bar.className='t1-action-bar';bar.setAttribute('role','toolbar');bar.setAttribute('aria-label','Stage tools');
  const specs=[
    ['select','⌖','Select / drag'],['actor','A','Place actor'],['cart','C','Place cart'],['path','⌁','Draw path'],['monitor','▣','Monitor'],['inspect','⋯','Inspect']
  ];
  bar.innerHTML=specs.map(([id,icon,label])=>`<button type="button" data-tool="${id}" aria-label="${label}" title="${label}"><span aria-hidden="true">${icon}</span><em>${label}</em></button>`).join('');
  world.append(bar);
  const selectTool = id => $$('.t1-action-bar button',world).forEach(b=>b.classList.toggle('active',b.dataset.tool===id));
  $('[data-tool="select"]',bar).onclick=()=>{selectTool('select');$('#worldCanvas')?.focus();};
  $('[data-tool="actor"]',bar).onclick=()=>{selectTool('actor');$('#placeActor')?.click();};
  $('[data-tool="cart"]',bar).onclick=()=>{selectTool('cart');$('#placeCart')?.click();};
  $('[data-tool="path"]',bar).onclick=()=>{selectTool('path');if($('#drawRoute')&&!$('#drawRoute').hidden)$('#drawRoute').click();};
  $('[data-tool="monitor"]',bar).onclick=()=>{selectTool('monitor');$('.camera-panel')?.classList.toggle('t1-monitor-expanded');};
  $('[data-tool="inspect"]',bar).onclick=()=>{selectTool('inspect');drawer?.open('inspect');};
  document.addEventListener('takeone:selection',event=>selectTool(event.detail?.kind==='actor'?'actor':event.detail?.kind==='cart'?'cart':'select'));
  selectTool('select');
}

function installMonitorDocking() {
  if (document.body.dataset.t1Page !== 'studio') return;
  const column=$('.camera-column'), handle=$('.camera-title'), grid=$('.preview-grid'), panel=$('.camera-panel');
  if(!column||!handle||!grid||handle.dataset.dockInstalled)return;
  handle.dataset.dockInstalled='1'; handle.title='Drag the Director Monitor · double-click to dock';
  const controls=document.createElement('span');controls.className='t1-monitor-actions';
  controls.innerHTML='<button type="button" data-monitor-settings aria-label="Show camera controls" aria-pressed="false">Lens</button><button type="button" data-monitor-dock aria-label="Dock Director Monitor">⌗</button>';
  handle.append(controls);
  $('[data-monitor-settings]',controls).onclick=event=>{event.stopPropagation();const open=panel.classList.toggle('t1-monitor-expanded');event.currentTarget.setAttribute('aria-pressed',String(open));};
  const dock=(where='tr')=>{column.dataset.dock=where;column.style.left=column.style.top=column.style.right=column.style.bottom='';};
  let dockIndex=0; const docks=['tr','br','tl'];
  $('[data-monitor-dock]',controls).onclick=event=>{event.stopPropagation();dockIndex=(dockIndex+1)%docks.length;dock(docks[dockIndex]);};
  let drag=null;
  handle.addEventListener('pointerdown',event=>{
    if(event.button!==0||event.target.closest('button,input,select')||matchMedia('(max-width:950px)').matches)return;
    const gr=grid.getBoundingClientRect(),cr=column.getBoundingClientRect();
    drag={id:event.pointerId,dx:event.clientX-cr.left,dy:event.clientY-cr.top};
    column.dataset.dock='free';column.style.right=column.style.bottom='auto';
    column.style.left=`${cr.left-gr.left}px`;column.style.top=`${cr.top-gr.top}px`;
    handle.setPointerCapture(event.pointerId);event.preventDefault();
  });
  handle.addEventListener('pointermove',event=>{
    if(!drag||drag.id!==event.pointerId)return;
    const gr=grid.getBoundingClientRect(),cr=column.getBoundingClientRect();
    const x=Math.max(8,Math.min(gr.width-cr.width-8,event.clientX-gr.left-drag.dx));
    const y=Math.max(8,Math.min(gr.height-cr.height-8,event.clientY-gr.top-drag.dy));
    column.style.left=`${x}px`;column.style.top=`${y}px`;event.preventDefault();
  });
  const finish=event=>{if(!drag||drag.id!==event.pointerId)return;if(handle.hasPointerCapture(event.pointerId))handle.releasePointerCapture(event.pointerId);drag=null;};
  handle.addEventListener('pointerup',finish);handle.addEventListener('pointercancel',finish);handle.ondblclick=()=>dock('tr');
  addEventListener('resize',()=>{if(matchMedia('(max-width:950px)').matches)dock('tr');});
  dock('tr');
}

function installScriptDialogue() {
  const rail=$('#shotRail'), panel=$('.camera-panel');
  if(!rail||!panel||$('#scriptDialogue'))return;
  const caption=document.createElement('p');caption.id='scriptDialogue';
  caption.className='script-dialogue';caption.hidden=true;panel.append(caption);
  const direct=document.createElement('a');direct.className='secondary';direct.textContent='Direct this shot in natural language ↗';direct.hidden=true;panel.append(direct);
  const session=new URLSearchParams(location.search).get('script')?.split('/')[0];
  const sync=()=>{
    const text=$('.rail-row.active em',rail)?.textContent||'';
    if(caption.textContent!==text)caption.textContent=text;
    caption.hidden=!text;
    const shot=$('.rail-row.active',rail)?.dataset.shotId;
    direct.hidden=!session||!shot;
    if(session&&shot)direct.href='/director.html?session='+encodeURIComponent(session)+'&direct_shot='+encodeURIComponent(shot);
  };
  new MutationObserver(sync).observe(rail,{subtree:true,childList:true,attributes:true,attributeFilter:['class'],characterData:true});
  sync();
}

function installScriptRecovery() {
  const ref=new URLSearchParams(location.search).get('script');
  const world=$('#worldPanel'), loading=$('#loadingText');
  if(!ref||!world||!loading)return;
  const session=ref.split('/')[0];
  if(!/^[0-9a-f-]{36}$/i.test(session))return;
  const link=document.createElement('a');link.className='secondary';
  link.href='/director.html?session='+encodeURIComponent(session);
  link.textContent='Open current script in Director';link.hidden=true;
  loading.insertAdjacentElement('afterend',link);
  const sync=()=>{link.hidden=world.dataset.previewState!=='error';};
  new MutationObserver(sync).observe(world,{attributes:true,attributeFilter:['data-preview-state']});
  sync();
}

function installPrimaryActionContract() {
  if (document.body.dataset.t1Page !== 'studio') return;
  const toolbar=$('.workspace-toolbar'), world=$('#worldPanel');
  if(!toolbar||!world||$('.t1-primary-actions',toolbar))return;
  const dock=document.createElement('div'); dock.className='t1-primary-actions'; dock.hidden=true; dock.setAttribute('role','toolbar'); dock.setAttribute('aria-label','Primary shot actions');
  dock.innerHTML=`<button type="button" data-primary="edit" class="secondary">Edit path</button><button type="button" data-primary="finish" class="primary">Finish path</button><button type="button" data-primary="undo" class="secondary">Undo</button><button type="button" data-primary="play" class="primary">▶ Play Preview</button><button type="button" data-primary="reset" class="secondary">Reset</button><button type="button" data-primary="retry" class="primary">Retry preview</button>`;
  toolbar.appendChild(dock);
  const map={edit:'#drawRoute',finish:'#finishRoute',undo:'#undoRoute',play:'#playBtn',reset:'#resetBtn',retry:'#retryPreview'};
  for(const [name,selector] of Object.entries(map))$(`[data-primary="${name}"]`,dock).onclick=()=>$(selector)?.click();
  const sync=()=>{
    const sequence=document.body.dataset.sequence==='true';
    const drawing=$('#worldCanvas')?.classList.contains('drawing');
    const mode=$('#moveMode')?.value||'';
    const ready=world.dataset.previewState==='ready';
    const failed=world.dataset.previewState==='error';
    const path=mode==='path';
    const play=$('[data-primary="play"]',dock),reset=$('[data-primary="reset"]',dock);
    $('[data-primary="edit"]',dock).hidden=sequence||!path||drawing;
    $('[data-primary="finish"]',dock).hidden=sequence||!path||!drawing;
    $('[data-primary="undo"]',dock).hidden=sequence||!path||!drawing;
    $('[data-primary="retry"]',dock).hidden=!failed;
    play.hidden=failed||drawing; reset.hidden=failed||drawing;
    play.disabled=$('#playBtn')?.disabled??true; reset.disabled=$('#resetBtn')?.disabled??true;
    const playing=$('#playBtn')?.textContent?.includes('Pause');
    play.textContent=sequence?(playing?'Ⅱ Pause rehearsal':'▶ Rehearse film'):(playing?'Ⅱ Pause simulation':'▶ Simulate shot');
    $('[data-primary="edit"]',dock).textContent=ready?'Edit path':'Draw path';
  };
  const observer=new MutationObserver(sync);
  observer.observe(world,{attributes:true,attributeFilter:['data-preview-state']});
  observer.observe($('#worldCanvas'),{attributes:true,attributeFilter:['class']});
  observer.observe(document.body,{attributes:true,attributeFilter:['data-sequence']});
  for(const id of ['playBtn','resetBtn','retryPreview']){const node=$(`#${id}`);if(node)observer.observe(node,{attributes:true,childList:true,subtree:true,attributeFilter:['disabled','hidden']});}
  for(const id of ['drawRoute','finishRoute','undoRoute'])$(`#${id}`)?.addEventListener('click',()=>requestAnimationFrame(sync));
  $('#moveMode')?.addEventListener('change',()=>requestAnimationFrame(sync));
  sync();
}

function installStudioDisclosure() {
  if (document.body.dataset.t1Page !== 'studio') return;
  const stage = $('#stageControls');
  if (stage && !stage.parentElement.matches('.t1-stage-disclosure')) {
    const details = document.createElement('details');
    details.className = 't1-stage-disclosure';
    const summary = document.createElement('summary'); summary.textContent = 'Stage & placement';
    stage.before(details); details.append(summary, stage);
  }
  const drawer=createStudioDrawer();
  const toolbar = $('.workspace-toolbar');
  if (toolbar && !$('.t1-studio-actions', toolbar)) {
    const actions = document.createElement('div'); actions.className = 't1-studio-actions';
    actions.innerHTML = `<button type="button" data-t1-library>Shot types</button><button type="button" data-t1-scene>Scene</button><button type="button" data-t1-inspect>Inspect</button><button type="button" data-t1-command>⌘K</button>`;
    toolbar.append(actions);
    $('[data-t1-library]', actions).onclick = () => drawer?.open('library');
    $('[data-t1-scene]', actions).onclick = () => drawer?.open('scene');
    $('[data-t1-inspect]', actions).onclick = () => drawer?.open('inspect');
    $('[data-t1-command]', actions).onclick = () => document.dispatchEvent(new Event('takeone:open-command'));
  }
  installStudioNavigator(); installPrimaryActionContract(); installStudioActionBar(drawer); installMonitorDocking(); installMovementLibrary(drawer);
}

function installHoldToRun() {
  if (document.body.dataset.t1Page !== 'studio') return;
  const button = $('#runRobot');
  if (!button || button.dataset.holdInstalled) return;
  button.dataset.holdInstalled = '1';
  button.classList.add('t1-hold');
  const originalLabel = 'Hold to run robot';
  let timer = 0, started = 0, raf = 0, allowClick = false;
  const reset = () => {
    clearTimeout(timer); cancelAnimationFrame(raf); timer = 0; started = 0;
    button.dataset.holding = '0'; button.style.setProperty('--t1-hold', '0%');
    if (!button.dataset.confirmed) button.textContent = originalLabel;
  };
  const tick = () => {
    if (!started) return;
    const pct = Math.min(100, ((performance.now() - started) / 900) * 100);
    button.style.setProperty('--t1-hold', `${pct}%`);
    if (pct < 100) raf = requestAnimationFrame(tick);
  };
  const begin = event => {
    if (button.disabled || started) return;
    event.preventDefault();
    started = performance.now(); button.dataset.holding = '1'; button.textContent = 'Keep holding…'; tick();
    timer = setTimeout(() => {
      allowClick = true; button.dataset.confirmed = '1'; button.textContent = '✓ Running';
      started = 0; button.click();
      setTimeout(() => { delete button.dataset.confirmed; button.textContent = originalLabel; button.style.setProperty('--t1-hold','0%'); }, 900);
    }, 900);
  };
  const cancel = () => { if (started) reset(); };
  button.addEventListener('pointerdown', begin);
  button.addEventListener('pointerup', cancel); button.addEventListener('pointercancel', cancel); button.addEventListener('pointerleave', cancel);
  button.addEventListener('keydown', event => { if ((event.key === ' ' || event.key === 'Enter') && !event.repeat) begin(event); });
  button.addEventListener('keyup', event => { if (event.key === ' ' || event.key === 'Enter') cancel(); });
  button.addEventListener('click', event => {
    if (allowClick) { allowClick = false; return; }
    event.preventDefault(); event.stopImmediatePropagation();
  }, true);
  new MutationObserver(() => { if (!button.dataset.holding && !button.dataset.confirmed) button.textContent = originalLabel; }).observe(button, {attributes:true, attributeFilter:['disabled']});
  button.textContent = originalLabel;
}

function installStudioLanguage() {
  if (document.body.dataset.t1Page !== 'studio') return;
  const mapping = [['.camera-title .eyebrow', 'Director monitor'],['.shot-readings .eyebrow', 'Shot facts']];
  mapping.forEach(([selector, label]) => { const node = $(selector); if (node) node.textContent = label; });
  const scope = $('.phone-scope');
  if (scope) scope.textContent = 'Lens, stabilization and horizon are preview choices. Match them in the iPhone recording app before the take.';
  const output=$('#outputView'); if(output?.closest('label'))output.closest('label').classList.add('t1-output-view');
}

function installProgressiveDisclosureTooltips() {
  let activeTooltip = null;

  const showTooltip = (trigger, text) => {
    if (!text) return;
    hideTooltip();
    const tip = document.createElement('div');
    tip.className = 't1-tooltip';
    tip.textContent = text;
    document.body.append(tip);
    const rect = trigger.getBoundingClientRect();
    const tipRect = tip.getBoundingClientRect();
    let top = rect.bottom + 6;
    let left = rect.left + (rect.width / 2) - (tipRect.width / 2);
    if (left + tipRect.width > window.innerWidth - 12) {
      left = window.innerWidth - tipRect.width - 12;
    }
    if (left < 12) left = 12;
    if (top + tipRect.height > window.innerHeight - 12) {
      top = rect.top - tipRect.height - 6;
    }
    tip.style.top = `${Math.round(top)}px`;
    tip.style.left = `${Math.round(left)}px`;
    requestAnimationFrame(() => { tip.dataset.visible = '1'; });
    activeTooltip = tip;
  };

  const hideTooltip = () => {
    if (activeTooltip) {
      activeTooltip.remove();
      activeTooltip = null;
    }
  };

  document.addEventListener('pointerover', (event) => {
    const trigger = event.target.closest('[data-tooltip]');
    if (trigger) showTooltip(trigger, trigger.dataset.tooltip);
  });

  document.addEventListener('pointerout', (event) => {
    const trigger = event.target.closest('[data-tooltip]');
    if (trigger && !event.relatedTarget?.closest?.('.t1-tooltip')) hideTooltip();
  });

  document.addEventListener('focusin', (event) => {
    const trigger = event.target.closest('[data-tooltip]');
    if (trigger) showTooltip(trigger, trigger.dataset.tooltip);
  });

  document.addEventListener('focusout', (event) => {
    const trigger = event.target.closest('[data-tooltip]');
    if (trigger) hideTooltip();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') hideTooltip();
  });
}

function init() {
  installCommandPalette();
  installDirectorProgressiveDisclosure();
  installDirectorDisplayPolish();
  installStudioDisclosure();
  installHoldToRun();
  installStudioLanguage();
  installScriptDialogue();
  installScriptRecovery();
  installProgressiveDisclosureTooltips();
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true});
else init();
