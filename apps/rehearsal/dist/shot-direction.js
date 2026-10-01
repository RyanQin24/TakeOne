import {inventoryLines} from './asset-library/scene-inventory.js';
import {travelReviewLines} from './choreography-review.js';

// Film direction uses the edit clock; setup and source-tail rehearsal have no invented cues.
export function performanceAt(segment, seconds) {
  const local = seconds - segment.t0_s - (segment.setup_s || 0);
  const duration = segment.edit ? (segment.edit.end_ms - segment.edit.start_ms) / 1000 : segment.filming_s;
  const beats = segment.shot_card?.beats || [];
  if (local < 0) return {phase:'setup', local, current:null, next:beats[0] || null};
  if (local >= duration || local > segment.filming_s + .0001)
    return {phase:'outside_edit', local, current:null, next:null};
  return {phase:'filming', local,
    current:beats.find(b => b.start_s <= local && local < b.end_s) || null,
    next:beats.find(b => b.start_s > local) || null};
}

export function motionReviewLines(motion) {
  if (!motion) return [];
  const mm = value => (value * 1000).toFixed(1) + ' mm';
  const lines = ['Motion check: ' + motion.status.replaceAll('_', ' ') +
    ' · ' + (motion.intent_source === 'camera_height_keyframes' ? 'explicit height keys override preset' : 'named boom')];
  for (const check of motion.checks) {
    lines.push(check.time_range_s.map(t => t.toFixed(2) + ' s').join('–') +
      ' · expected ' + check.expected_direction +
      ' · authored ' + mm(check.requested_delta_m) + ' / achieved ' + mm(check.achieved_delta_m) +
      ' · source ' + check.source_range_s.map(t => t.toFixed(2) + ' s').join('–'));
  }
  lines.push('Simulated raw optical pose; setup and unused source tails excluded.');
  return lines;
}

const textNode = (tag, text) => {const node=document.createElement(tag);node.textContent=text;return node;};
const clock = n => Number(n).toFixed(2) + ' s';
export function directionCard(card, names={}) {
  const root=textNode('section','');root.className='direction-card';
  root.append(textNode('h4',card.size_label || 'Shot design'),textNode('p',card.actor_instruction || card.attention));
  const list=textNode('dl','');
  for(const [name,value] of Object.entries({
    Purpose:card.purpose, 'Watch for':card.attention, Opening:card.opening, Ending:card.ending,
    Continuity:card.continuity, 'Practical setup':card.practical_setup,
    Focus:card.focus ? card.focus.mode + ' · ' + card.focus.target + ' · set in the phone app' : '',
  })) if(value)list.append(textNode('dt',name),textNode('dd',value));
  root.append(list);
  const beats=textNode('ol','');beats.className='performance-beats';
  for(const beat of card.beats || []) {
    const row=textNode('li','');
    row.append(textNode('strong',clock(beat.start_s)+'–'+clock(beat.end_s)+' · '+(names[beat.actor_id] || 'Crew')));
    row.append(textNode('p',beat.action));
    const detail=[beat.motivation,beat.emotion,beat.eyeline,beat.delivery].filter(Boolean);
    if(detail.length)row.append(textNode('small',detail.join(' · ')));
    beats.append(row);
  }
  root.append(beats);return root;
}

export function shootingGuide(program) {
  const lines=['# '+program.title,'','Shooting guide · authored direction and simulated geometry',
    'Script revision: '+program.document_digest,
    'Capture preview: 16:9 landscape. Requested edit: '+(program.requested_aspect || '16:9')+'.',
    'Match the recording phone, lens and crop before filming. Hardware and live tracking need separate qualification.',''];
  const names=Object.fromEntries((program.actors || []).map(a=>[a.actor_id,a.name]));
  if(program.visual_style) {
    lines.push('## Film language','');
    for(const [key,value] of Object.entries(program.visual_style))
      lines.push(key.replaceAll('_',' ')+': '+(Array.isArray(value)?value.join('; '):value),'');
  }
  let sceneId=null;
  for(const shot of program.segments.filter(s=>s.kind==='shot')) {
    const scene=program.scenes.find(s=>s.scene_id===shot.scene_id);
    if(sceneId!==shot.scene_id) {
      lines.push('## '+(scene?.title || 'Scene'),'',scene?.location || '',scene?.location_notes || '',
        'Location change: allow a separate setup; travel time is unestimated.','');
      const inventory = inventoryLines(scene);
      if(inventory.length)lines.push('Set inventory (operator declarations; not physical qualification):', ...inventory.map(value=>'- '+value), '');
      sceneId=shot.scene_id;
    }
    const card=shot.shot_card || {};
    lines.push('### Shot '+(shot.shot_number || shot.index+1)+' · '+(card.size_label || shot.name),'',
      'Edit: '+clock(shot.edit.start_ms/1000)+'–'+clock(shot.edit.end_ms/1000),
      'Setup: '+clock(shot.setup_s)+'; filmed source: '+clock(shot.filming_s),
      'Mark: '+shot.mark_id+' · '+JSON.stringify(shot.stage?.origin_m || [])+' m',
      'Move: '+shot.name, card.actor_instruction || '', 'Purpose: '+(card.purpose || ''),
      'Opening: '+(card.opening || ''), 'Ending: '+(card.ending || ''),
      'Continuity: '+(card.continuity || ''),'Setup directions: '+(card.practical_setup || ''),'');
    for(const b of card.beats || [])
      lines.push('- '+clock(b.start_s)+'–'+clock(b.end_s)+' · '+(names[b.actor_id] || 'Crew')+': '+b.action+
        ' '+[b.motivation,b.emotion,b.eyeline,b.delivery].filter(Boolean).join(' · '));
    lines.push('','Sound: '+(shot.audio_intent || 'Confirm on set.'));
    if(shot.dialogue)lines.push('Dialogue: '+shot.dialogue);
    if(card.focus)lines.push('Focus: '+card.focus.mode+' · '+card.focus.target+' (manual phone setup)');
    if(shot.tracking)lines.push('Tracking: '+shot.tracking.message);
    const review=shot.shot_review;
    if(review) {
      if(review.lens_start && review.lens_end && review.camera_height_range_m) {
        lines.push('Phone: '+review.phone_profile+' · '+review.lens_start.equivalent_mm+'–'+review.lens_end.equivalent_mm+' mm equivalent',
          review.lens_start.choice+' (manual phone app)',
          'Camera height achieved: '+review.camera_height_range_m.join('–')+' m',
          'Geometry review: '+review.status.replaceAll('_',' ')+' · '+review.samples_examined+' filmed samples');
      } else lines.push("Achieved camera geometry unavailable; recompile before review.");
      lines.push(...motionReviewLines(review.motion), ...travelReviewLines(review.travel));
      for(const issue of review.issues)
        lines.push('- '+issue.time_range_s.map(clock).join('–')+': '+issue.observation+' '+issue.recommendation);
      lines.push('Unchecked: '+review.unchecked.join('; '));
    }
    for(const advice of shot.advice || [])lines.push('- '+advice);
    lines.push('');
  }
  return lines.join('\n');
}
