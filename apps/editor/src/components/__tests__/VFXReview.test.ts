import { describe, expect, it } from "vitest";
import { EMPTY_REVIEW_PLAYBACK, reviewPlayback } from "../VFXReview";

describe("VFX review playback gate", () => {
  it("requires both complete media playbacks and resets them together", () => {
    const sourcePlaying = reviewPlayback(EMPTY_REVIEW_PLAYBACK, { type: "start", media: "source" });
    const sourceDone = reviewPlayback(sourcePlaying, { type: "complete", media: "source" });
    expect(sourceDone).toEqual({ source: "complete", candidate: "idle" });

    const candidatePlaying = reviewPlayback(sourceDone, { type: "start", media: "candidate" });
    const bothDone = reviewPlayback(candidatePlaying, { type: "complete", media: "candidate" });
    expect(bothDone).toEqual({ source: "complete", candidate: "complete" });
    expect(reviewPlayback(bothDone, { type: "reset" })).toEqual(EMPTY_REVIEW_PLAYBACK);
  });

  it("does not count a seek to the end as complete playback", () => {
    const playing = { source: "playing", candidate: "complete" } as const;
    const seeking = reviewPlayback(playing, { type: "invalidate", media: "source" });
    expect(reviewPlayback(seeking, { type: "complete", media: "source" }))
      .toEqual({ source: "invalid", candidate: "complete" });
  });
});
