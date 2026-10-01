import type { EditOperation, EffectSpec, ProjectState, RenderJob } from "./types";
import type { DerivativeMetadata, DerivativeReceipt, VFXReceipt, VFXRequest } from "./vfx";

const BASE = "/api/editor";

export class APIError extends Error {
  constructor(message: string, public readonly status: number, public readonly code?: string) {
    super(message);
  }
}

async function call<T>(path: string, body?: unknown, method?: string): Promise<T> {
  const response = await fetch(BASE + path, {
    method: method ?? (body === undefined ? "GET" : "POST"),
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const document = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    throw new APIError((document.message as string) ?? `Request failed (${response.status})`, response.status, document.code as string | undefined);
  }
  return document as T;
}

export interface OperationRequest {
  type: string;
  target: Record<string, string>;
  parameters?: Record<string, unknown>;
  public_explanation?: string;
}

export const api = {
  planVFX: (projectId: string, request: VFXRequest) =>
    call<VFXReceipt>(`/projects/${projectId}/vfx/plan`, request),

  getVFX: (projectId: string, requestId: string) =>
    call<VFXReceipt>(`/projects/${projectId}/vfx/plans/${requestId}`),

  uploadDerivative: async (projectId: string, file: File, metadata: DerivativeMetadata) => {
    const body = new FormData();
    body.append("file", file, file.name);
    body.append("metadata", JSON.stringify(metadata));
    const response = await fetch(`${BASE}/projects/${projectId}/vfx/derivatives/upload`, { method: "POST", body });
    const document = await response.json().catch(() => ({})) as Record<string, unknown>;
    if (!response.ok) throw new APIError((document.message as string) ?? `Import failed (${response.status})`, response.status, document.code as string | undefined);
    return document as unknown as DerivativeReceipt;
  },
  health: () => call<{ ok: boolean; backend: { ready: boolean } }>("/health"),

  projects: () =>
    call<{ projects: { project_id: string; title: string; updated_utc: string }[] }>("/projects"),

  createProject: (
    project_id: string,
    title: string,
    intent?: { prompt: string; target_duration_s: number; aspect_ratio: string },
  ) =>
    call<{ state: ProjectState; library: { folder: string } }>("/projects", {
      project_id,
      title,
      ...(intent ? { intent } : {}),
    }),

  inspect: (projectId: string) =>
    call<{
      project: { project_id: string; title: string };
      state: ProjectState;
      operations: { sequence: number; operation: EditOperation }[];
    }>(`/projects/${projectId}`),

  importMedia: (projectId: string, path: string, place = false) =>
    call<{ operation: EditOperation; media_id?: string }>(`/projects/${projectId}/media`, {
      path,
      place,
    }),

  placeMedia: (projectId: string, media_id: string) =>
    call<{ ok: boolean }>(`/projects/${projectId}/place`, { media_id }),

  uploadMedia: async (projectId: string, file: File, place = true) => {
    const body = new FormData();
    body.append("file", file, file.name);
    body.append("place", place ? "true" : "false");
    const response = await fetch(`${BASE}/projects/${projectId}/upload`, {
      method: "POST",
      body,
    });
    const document = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    if (!response.ok) {
      throw new Error((document.message as string) ?? `Upload failed (${response.status})`);
    }
    return document as { ok: boolean; media_id: string; imported: boolean; placed: boolean };
  },

  submit: (projectId: string, operation: OperationRequest) =>
    call<{ sequence: number; version: number }>(`/projects/${projectId}/operations`, { operation }),

  autoEdit: (projectId: string, pace_s = 0.32) =>
    call<{ ok: boolean; applied: number; phase: string; duration_s: number }>(
      `/projects/${projectId}/auto-edit`,
      { pace_s },
    ),

  undo: (projectId: string, steps = 1) =>
    call<{ version: number }>(`/projects/${projectId}/undo`, { steps }),

  render: (projectId: string, target: "preview" | "master" = "preview", wait = false) =>
    call<{
      cached: boolean;
      artifact?: string;
      job?: RenderJob;
      work: { output_id: string; cache: { nodes: number; cached: number; missing: number } };
    }>(`/projects/${projectId}/render`, { target, wait }),

  jobs: (projectId: string) => call<{ jobs: RenderJob[] }>(`/projects/${projectId}/jobs`),

  effects: () => call<{ effects: EffectSpec[] }>("/effects"),

  artifactUrl: (nodeId: string, download = false, filename?: string) => {
    const params = new URLSearchParams();
    if (download) params.set("download", "1");
    if (filename) params.set("filename", filename);
    const query = params.toString();
    return `${BASE}/artifacts/${nodeId}${query ? `?${query}` : ""}`;
  },

  mediaUrl: (projectId: string, mediaId: string, variant = "proxy") =>
    `${BASE}/projects/${projectId}/media/${mediaId}/${variant}`,
};
