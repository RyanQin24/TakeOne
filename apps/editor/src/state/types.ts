// The wire shapes the Python editor publishes. These mirror `state.wire()` exactly; the
// client never invents a field, because the client never derives state.

export type Phase =
  | "understand" | "select" | "structure" | "rhythm"
  | "color" | "effects" | "audio" | "finalize" | "complete";

export const PHASES: Phase[] = [
  "understand", "select", "structure", "rhythm", "color", "effects", "audio", "finalize",
];

export interface MediaProbe {
  duration_s: number;
  width: number;
  height: number;
  fps: number;
  has_audio: boolean;
  video_codec: string;
}

export interface MediaItem {
  media_id: string;
  name: string;
  path: string;
  sha256: string;
  probe: MediaProbe;
  proxy_path: string | null;
  thumbnail_path: string | null;
  waveform_path: string | null;
}

export interface ColorGrade {
  exposure_stops: number;
  temperature_k: number;
  tint: number;
  contrast: number;
  saturation: number;
  lift: number;
  look_id: string | null;
  look_intensity: number;
  matched_to: string | null;
}

export interface EffectInstance {
  instance_id: string;
  effect_id: string;
  effect_version: number;
  parameters: Record<string, unknown>;
  start_s: number | null;
  end_s: number | null;
  enabled: boolean;
}

export interface SpeedPoint {
  time_s: number;
  rate: number;
  easing: string;
}

export interface SpeedCurve {
  points: SpeedPoint[];
}

export interface Clip {
  clip_id: string;
  media_id: string;
  timeline_start_s: number;
  timeline_end_s: number;
  timeline_duration_s: number;
  source_start_s: number;
  source_end_s: number;
  speed_curve: SpeedCurve | null;
  interpolation: string;
  effects: EffectInstance[];
  color: ColorGrade;
  enabled: boolean;
  label: string | null;
}

export interface Track {
  track_id: string;
  kind: "video" | "overlay" | "effect" | "audio";
  duration_s: number;
  clips: Clip[];
}

export interface TransitionInstance {
  transition_id: string;
  effect_id: string;
  from_clip_id: string;
  to_clip_id: string;
  duration_s: number;
}

export interface Marker {
  marker_id: string;
  time_s: number;
  kind: "beat" | "downbeat" | "impact" | "slot" | "cut";
  label: string | null;
  strength: number;
}

export interface Timeline {
  duration_s: number;
  tracks: Track[];
  transitions: TransitionInstance[];
  markers: Marker[];
}

export interface SelectionState {
  state: "pending" | "analyzing" | "selected" | "rejected";
  score: number | null;
  signals: Record<string, number>;
  reason: string | null;
}

export interface AudioEvent {
  event_id: string;
  kind: string;
  asset_id: string;
  timeline_start_s: number;
  duration_s: number;
  gain_db: number;
  ducks: boolean;
}

export interface RenderSettings {
  fps: number;
  fps_num: number;
  fps_den: number;
  master_width: number;
  master_height: number;
  preview_long_edge: number;
}

export interface ProjectState {
  schema_version: number;
  project_id: string;
  version: number;
  phase: Phase;
  intent: { prompt: string; target_duration_s: number; aspect_ratio: string } | null;
  media: Record<string, MediaItem>;
  analysis: Record<string, Record<string, unknown>>;
  selection: Record<string, SelectionState>;
  timeline: Timeline;
  audio: AudioEvent[];
  render_settings: RenderSettings;
  finalized: boolean;
}

export interface EditOperation {
  operation_id: string;
  sequence: number;
  type: string;
  phase: Phase;
  target: { kind: string; [key: string]: string };
  parameters: Record<string, never> | Record<string, unknown>;
  status: string;
  created_utc: string;
  executed_utc: string | null;
  public_explanation: string;
  metadata: Record<string, unknown>;
}

export interface PatchOperation {
  op: "add" | "remove" | "replace";
  path: string;
  value?: unknown;
}

export interface StreamEvent {
  schema_version: number;
  project_id: string;
  sequence: number;
  version: number;
  operation: EditOperation | null;
  patch: PatchOperation[];
}

export interface EffectParam {
  name: string;
  kind: string;
  required: boolean;
  minimum: number | null;
  maximum: number | null;
  choices: string[];
  default: unknown;
}

export interface EffectSpec {
  id: string;
  version: number;
  name: string;
  category: string;
  arity: number;
  primitive: boolean;
  description: string;
  tags: string[];
  parameters: EffectParam[];
}

export interface RenderJob {
  job_id: string;
  kind: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  progress: number;
  stage: string;
  output_id?: string;
  artifact: string | null;
  error: { message: string } | null;
}
