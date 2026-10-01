// Read-only presentation of the compiler's edited-window motion evidence.
export function travelReviewLines(report) {
  if (!report) return [];
  const m=report.metrics;
  if (!m) return ['Movement evidence unavailable; recompile the retained source window.'];
  const lines=[`Movement: ${report.status.replaceAll('_',' ')} · simulated FK`,
    `Actor ${m.actor.path_m.toFixed(2)} m · cart ${m.cart.path_m.toFixed(2)} m · optical path ${m.optical.path_m.toFixed(2)} m`,
    `Phone relative to base: ${(m.arm_relative.excursion_m*100).toFixed(1)} cm · ${(m.arm_rotation_excursion_rad*180/Math.PI).toFixed(1)}°`,
    `Light relative to base: ${(m.light_relative?.excursion_m*100||0).toFixed(1)} cm · ${((m.light_rotation_excursion_rad||0)*180/Math.PI).toFixed(1)}°`,
    `Longest actor + cart + phone overlap: ${m.longest_simultaneous_s.toFixed(2)} s`];
  if(report.requirements?.light_role&&report.requirements.light_role!=='natural') lines.push(`Light role: ${report.requirements.light_role.replaceAll('_',' ')} · position/aim preview; BR60 brightness/CCT remain manual`);
  const joints=['shoulder pan','shoulder lift','elbow flex','wrist flex','wrist roll'];
  for(const [role,values] of [['Phone',m.phone_joint_excursion_rad],['Light',m.light_joint_excursion_rad]]) {
    if(Array.isArray(values)&&values.length===5&&values.every(Number.isFinite))
      lines.push(`${role} joint travel (simulated range): ${values.map((v,i)=>`${joints[i]} ${(v*180/Math.PI).toFixed(1)}°`).join(' · ')}`);
    else lines.push(`${role} joint travel unavailable.`);
  }
  for(const [a,b] of report.overlap_intervals_s||[]) lines.push(`Simultaneous ${a.toFixed(2)}–${b.toFixed(2)} s of this edit`);
  for(const phase of report.coordination_phases||[]) {
    const active=phase.active?.length?phase.active.join(' + '):'intentional hold';
    lines.push(`Phase ${phase.start_s.toFixed(2)}–${phase.end_s.toFixed(2)} s · ${active}`);
  }
  if(m.camera_position_error_max_m!==undefined)lines.push(`Requested optical path maximum error: ${(m.camera_position_error_max_m*100).toFixed(1)} cm`);
  if(m.light_position_error_max_m!==undefined)lines.push(`Requested light path maximum error: ${(m.light_position_error_max_m*100).toFixed(1)} cm`);
  lines.push('Setup and discarded footage excluded. Sampled bins do not establish hardware safety, photometry or cinematic quality.');
  return lines;
}

export function opticalKeysFromPreview(preview) {
  const source=preview.frames.filter(f=>f.time_s>=preview.orbit_start_s-1e-8);
  if(!source.length)throw new Error('Compile the achieved camera before seeding path handles.');
  return [0,.5,1].map(at=>{
    const t=preview.orbit_start_s+at*preview.orbit_duration_s;
    let frame=source[0];for(const f of source){if(f.time_s>t+1e-8)break;frame=f;}
    return {at,value:[...frame.camera.pos],ease:'smooth'};
  });
}
