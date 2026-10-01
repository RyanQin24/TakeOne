import { api } from "./api";
import { useEditor } from "./store";
import type { StreamEvent } from "./types";

// The stream is the only way state reaches the interface after the first load. It resumes
// from the last sequence it saw, so a dropped connection costs nothing: the server replays
// the operations that were missed, in order, with their patches.

export function connect(
  projectId: string,
  isCurrent: () => boolean = () => useEditor.getState().projectId === projectId,
): () => void {
  const store = useEditor.getState();
  let source: EventSource | null = null;
  let retry: number | undefined;
  let closed = false;

  const start = () => {
    if (closed || !isCurrent()) return;
    const since = useEditor.getState().lastSequence;
    source = new EventSource(`/api/editor/projects/${projectId}/stream?since=${since}`);

    source.addEventListener("open", () => {
      if (isCurrent()) useEditor.getState().setConnected(true);
    });

    source.addEventListener("operation", (message) => {
      if (!isCurrent()) return;
      try {
        useEditor.getState().ingest(JSON.parse((message as MessageEvent).data) as StreamEvent);
      } catch (error) {
        useEditor.getState().setError((error as Error).message);
      }
    });

    source.addEventListener("error", () => {
      if (!isCurrent()) return;
      useEditor.getState().setConnected(false);
      source?.close();
      source = null;
      if (!closed) retry = window.setTimeout(start, 1200);
    });
  };

  start();
  void store;

  return () => {
    closed = true;
    if (retry) window.clearTimeout(retry);
    source?.close();
    useEditor.getState().setConnected(false);
  };
}

export async function pollJobs(
  projectId: string,
  interval = 900,
  isCurrent: () => boolean = () => useEditor.getState().projectId === projectId,
): Promise<() => void> {
  let stopped = false;
  const tick = async () => {
    if (stopped || !isCurrent()) return;
    try {
      const { jobs } = await api.jobs(projectId);
      if (!stopped && isCurrent()) useEditor.getState().setJobs(jobs);
    } catch {
      /* a failed poll is not worth surfacing; the next one will say the same thing */
    }
    if (!stopped && isCurrent()) window.setTimeout(tick, interval);
  };
  void tick();
  return () => {
    stopped = true;
  };
}
