/* One definition, used by the rail, the activity panel and the cross-app nav.
 *
 * The production phases mirror apps/rehearsal/dist/takeone-phases.js — five,
 * in that order, on every surface. The editor's own stages are four: nine steps
 * of ceremony is more vocabulary than the product can teach, so the nine
 * internal phase names map underneath four the operator reads.
 */
import { PHASES as INTERNAL, type Phase } from "./types";

export const PRODUCTION: { id: string; label: string; path: string | null }[] = [
  { id: "director", label: "Director", path: "/director.html" },
  { id: "world", label: "World", path: "/world.html" },
  { id: "studio", label: "Shot Studio", path: "/" },
  { id: "record", label: "Record", path: "/record.html" },
  { id: "edit", label: "Edit", path: null },
];

export const UTILITIES: { label: string; path: string; note: string }[] = [
  { label: "Voice rehearsal", path: "/voice.html", note: "Scripted read-through, offline fixture" },
  { label: "Motor Lab", path: "/motor-test.html", note: "Direct calibrated motor diagnostics" },
  { label: "Motion proof", path: "/drive-proof.html", note: "Cart movement evidence and limits" },
  { label: "Asset library", path: "/asset-library/browser.html", note: "Installed models and performers" },
];

export const STAGES = ["review", "assemble", "refine", "deliver"] as const;
export type Stage = (typeof STAGES)[number];

export const STAGE_LABEL: Record<Stage, string> = {
  review: "Review",
  assemble: "Assemble",
  refine: "Refine",
  deliver: "Deliver",
};

/* The internal phase names are unchanged; only what an operator reads is. */
export const STAGE_OF: Record<Phase, Stage> = {
  understand: "review",
  select: "review",
  structure: "assemble",
  rhythm: "assemble",
  color: "refine",
  effects: "refine",
  audio: "refine",
  finalize: "deliver",
  complete: "deliver",
};

export const PHASE_LABEL: Record<Phase, string> = Object.fromEntries(
  INTERNAL.map((phase) => [phase, STAGE_LABEL[STAGE_OF[phase]]]),
) as Record<Phase, string>;
