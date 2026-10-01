export const PRESERVATION = ["people", "action", "camera_motion", "geometry", "text_logos"] as const;
export type Preservation = typeof PRESERVATION[number];

export interface VFXSource {
  media_id: string;
  source_sha256: string;
  source_start_s: number;
  source_end_s: number;
  observations: { source: string; text: string }[];
}

export interface VFXRequest {
  request_id: string;
  expected_version: number;
  script: string;
  sources: VFXSource[];
}

export interface VFXProposal extends Omit<VFXSource, "observations"> {
  decision: "none" | "augment";
  effect_start_s: number | null;
  effect_end_s: number | null;
  prompt: string;
  reason: string;
  protected_content: Record<Preservation | "original_audio", boolean>;
}

export type VFXStatus = "queued" | "running" | "proposal" | "unavailable" | "failed" | "uncertain" | "stale";
export interface VFXReceipt {
  schema_version: number;
  request_id: string;
  project_version: number;
  status: VFXStatus;
  generated: false;
  placed: false;
  proposals?: VFXProposal[];
  provenance?: Record<string, unknown>;
  error?: { code: string; message: string };
}
export interface VFXFlow { request: VFXRequest; receipt: VFXReceipt | null }

export interface DerivativeMetadata {
  source_media_id: string;
  source_sha256: string;
  source_start_s: number;
  source_end_s: number;
  output_source_space: string;
  provider: string;
  model: string;
  model_version: string;
  job_id: string;
  prompt: string;
  settings: Record<string, unknown>;
  cost: { amount: number | null; unit: string; status: "reported" | "unknown" };
  rights_evidence: string;
  review: {
    reviewer: string;
    decision: "approved";
    notes: string;
    preserved: Record<Preservation, boolean>;
    audio: "reviewed" | "silent_source";
  };
}

export interface DerivativeReceipt {
  ok: boolean;
  media_id: string;
  reused: boolean;
  status: "reviewed_derivative";
  placed: false;
  lineage: Record<string, unknown>;
}

export function flowKey(projectId: string) { return `takeone-vfx:${projectId}`; }

export function loadFlow(storage: Pick<Storage, "getItem">, projectId: string): VFXFlow | null {
  try {
    const raw = storage.getItem(flowKey(projectId));
    if (!raw || raw.length > 64000) return null;
    const value = JSON.parse(raw) as VFXFlow;
    if (!value?.request || typeof value.request.request_id !== "string"
      || !Number.isInteger(value.request.expected_version) || typeof value.request.script !== "string"
      || !Array.isArray(value.request.sources) || value.request.sources.length !== 1) return null;
    const source = value.request.sources[0];
    if (!source || typeof source.media_id !== "string" || typeof source.source_sha256 !== "string"
      || !Number.isFinite(source.source_start_s) || !Number.isFinite(source.source_end_s)
      || !Array.isArray(source.observations) || source.observations.length !== 1
      || typeof source.observations[0]?.text !== "string") return null;
    if (value.receipt && (value.receipt.request_id !== value.request.request_id
      || !["queued", "running", "proposal", "unavailable", "failed", "uncertain", "stale"].includes(value.receipt.status))) return null;
    if (value.receipt?.status === "proposal") {
      const proposal = value.receipt.proposals?.[0];
      if (!proposal || !["none", "augment"].includes(proposal.decision) || typeof proposal.prompt !== "string"
      || typeof proposal.reason !== "string" || proposal.media_id !== source.media_id
      || proposal.source_sha256 !== source.source_sha256 || proposal.source_start_s !== source.source_start_s
      || proposal.source_end_s !== source.source_end_s) return null;
      if (proposal.decision === "augment" && (!Number.isFinite(proposal.effect_start_s)
        || !Number.isFinite(proposal.effect_end_s))) return null;
    }
    return value;
  } catch { return null; }
}

export function flowStale(flow: VFXFlow | null, version: number): boolean {
  return !!flow && (flow.request.expected_version !== version || flow.receipt?.status === "stale");
}

export function proposalMatches(
  receipt: VFXReceipt,
  request: VFXRequest,
  proposal: VFXProposal,
): boolean {
  const source = request.sources[0];
  return proposal.decision === "augment"
    && receipt.status === "proposal" && receipt.request_id === request.request_id
    && receipt.proposals?.some((candidate) => candidate.decision === "augment"
      && candidate.media_id === source?.media_id
      && candidate.source_sha256 === source?.source_sha256
      && candidate.source_start_s === source?.source_start_s
      && candidate.source_end_s === source?.source_end_s
      && candidate.media_id === proposal.media_id
      && candidate.source_sha256 === proposal.source_sha256
      && candidate.source_start_s === proposal.source_start_s
      && candidate.source_end_s === proposal.source_end_s) === true;
}

export function statusText(status: VFXStatus): string {
  return {
    queued: "Waiting for an effect proposal…",
    running: "Planning an effect…",
    proposal: "Effect proposal ready",
    unavailable: "AI planning is unavailable. Configure the planning provider on the local server.",
    failed: "The proposal failed. No effect was generated or placed.",
    uncertain: "The request could not be confirmed. Check its status before starting another request.",
    stale: "The project changed. Request a new proposal for the current edit.",
  }[status];
}
