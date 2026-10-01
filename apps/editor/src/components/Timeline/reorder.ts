import type { Clip } from "../../state/types";

// Presentation-only drop hint. The server owns the resulting timeline positions.
export function dropPosition(clips: Clip[], clipId: string, seconds: number) {
  const others = clips.filter((clip) => clip.clip_id !== clipId);
  const found = others.findIndex((clip) => seconds < clip.timeline_start_s + clip.timeline_duration_s / 2);
  const index = found < 0 ? others.length : found;
  return { index, time: others[index]?.timeline_start_s ?? others.at(-1)?.timeline_end_s ?? 0 };
}

export function reorderRequest(clipId: string, index: number) {
  return {
    type: "REORDER_CLIP",
    target: { kind: "clip", clip_id: clipId },
    parameters: { index },
    public_explanation: `Move shot to position ${index + 1}.`,
  };
}
