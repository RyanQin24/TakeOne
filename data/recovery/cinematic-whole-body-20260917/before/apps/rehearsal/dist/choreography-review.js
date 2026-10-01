// Read-only presentation of the compiler's edited-window motion evidence.
export function travelReviewLines(report) {
  if (!report) return [];
  const m=report.metrics;
  if (!m) return ['Movement evidence unavailable; recompile the retained source window.'];
  const lines=[`Movement: ${report.status.replaceAll('_',' ')} Â· simulated FK`,
    `Actor ${m.actor.path_m.toFixed(2)} m Â· cart ${m.cart.path_m.toFixed(2)} m Â· optical path ${m.optical.path_m.toFixed(2)} m`,
    `Phone relative to base: ${(m.arm_relative.excursion_m*100).toFixed(1)} cm Â· ${(m.arm_rotation_excursion_rad*180/Math.PI).toFixed(1)}Â°`,
    `Longest actor + cart + phone overlap: ${m.longest_simultaneous_s.toFixed(2)} s`];
  for(const [a,b] of report.overlap_intervals_s||[]) lines.push(`Simultaneous ${a.toFixed(2)}â€“${b.toFixed(2)} s of this edit`);
  if(m.camera_position_error_max_m!==undefined)lines.push(`Requested optical path maximum error: ${(m.camera_position_error_max_m*100).toFixed(1)} cm`);
  lines.push('Setup and discarded footage excluded. Sampled bins do not establish hardware safety or cinematic quality.');
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
