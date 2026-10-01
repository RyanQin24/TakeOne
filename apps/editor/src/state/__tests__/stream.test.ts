import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { pollJobs } from "../stream";
import { useEditor } from "../store";
import type { ProjectState, RenderJob } from "../types";

const project = (project_id: string) => ({
  project_id,
  version: 0,
  timeline: { tracks: [], duration_s: 0 },
}) as unknown as ProjectState;

describe("project-scoped job polling", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("discards an old project's in-flight response after a project switch", async () => {
    vi.stubGlobal("window", { setTimeout: vi.fn() });
    let finish!: (value: { jobs: RenderJob[] }) => void;
    const response = new Promise<{ jobs: RenderJob[] }>((resolve) => { finish = resolve; });
    vi.spyOn(api, "jobs").mockReturnValue(response);
    useEditor.getState().open("old", project("old"), []);
    const stop = await pollJobs("old", 100_000);

    useEditor.getState().open("new", project("new"), []);
    finish({ jobs: [{ status: "COMPLETED", artifact: "/old-preview.mp4" } as RenderJob] });
    await response;
    await Promise.resolve();

    expect(useEditor.getState().jobs).toEqual([]);
    stop();
  });

  it("discards a response as soon as the selected project changes", async () => {
    vi.stubGlobal("window", { setTimeout: vi.fn() });
    let finish!: (value: { jobs: RenderJob[] }) => void;
    const response = new Promise<{ jobs: RenderJob[] }>((resolve) => { finish = resolve; });
    vi.spyOn(api, "jobs").mockReturnValue(response);
    useEditor.getState().open("old", project("old"), []);
    let selected = "old";
    const stop = await pollJobs("old", 100_000, () => selected === "old");

    selected = "new";
    finish({ jobs: [{ status: "COMPLETED", artifact: "/old-preview.mp4" } as RenderJob] });
    await response;
    await Promise.resolve();

    expect(useEditor.getState().jobs).toEqual([]);
    stop();
  });
});
