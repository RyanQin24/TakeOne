// Pure playback maths for a multi-shot rehearsal. No DOM, no THREE: node --test runs this directly.

// Each shot is compiled with its actor at the origin. A stage places that take on
// its scene-local mark without rebuilding the rig or solving its motion again.
export function rotateZ(quat, sin, cos) {
  const [x, y, z, w] = quat;
  return [cos * x - sin * y, sin * x + cos * y, cos * z + sin * w, cos * w - sin * z];
}

export function placePreview(preview, stage) {
  if (!stage || (!stage.heading_rad && !stage.origin_m[0] && !stage.origin_m[1])) return preview;
  const [ox, oy] = stage.origin_m, h = stage.heading_rad;
  const c = Math.cos(h), s = Math.sin(h), hs = Math.sin(h / 2), hc = Math.cos(h / 2);
  const point = (x, y) => [ox + x * c - y * s, oy + x * s + y * c];
  const pose = target => {
    const [x, y] = point(target.pos[0], target.pos[1]);
    target.pos = [x, y, target.pos[2]];
    target.quat = rotateZ(target.quat, hs, hc);
  };
  for (const frame of preview.frames) {
    [frame.q[0], frame.q[1]] = point(frame.q[0], frame.q[1]);
    frame.q[2] += h;
    frame.axle_m = point(frame.axle_m[0], frame.axle_m[1]);
    frame.face = [...point(frame.face[0], frame.face[1]), frame.face[2]];
    if (frame.camera_target_m) frame.camera_target_m = [...point(frame.camera_target_m[0], frame.camera_target_m[1]), frame.camera_target_m[2]];
    for (const body of frame.bodies) {
      const [x, y] = point(body[0], body[1]);
      body[0] = x;body[1] = y;
      const q = rotateZ([body[3], body[4], body[5], body[6]], hs, hc);
      body[3] = q[0];body[4] = q[1];body[5] = q[2];body[6] = q[3];
    }
    for (const key of ['camera', 'camera_view', 'light']) if (frame[key]) pose(frame[key]);
    if (frame.actor) {
      frame.actor.position_m = [...point(frame.actor.position_m[0], frame.actor.position_m[1]), frame.actor.position_m[2]];
      frame.actor.heading_rad += h;
    }
  }
  if (preview.requested_path_m) preview.requested_path_m = preview.requested_path_m.map(p => point(p[0], p[1]));
  return preview;
}

// One concatenated preview means the studio's existing renderer, scrubber and
// readouts work on a whole script without learning what a segment is.
export function concatenate(program, previews) {
  const frames = [];
  const segments = program.segments.filter(segment => previews.has(segment.segment_id));
  // A move has no performance of its own. Show the actor already standing on the
  // mark the cart is driving to, so the frame never loses its subject at a cut.
  segments.forEach((segment, index) => {
    if (segment.kind !== 'reposition') return;
    const next = previews.get(segments[index + 1]?.segment_id)?.frames[0];
    if (!next) return;
    for (const frame of previews.get(segment.segment_id).frames) {
      frame.actor = next.actor;
      frame.face = next.face;
    }
  });
  for (const segment of segments) {
    const preview = previews.get(segment.segment_id);
    for (const frame of preview.frames) frames.push({...frame, segment_id:segment.segment_id, time_s: segment.t0_s + frame.time_s});
  }
  if (!frames.length) throw new Error('This script has no rehearsable shots yet.');
  const first = previews.get(segments[0].segment_id);
  const last = segments[segments.length - 1];
  return {
    kind: 'takeone_sequence_previs', schema_version: 1,
    program, segments, frames,
    duration_s: last.t0_s + last.duration_s,
    orbit_start_s: segments[0].setup_s, orbit_duration_s: Math.max(segments[0].filming_s, 0.04),
    settings: segments[0].settings || {mode: 'reposition'},
    capabilities: first.capabilities, camera_output: first.camera_output,
    notes: [], frame: 'world_z_up',
    summary: summarize(program, segments, previews),
  };
}

