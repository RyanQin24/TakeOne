import { useCallback, useEffect, useRef, useState } from "react";
import { IntentBar } from "./components/IntentBar";
import { Launch } from "./components/Launch";
import { Preview } from "./components/Preview";
import { ShotPanel } from "./components/ShotPanel";
import { Studio } from "./components/Studio";
import { TopBar } from "./components/TopBar";
import { Timeline } from "./components/Timeline/Timeline";
import { api } from "./state/api";
import { connect, pollJobs } from "./state/stream";
import { useEditor } from "./state/store";
import { renderJobFor } from "./state/render";

function fileTitle(title: string) {
  const stem = title.replace(/[^\w]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
  return `${stem || "takeone"}.mp4`;
}

function downloadMaster(nodeId: string, title: string) {
  const filename = fileTitle(title);
  const link = document.createElement("a");
  link.href = api.artifactUrl(nodeId, true, filename);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function writeProject(id: string | null) {
  const url = new URL(location.href);
  if (id) url.searchParams.set("project", id);
  else url.searchParams.delete("project");
  history.replaceState(null, "", `${url.pathname}${url.search}`);
}

export function App() {
  const [projectId, setProjectId] = useState<string | null>(
    new URLSearchParams(location.search).get("project"),
  );
  const selectedProjectId = useRef(projectId);
  const [title, setTitle] = useState("");
  const [exportUrl, setExportUrl] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const exportPending = useRef(false);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const previewRequest = useRef(0);
  const error = useEditor((state) => state.error);
  const status = useEditor((state) => state.status);
  const jobs = useEditor((state) => state.jobs);
  const project = useEditor((state) => state.project);
  const open = useEditor((state) => state.open);
  const exportId = useEditor((state) => state.exportId);
  const setPreview = useEditor((state) => state.setPreview);
  const setError = useEditor((state) => state.setError);
  const setStatus = useEditor((state) => state.setStatus);
  const setExportId = useEditor((state) => state.setExportId);
  const isSelectedProject = useCallback(
    (candidate: string) => selectedProjectId.current === candidate,
    [],
  );

  const go = useCallback((id: string | null) => {
    selectedProjectId.current = id;
    setProjectId(id);
    setTitle("");
    setExportUrl(null);
    setExporting(false);
    exportPending.current = false;
    setPreviewId(null);
    previewRequest.current += 1;
    writeProject(id);
  }, []);

  useEffect(() => {
    if (!projectId) return undefined;
    let disconnect: (() => void) | undefined;
    let stopJobs: (() => void) | undefined;
    let disposed = false;
    const current = () => !disposed && isSelectedProject(projectId);
    void (async () => {
      try {
        const result = await api.inspect(projectId);
        if (!current()) return;
        setTitle(result.project.title);
        open(projectId, result.state, result.operations.map((entry) => entry.operation));
        disconnect = connect(projectId, current);
        const stop = await pollJobs(projectId, 900, current);
        if (!current()) stop();
        else stopJobs = stop;
      } catch (problem) {
        if (current()) setError((problem as Error).message);
      }
    })();
    return () => {
      disposed = true;
      disconnect?.();
      stopJobs?.();
    };
  }, [projectId, isSelectedProject, open, setError]);

  useEffect(() => {
    setExportUrl(null);
    if (useEditor.getState().status?.startsWith("MP4 ready")) setStatus(null);
  }, [project?.version, setStatus]);

  useEffect(() => {
    if (!projectId || !isSelectedProject(projectId) || project?.project_id !== projectId) return;
    const finished = renderJobFor(jobs, previewId, "preview");
    if (finished?.status === "COMPLETED" && finished.artifact) {
      const nodeId = finished.output_id
        ?? finished.artifact!.split(/[\\/]/).pop()!.replace(/\.[^.]+$/, "");
      if (finished.kind !== "render:master") setPreview(api.artifactUrl(nodeId));
    } else if (finished?.status === "FAILED" || finished?.status === "CANCELLED") {
      setPreviewId(null);
      setError(finished.error?.message ?? "Preview render failed. Try Preview again.");
    }
    if (!exportId) return;
    const exportJob = renderJobFor(jobs, exportId, "master");
    if (!exportJob) return;
    if (exportJob.status === "RUNNING" || exportJob.status === "QUEUED") {
      const percent = Math.round((exportJob.progress || 0) * 100);
      setStatus(percent ? `Exporting master… ${percent}%` : "Exporting master…");
      return;
    }
    if (exportJob.status === "COMPLETED" && exportJob.artifact) {
      const nodeId = exportJob.output_id
        ?? exportJob.artifact.split(/[\\/]/).pop()!.replace(/\.[^.]+$/, "");
      downloadMaster(nodeId, title);
      setExportUrl(api.artifactUrl(nodeId, true, fileTitle(title)));
      setExportId(null);
      setExporting(false);
      exportPending.current = false;
      setStatus("MP4 ready — download started. Use the link to download again.");
      setError(null);
      return;
    }
    if (exportJob.status === "FAILED" || exportJob.status === "CANCELLED") {
      setExportId(null);
      setExporting(false);
      exportPending.current = false;
      setStatus(null);
      setError(exportJob.error?.message ?? "Export failed.");
    }
  }, [jobs, previewId, exportId, title, projectId, project?.project_id, isSelectedProject,
    setPreview, setExportId, setStatus, setError]);

  const render = useCallback(async () => {
    if (!projectId) return;
    const request = ++previewRequest.current;
    setPreviewId(null);
    setPreview(null);
    try {
      const result = await api.render(projectId, "preview", false);
      if (!isSelectedProject(projectId) || request !== previewRequest.current) return;
      setPreviewId(result.work.output_id);
      if (result.cached || result.artifact) {
        setPreview(api.artifactUrl(result.work.output_id));
      }
    } catch (problem) {
      if (isSelectedProject(projectId) && request === previewRequest.current) setError((problem as Error).message);
    }
  }, [projectId, isSelectedProject, setPreview, setError]);

  useEffect(() => {
    if (!projectId || project?.project_id !== projectId) return;
    const store = useEditor.getState();
    if (store.ingestKey === projectId) return;
    const files = store.ingestQueued;
    if (!files.length) return;
    store.markIngestStarted(projectId);
    void (async () => {
      const setStatus = useEditor.getState().setStatus;
      let imported = 0;
      for (const [index, file] of files.entries()) {
        if (!isSelectedProject(projectId)) return;
        setStatus(`Storing ${index + 1} of ${files.length} — ${file.name}`);
        try {
          await api.uploadMedia(projectId, file, true);
          imported += 1;
        } catch (problem) {
          if (!isSelectedProject(projectId)) return;
          useEditor.getState().setError((problem as Error).message);
        }
      }
      if (!isSelectedProject(projectId)) return;
      setStatus(`${imported} of ${files.length} videos imported. ${imported ? "Drag shots on the timeline to arrange your film." : "Check the error and try importing again."}`);
      if (!imported) return;
      try {
        await render();
      } catch (problem) {
        if (!isSelectedProject(projectId)) return;
        setStatus(null);
        useEditor.getState().setError((problem as Error).message);
      }
    })();
  }, [projectId, project?.project_id, isSelectedProject, render]);

  const exportFilm = useCallback(async () => {
    if (!projectId || exportPending.current) return;
    exportPending.current = true;
    setExporting(true);
    setExportUrl(null);
    setStatus("Exporting master…");
    setError(null);
    try {
      const result = await api.render(projectId, "master", false);
      if (!isSelectedProject(projectId)) return;
      const nodeId = result.work.output_id;
      if (result.cached || result.artifact) {
        downloadMaster(nodeId, title);
        setExportUrl(api.artifactUrl(nodeId, true, fileTitle(title)));
        setExporting(false);
        exportPending.current = false;
        setStatus("MP4 ready — download started. Use the link to download again.");
        return;
      }
      setExportId(nodeId);
    } catch (problem) {
      if (!isSelectedProject(projectId)) return;
      setExporting(false);
      exportPending.current = false;
      setStatus(null);
      setError((problem as Error).message);
    }
  }, [projectId, title, isSelectedProject, setError, setStatus, setExportId]);

  const undo = useCallback(async () => {
    if (!projectId) return;
    try {
      await api.undo(projectId, 1);
      if (isSelectedProject(projectId)) await render();
    } catch (problem) {
      if (isSelectedProject(projectId)) setError((problem as Error).message);
    }
  }, [projectId, isSelectedProject, setError, render]);

  if (!projectId) return <Launch onOpen={go} />;

  return (
    <div className="app">
      <TopBar title={title} onHome={() => go(null)} onRender={render} onExport={exportFilm} onUndo={undo} exporting={exporting} />
      {status ? <p className="process" role="status">{status} {exportUrl ? <a href={exportUrl} download={fileTitle(title)}>Download MP4</a> : null}</p> : null}
      {error ? <p className="error">{error}</p> : null}
      <div className="stage">
        <ShotPanel key={projectId} projectId={projectId} onMutate={() => void render()} />
        <Preview />
        <Studio projectId={projectId} onMutate={() => void render()} />
      </div>
      <div className="timeline">
        <Timeline key={projectId} onMutate={() => void render()} />
        <div className="timeline__intents">
          <IntentBar projectId={projectId} />
        </div>
      </div>
    </div>
  );
}
