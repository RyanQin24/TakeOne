import { describe, expect, it } from "vitest";
import { dropPosition, reorderRequest } from "../Timeline/reorder";
import type { Clip } from "../../state/types";

const clips = [["a", 0, 2], ["b", 2, 5], ["c", 5, 6]].map(([id, start, end]) => ({
  clip_id: id, timeline_start_s: start, timeline_end_s: end,
  timeline_duration_s: Number(end) - Number(start),
})) as Clip[];

describe("timeline insertion", () => {
  it("drops at beginning, between neighbours, and at end", () => {
    expect(dropPosition(clips, "c", -1)).toEqual({ index: 0, time: 0 });
    expect(dropPosition(clips, "c", 2.5)).toEqual({ index: 1, time: 2 });
    expect(dropPosition(clips, "a", 100)).toEqual({ index: 2, time: 6 });
  });
  it("does not count the dragged clip as an insertion slot", () => {
    expect(dropPosition(clips, "b", 3)).toEqual({ index: 1, time: 5 });
    expect(dropPosition([clips[0]], "a", 3)).toEqual({ index: 0, time: 0 });
  });
  it("submits a single journal operation, not optimistic position patches", () => {
    expect(reorderRequest("b", 0)).toEqual({ type: "REORDER_CLIP", target: { kind: "clip", clip_id: "b" },
      parameters: { index: 0 }, public_explanation: "Move shot to position 1." });
  });
});
