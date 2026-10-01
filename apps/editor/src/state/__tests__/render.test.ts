import { expect, it } from "vitest";
import { renderJobFor } from "../render";
import type { RenderJob } from "../types";

it("never downloads an older completed export while the requested master is rendering", () => {
  const jobs = [
    { output_id: "old", kind: "render:master", status: "COMPLETED" },
    { output_id: "new", kind: "render:master", status: "RUNNING" },
    { output_id: "preview", kind: "render:preview", status: "COMPLETED" },
  ] as RenderJob[];
  expect(renderJobFor(jobs, "new", "master")?.status).toBe("RUNNING");
  expect(renderJobFor(jobs, "missing", "master")).toBeUndefined();
  expect(renderJobFor(jobs, null, "master")).toBeUndefined();
  expect(renderJobFor(jobs, "preview", "master")).toBeUndefined();
  expect(renderJobFor(jobs, "preview", "preview")?.status).toBe("COMPLETED");
});
