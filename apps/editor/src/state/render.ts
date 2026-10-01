import type { RenderJob } from "./types";

export function renderJobFor(jobs: RenderJob[], outputId: string | null, target: "preview" | "master") {
  if (!outputId) return undefined;
  return jobs.find((job) => job.output_id === outputId && job.kind === `render:${target}`);
}
