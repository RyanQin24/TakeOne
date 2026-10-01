import { describe, expect, it } from "vitest";
import { flowKey, flowStale, loadFlow, proposalMatches, statusText } from "../vfx";
import type { VFXFlow } from "../vfx";

const flow: VFXFlow = {
  request: { request_id: "persisted-request", expected_version: 5, script: "One brief addition.",
    sources: [{ media_id: "source", source_sha256: "a".repeat(64), source_start_s: 0.5,
      source_end_s: 2.5, observations: [{ source: "operator notes", text: "The actor waves." }] }] },
  receipt: { schema_version: 1, request_id: "persisted-request", project_version: 5,
    status: "running", generated: false, placed: false },
};

describe("VFX refresh recovery", () => {
  it("recovers the same in-flight request, without constructing a replacement ID", () => {
    const storage = { getItem: (key: string) => key === flowKey("film") ? JSON.stringify(flow) : null };
    expect(loadFlow(storage, "film")).toEqual(flow);
    expect(loadFlow(storage, "other-film")).toBeNull();
  });

  it("retains request identity when refresh happens before a response arrives", () => {
    expect(loadFlow({ getItem: () => JSON.stringify({ ...flow, receipt: null }) }, "film")?.request.request_id)
      .toBe("persisted-request");
  });

  it("rejects corrupt storage and mismatched receipts rather than crashing or applying another request", () => {
    for (const raw of ["{", "null", JSON.stringify({ request: { ...flow.request, sources: [null] } }),
      JSON.stringify({ ...flow, receipt: { ...flow.receipt, request_id: "another-request" } }),
      JSON.stringify({ ...flow, receipt: { ...flow.receipt, status: "invented" } })]) {
      expect(loadFlow({ getItem: () => raw }, "film")).toBeNull();
    }
    expect(loadFlow({ getItem: () => { throw new Error("blocked"); } }, "film")).toBeNull();
  });

  it("marks results stale after an edit and respects server staleness after an undo", () => {
    expect(flowStale(flow, 5)).toBe(false);
    expect(flowStale(flow, 6)).toBe(true);
    expect(flowStale({ ...flow, receipt: { ...flow.receipt!, status: "stale" } }, 5)).toBe(true);
  });

  it("refuses a stored proposal with nonnumeric effect timing", () => {
    const malformed = { ...flow, receipt: { ...flow.receipt, status: "proposal", proposals: [{
      ...flow.request.sources[0], decision: "augment", prompt: "Add a sparkle", reason: "Small accent",
      effect_start_s: "0.5", effect_end_s: 1,
    }] } };
    expect(loadFlow({ getItem: () => JSON.stringify(malformed) }, "film")).toBeNull();
  });

  it("shows unavailable and uncertain outcomes without describing them as generated effects", () => {
    expect(statusText("unavailable")).toContain("unavailable");
    expect(statusText("uncertain")).toContain("Check its status");
    expect(statusText("failed")).toContain("No effect was generated or placed");
  });

  it("requires a fresh augment proposal for the exact persisted source", () => {
    const proposal = {
      ...flow.request.sources[0], decision: "augment" as const, prompt: "Add a sparkle", reason: "Small accent",
      effect_start_s: 0.5, effect_end_s: 1, protected_content: {
        people: true, action: true, camera_motion: true, geometry: true, text_logos: true, original_audio: true,
      },
    };
    const receipt = { ...flow.receipt!, status: "proposal" as const, proposals: [proposal] };
    expect(proposalMatches(receipt, flow.request, proposal)).toBe(true);
    expect(proposalMatches({ ...receipt, status: "stale" }, flow.request, proposal)).toBe(false);
    expect(proposalMatches({ ...receipt, proposals: [{ ...proposal, source_start_s: 0 }] }, flow.request, proposal)).toBe(false);
  });
});
