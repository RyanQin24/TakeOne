import { beforeEach, describe, expect, it } from "vitest";
import { useEditor } from "../store";
import type { EditOperation, ProjectState, RenderJob, StreamEvent } from "../types";

const project = { project_id: "test", version: 2, timeline: { tracks: [], duration_s: 0 } } as unknown as ProjectState;
const operation = { sequence: 2, type: "SET_INTENT", target: {}, parameters: {}, public_explanation: "Update brief" } as EditOperation;
describe("undo state mirror", () => {
  beforeEach(() => useEditor.getState().open("test", project, [operation]));
  it("resets the cursor on undo and accepts a new edit reusing that sequence", () => {
    const undone = { ...project, version: 1 };
    useEditor.getState().ingest({ sequence: 1, operation: null, patch: [{ op: "replace", path: "", value: undone }] } as StreamEvent);
    expect(useEditor.getState().lastSequence).toBe(1);
    useEditor.getState().ingest({ sequence: 2, operation, patch: [{ op: "replace", path: "/version", value: 2 }] } as StreamEvent);
    expect(useEditor.getState().project?.version).toBe(2);
    expect(useEditor.getState().activity).toHaveLength(1);
  });
  it("still ignores duplicate incremental events", () => {
    useEditor.getState().ingest({ sequence: 2, operation, patch: [{ op: "replace", path: "/version", value: 99 }] } as StreamEvent);
    expect(useEditor.getState().project?.version).toBe(2);
  });
  it("keeps timeline and Media selections exclusive", () => {
    useEditor.getState().selectClip("clip-1");
    expect(useEditor.getState().selectedClipId).toBe("clip-1");
    expect(useEditor.getState().selectedMediaId).toBeNull();
    useEditor.getState().selectMedia("media-2");
    expect(useEditor.getState().selectedClipId).toBeNull();
    expect(useEditor.getState().selectedMediaId).toBe("media-2");
  });
  it("preserves the explicit Media source when an unrelated clip edit streams in", () => {
    useEditor.getState().selectMedia("media-2");
    useEditor.getState().ingest({ schema_version: 1, project_id: "test", version: 3, sequence: 3,
      operation: { ...operation, sequence: 3, type: "TRIM_CLIP", target: { kind: "clip", clip_id: "clip-1" } },
      patch: [{ op: "replace", path: "/version", value: 3 }] });
    expect(useEditor.getState().selectedMediaId).toBe("media-2");
    expect(useEditor.getState().selectedClipId).toBeNull();
  });
  it("preserves the explicit timeline source when another clip edit streams in", () => {
    useEditor.getState().selectClip("clip-1");
    useEditor.getState().ingest({ schema_version: 1, project_id: "test", version: 3, sequence: 3,
      operation: { ...operation, sequence: 3, type: "TRIM_CLIP", target: { kind: "clip", clip_id: "clip-2" } },
      patch: [{ op: "replace", path: "/version", value: 3 }] });
    expect(useEditor.getState().selectedClipId).toBe("clip-1");
    expect(useEditor.getState().selectedMediaId).toBeNull();
  });
  it("retains automatic clip focus until the operator chooses a source", () => {
    for (const [sequence, clip_id] of [[3, "clip-1"], [4, "clip-2"]] as const) {
      useEditor.getState().ingest({ schema_version: 1, project_id: "test", version: sequence, sequence,
        operation: { ...operation, sequence, type: "TRIM_CLIP", target: { kind: "clip", clip_id } },
        patch: [{ op: "replace", path: "/version", value: sequence }] });
      expect(useEditor.getState().selectedClipId).toBe(clip_id);
      expect(useEditor.getState().selectedMediaId).toBeNull();
    }
  });
  it("clears project-scoped viewing state when another project is opened", () => {
    useEditor.getState().selectMedia("media-2");
    useEditor.getState().setPlayhead(4);
    useEditor.getState().setPreview("/api/editor/artifacts/old-project");
    useEditor.getState().setComparing(true);
    useEditor.getState().setJobs([{ status: "COMPLETED", artifact: "/old-project.mp4" } as RenderJob]);
    useEditor.getState().setStatus("Exporting old project");
    useEditor.getState().setExportId("old-project");
    useEditor.getState().open("another", { ...project, project_id: "another" }, []);
    expect(useEditor.getState().selectedMediaId).toBeNull();
    expect(useEditor.getState().selectedClipId).toBeNull();
    expect(useEditor.getState().playhead).toBe(0);
    expect(useEditor.getState().previewUrl).toBeNull();
    expect(useEditor.getState().comparing).toBe(false);
    expect(useEditor.getState().jobs).toEqual([]);
    expect(useEditor.getState().status).toBeNull();
    expect(useEditor.getState().exportId).toBeNull();
  });
});