// Preserve source speed. Trim over-coverage; label an end-frame hold if footage is short.
export function editedPreview(program, previews) {
  if(program.segments.some(s=>s.kind==='unavailable'))throw new Error('Resolve unavailable shots before playing the story edit.');
  const frames = [], segments = [];
  for (const shot of program.segments.filter(s => s.kind === 'shot')) {
    const source = previews.get(shot.segment_id);
    if (!source) throw new Error('A shot preview is missing. Recompile the script before playing the story edit.');
    const start = shot.edit.start_ms / 1000, duration = (shot.edit.end_ms-shot.edit.start_ms)/1000;
    const previousEnd=segments.length?segments.at(-1).t0_s+segments.at(-1).duration_s:0;
    if(Math.abs(start-previousEnd)>.001)throw new Error('The edit has an uncovered time interval. Add or adjust a shot before playing the story edit.');
    const take = source.frames.filter(f => f.time_s >= shot.setup_s-1e-8);
    const segment = {...shot, t0_s:start, duration_s:duration, setup_s:0, filming_s:duration,
      source_setup_s:shot.setup_s, coverage_gap_s:Math.max(0,duration-shot.filming_s)};
    segments.push(segment);
    for (const frame of take) {
      const elapsed = frame.time_s-shot.setup_s;
      if (elapsed > duration+1e-8) break;
      frames.push({...frame, segment_id:shot.segment_id, time_s:start+elapsed});
    }
    if (frames.length && frames.at(-1).time_s < start+duration-1e-8)
      frames.push({...frames.at(-1), time_s:start+duration, preview_hold:segment.coverage_gap_s>0.04});
  }
  if (!frames.length) throw new Error('No filmed shots are available for the edit.');
  const first = previews.get(segments[0].segment_id);
  return {kind:'takeone_sequence_previs',schema_version:1,program,segments,frames,
    duration_s:program.edit_duration_s,orbit_start_s:0,orbit_duration_s:segments[0].duration_s,
    settings:segments[0].settings,capabilities:first.capabilities,camera_output:first.camera_output,
    notes:[],frame:'world_z_up',playback_mode:'edit',summary:{...summarize(program,segments,previews),...frameTravel(frames,program.edit_duration_s)}};
}

export function frameTravel(frames,duration) {
  let distance=0,peak=0;
  for(let i=1;i<frames.length;i++) {
    const a=frames[i-1],b=frames[i],dt=b.time_s-a.time_s;
    if(a.segment_id!==b.segment_id||dt<=0||!a.axle_m||!b.axle_m)continue;
    const step=Math.hypot(b.axle_m[0]-a.axle_m[0],b.axle_m[1]-a.axle_m[1]);
    distance+=step;peak=Math.max(peak,step/dt);
  }
  return {distance_m:distance,average_speed_m_s:distance/Math.max(duration,1e-6),peak_speed_m_s:peak};
}

export function summarize(program, segments, previews) {
  let distance = 0, peak = 0, height = 0, subject = 0;
  for (const segment of segments) {
    const s = previews.get(segment.segment_id).summary;
    distance += s.distance_m || 0;
    peak = Math.max(peak, s.peak_speed_m_s || 0);
    height = s.camera_height_m ?? height;
    subject = s.subject_distance_m ?? subject;
  }
  const shots = segments.filter(s => s.kind === 'shot');
  return {
    distance_m: distance, peak_speed_m_s: peak, camera_height_m: height, subject_distance_m: subject,
    average_speed_m_s: distance / Math.max(1e-6, program.duration_s),
    shot_count: shots.length, move_count: segments.length - shots.length,
    rehearsal_duration_s: program.duration_s, edit_duration_s: program.edit_duration_s,
    physical_path_verified: false,
  };
}

// Half-open lookup: a boundary time belongs to the segment that starts there.
export function segmentAt(segments, seconds) {
  let low = 0, high = segments.length - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (segments[middle].t0_s <= seconds) low = middle;
    else high = middle - 1;
  }
  return segments[low];
}

export function boundaries(segments, duration) {
  return segments.map(segment => ({
    segment,
    left: (segment.t0_s / duration) * 100,
    width: (segment.duration_s / duration) * 100,
  }));
}
