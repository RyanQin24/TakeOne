import { create } from "zustand";
import { applyPatch } from "./patch";
import type { EditOperation, Phase, ProjectState, RenderJob, StreamEvent } from "./types";

// One rule governs this file: the client mirrors state, it does not derive it. Every field
// of `project` arrived in a patch computed by the Python reducer. The only things the
// client owns are what it is looking at (selection, playhead) and how it animates the
// difference between one published version and the next.

export interface ActivityEntry {
  sequence: number;
  type: string;
  phase: Phase;
  explanation: string;
  targetClipId?: string;
  at: number;
}

interface EditorStore {
  projectId: string | null;
  project: ProjectState | null;
  connected: boolean;
  lastSequence: number;
  activity: ActivityEntry[];
  jobs: RenderJob[];
  previewUrl: string | null;
  comparing: boolean;
  selectedClipId: string | null;
  selectedMediaId: string | null;
  selectionExplicit: boolean;
  playhead: number;
  error: string | null;
  status: string | null;
  ingestQueued: File[];
  ingestKey: string | null;
  exportId: string | null;
  /** Clips that arrived since the last render, so the timeline can animate them in once. */
  entering: Set<string>;

  open: (projectId: string, state: ProjectState, operations: EditOperation[]) => void;
  ingest: (event: StreamEvent) => void;
  queueIngest: (files: File[]) => void;
  markIngestStarted: (projectId: string) => void;
  setStatus: (status: string | null) => void;
  setExportId: (exportId: string | null) => void;
  setConnected: (connected: boolean) => void;
  setJobs: (jobs: RenderJob[]) => void;
  setPreview: (url: string | null) => void;
  setComparing: (comparing: boolean) => void;
  selectClip: (clipId: string | null) => void;
  selectMedia: (mediaId: string | null) => void;
  setPlayhead: (seconds: number) => void;
  setError: (message: string | null) => void;
  settle: (clipId: string) => void;
}

const ACTIVITY_LIMIT = 120;

function entryFor(operation: EditOperation): ActivityEntry {
  return {
    sequence: operation.sequence,
    type: operation.type,
    phase: operation.phase,
    explanation: operation.public_explanation,
    targetClipId: operation.target.clip_id,
    at: Date.now(),
  };
}

export const useEditor = create<EditorStore>((set, get) => ({
  projectId: null,
  project: null,
  connected: false,
  lastSequence: 0,
  activity: [],
  jobs: [],
  previewUrl: null,
  comparing: false,
  selectedClipId: null,
  selectedMediaId: null,
  selectionExplicit: false,
  playhead: 0,
  error: null,
  status: null,
  ingestQueued: [],
  ingestKey: null,
  exportId: null,
  entering: new Set<string>(),

  open: (projectId, state, operations) =>
    set({
      projectId,
      project: state,
      lastSequence: operations.length ? operations[operations.length - 1].sequence : 0,
      activity: operations
        .filter((item) => item.public_explanation)
        .slice(-ACTIVITY_LIMIT)
        .map(entryFor),
      selectedClipId: null,
      selectedMediaId: null,
      selectionExplicit: false,
      playhead: 0,
      jobs: [],
      previewUrl: null,
      comparing: false,
      status: null,
      exportId: null,
      entering: new Set<string>(),
      error: null,
    }),

  ingest: (event) => {
    const current = get();
    if (event.sequence && event.sequence <= current.lastSequence && event.operation) return;
    const wholeDocument = event.patch.length === 1 && event.patch[0].path === "";
    if (!current.project && !wholeDocument) {
      // An incremental patch is only meaningful against the state it was computed from.
      // Without that state, applying it would invent a project rather than mirror one.
      set({ error: "Waiting for the project snapshot before applying changes" });
      return;
    }
    let next: ProjectState | null = current.project;
    try {
      next = applyPatch(current.project ?? ({} as ProjectState), event.patch);
    } catch (error) {
      set({ error: `The state mirror fell out of step: ${(error as Error).message}` });
      return;
    }
    const activity = event.operation
      ? [...current.activity, entryFor(event.operation)].slice(-ACTIVITY_LIMIT)
      : wholeDocument ? current.activity.filter((item) => item.sequence <= event.sequence) : current.activity;
    const entering = new Set(current.entering);
    const clipId =
      event.operation?.target.clip_id ??
      (event.operation?.parameters as { clip_id?: string } | undefined)?.clip_id;
    if (event.operation?.type === "ADD_CLIP" && clipId) entering.add(clipId);
    const playhead = clipId
      ? (next?.timeline.tracks.flatMap((track) => track.clips).find((clip) => clip.clip_id === clipId)
          ?.timeline_start_s ?? current.playhead)
      : current.playhead;
    set({
      project: next,
      // Undo truncates the journal; the next real edit may reuse its removed sequence.
      lastSequence: wholeDocument ? event.sequence ?? next?.version ?? 0 : Math.max(current.lastSequence, event.sequence ?? 0),
      activity,
      entering,
      // Streamed edits may follow the AI cut, but never override an operator's source.
      selectedClipId: current.selectionExplicit ? current.selectedClipId : clipId ?? current.selectedClipId,
      selectedMediaId: current.selectionExplicit || !clipId ? current.selectedMediaId : null,
      playhead,
      error: null,
    });
  },

  queueIngest: (ingestQueued) => set({ ingestQueued, ingestKey: null }),
  markIngestStarted: (ingestKey) => set({ ingestKey }),
  setStatus: (status) => set({ status }),
  setExportId: (exportId) => set({ exportId }),

  setConnected: (connected) => set({ connected }),
  setJobs: (jobs) => set({ jobs }),
  setPreview: (previewUrl) => set({ previewUrl }),
  setComparing: (comparing) => set({ comparing }),
  selectClip: (selectedClipId) => set({
    selectedClipId,
    selectionExplicit: !!selectedClipId,
    ...(selectedClipId ? { selectedMediaId: null } : {}),
  }),
  selectMedia: (selectedMediaId) => set({
    selectedMediaId,
    selectionExplicit: !!selectedMediaId,
    ...(selectedMediaId ? { selectedClipId: null } : {}),
  }),
  setPlayhead: (playhead) => set({ playhead }),
  setError: (error) => set({ error }),
  settle: (clipId) =>
    set((current) => {
      if (!current.entering.has(clipId)) return current;
      const entering = new Set(current.entering);
      entering.delete(clipId);
      return { entering };
    }),
}));

export function findClip(project: ProjectState | null, clipId: string | null) {
  if (!project || !clipId) return null;
  for (const track of project.timeline.tracks) {
    const clip = track.clips.find((item) => item.clip_id === clipId);
    if (clip) return { track, clip };
  }
  return null;
}
