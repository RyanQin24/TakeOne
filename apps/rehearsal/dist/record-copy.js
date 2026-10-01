/* Every user-visible sentence on the Record page, in one place.
 *
 * Ninety-nine prose strings used to live inline across dist/*.js with no shared
 * copy layer, which is why the voice drifted from panel to panel. The truth
 * claims here are quoted from the honesty ledger and are not editable copy:
 * they may move into Evidence, they may not be softened.
 */

/* Three transport states. These exact words, nothing else. */
export const TRANSPORT = {
  idle: 'Idle',
  waiting: 'Waiting for framing',
  recording: 'Recording',
};

/* Why it is not rolling yet, in one sentence a director can act on. */
export const FRAMING = {
  started: 'Settled. The phone started recording.',
  holding: 'Holding steady.',
  aim: 'Not aimed at the subject yet.',
  too_small: 'Aimed, but the subject is too small in frame.',
  too_large: 'Aimed, but the subject is too large in frame.',
  stale_perception: 'Lost the camera feed. Check the witness camera.',
  target_lost: 'The subject left the frame.',
  target_confidence_low: 'Cannot see the subject clearly enough.',
  controller_update_rejected: 'The rig refused the last correction.',
  subject_required: 'Choose which person to film.',
  perception_unavailable: 'Grant camera access to judge framing.',
  manual: 'Manual recording: person detection and framing scores do not block Start filming.',
  watching: 'Watching for framing.',
};

/* The four claims this feature introduces. Required wording. */
export const HONESTY = {
  witness_offset:
    'Framing is judged from the witness camera. The offset to the phone lens has not been measured.',
  /* Only true once the operator has routed the handset's own video feed into
   * this computer and said so. It claims the tracked frames are the frames the
   * taking lens forms — not that TakeOne has read the recorded clip. */
  phone_feed:
    'Framing is judged on the phone\u2019s own video feed, so there is no witness-to-lens offset. '
    + 'TakeOne still has not read the recorded clip.',
  phone_feed_unset:
    'Tracking is watching a separate camera. Route the phone\u2019s USB-C video feed into this '
    + 'computer and select it below to aim on the frame the lens actually sees.',
  phone_unverified: 'The clip is on the phone. TakeOne has not read these frames.',
  people_only: 'Automatic framing works for people. Roll this take manually.',
  observe_no_motion: 'TakeOne is watching and will roll the camera. It is not moving the rig.',
};

/* Preserved verbatim from the previous surface — accurate, and about clocks. */
export const CLOCKS =
  'Host monotonic request and acknowledgement times share the event’s producer epoch. '
  + 'They are not camera timestamps.';

export const TAKE_STATES = {
  starting: 'starting',
  recording: 'recording',
  finalizing: 'finalizing',
  ready: 'ready',
  failed: 'failed',
  unknown: 'unresolved',
};

/* The four fatal ownership codes become one sentence and a reload, never a code. */
export const FATAL = {
  wrong_owner: 'Another tab owns this recorder. Reload to take over.',
  ownership_required: 'This tab lost its claim on the recorder. Reload to reconnect.',
  runtime_changed: 'The recorder restarted. Reload to reconnect.',
  runtime_replaced: 'The recorder was replaced. Reload to reconnect.',
};

export const LABELS = {
  monitor: 'Monitor',
  witness: 'Witness',
  plan: 'Plan',
  simulated: 'Simulated',
  framing: 'Framing',
  aim: 'Aim',
  size: 'Size',
  held: 'Held',
  subject: 'Subject',
  phone: 'Phone',
  takes: 'Takes',
  evidence: 'Evidence',
  start: 'Start filming',
  watch: 'Watch for framing',
  stop: 'Stop take',
  phoneSetup: 'Phone setup',
  score: 'Score this take',
  resolve: 'Resolve',
  retry: 'Retry',
  grantCamera: 'Grant camera access',
  noTakes: 'No takes yet. Start one when the framing is right.',
  phoneIdle: 'Not paired',
  cameraDenied: 'The camera is not available to this page.',
};

export const POLICIES = [
  { value: 'after_settle', label: 'Roll when settled' },
  { value: 'immediate', label: 'Roll immediately' },
  { value: 'manual', label: 'Roll manually' },
];

/* One sentence for the framing panel, chosen from the manager snapshot. */
export function framingSentence({
  cameraState = 'idle',
  policy = 'after_settle',
  subjectRequired = false,
  takeRolling = false,
  settled = false,
  holdComplete = false,
  aimWithin = false,
  sizeBelow = false,
  sizeAbove = false,
  reason = null,
} = {}) {
  if (policy === 'manual') return FRAMING.manual;
  if (reason === 'stale_perception') return FRAMING.stale_perception;
  if (typeof reason === 'string' && reason.startsWith('target_lost')) return FRAMING.target_lost;
  if (reason === 'target_confidence_low') return FRAMING.target_confidence_low;
  if (reason === 'controller_update_rejected') return FRAMING.controller_update_rejected;
  if (cameraState === 'denied' || cameraState === 'unavailable') return FRAMING.perception_unavailable;
  if (subjectRequired) return FRAMING.subject_required;
  if (takeRolling && settled && holdComplete) return FRAMING.started;
  if (settled) return FRAMING.holding;
  if (!aimWithin) return FRAMING.aim;
  if (sizeBelow) return FRAMING.too_small;
  if (sizeAbove) return FRAMING.too_large;
  return FRAMING.watching;
}
