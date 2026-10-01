import { useEffect, useRef, useState } from "react";
import { api, APIError } from "../state/api";
import { findClip, useEditor } from "../state/store";
import { flowKey, flowStale, loadFlow, proposalMatches, statusText } from "../state/vfx";
import type { VFXFlow, VFXReceipt, VFXRequest } from "../state/vfx";
import { VFXReview } from "./VFXReview";

function restore(projectId: string) {
  try { return loadFlow(sessionStorage, projectId); } catch { return null; }
}

export function VFXPanel({ projectId }: { projectId: string }) {
  const mirroredProject = useEditor((state) => state.project);
  const project = mirroredProject?.project_id === projectId ? mirroredProject : null;
  const selectedClip = useEditor((state) => state.selectedClipId);
  const selectedMedia = useEditor((state) => state.selectedMediaId);
  const [flow, setFlow] = useState<VFXFlow | null>(() => restore(projectId));
  const [script, setScript] = useState(flow?.request.script ?? project?.intent?.prompt ?? "");
  const [observations, setObservations] = useState(flow?.request.sources[0]?.observations[0]?.text ?? "");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const submitting = useRef(false);
  const initializedScript = useRef(!!flow);
  const found = findClip(project, selectedClip);
  const media = project?.media[found?.clip.media_id ?? selectedMedia ?? ""];
  const start = found?.clip.source_start_s ?? 0;
  const end = found?.clip.source_end_s ?? media?.probe.duration_s ?? 0;
  const requestId = flow?.request.request_id;
  const status = flow?.receipt?.status;
  const stale = flowStale(flow, project?.version ?? -1);
  const proposal = flow?.receipt?.proposals?.[0];
  const waiting = status === "queued" || status === "running" || busy;

  useEffect(() => {
    if (project && !initializedScript.current) {
      initializedScript.current = true;
      setScript(project.intent?.prompt ?? "");
    }
  }, [project]);

  function store(next: VFXFlow) {
    try { sessionStorage.setItem(flowKey(projectId), JSON.stringify(next)); }
    catch { setNotice("Refresh recovery is unavailable in this browser."); }
    setFlow(next);
  }

  useEffect(() => {
    if (!requestId || status === "unavailable" || (submitting.current && !status)) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function inspect() {
      try {
        const receipt = await api.getVFX(projectId, requestId!);
        if (cancelled) return;
        setFlow((current) => {
          if (!current || current.request.request_id !== receipt.request_id) return current;
          const next = { ...current, receipt };
          try { sessionStorage.setItem(flowKey(projectId), JSON.stringify(next)); } catch { /* Request ID remains saved. */ }
          return next;
        });
        setNotice(null);
        if (receipt.status === "queued" || receipt.status === "running") timer = setTimeout(inspect, 1500);
      } catch (error) {
        if (cancelled) return;
        setNotice(error instanceof APIError && error.status === 404
          ? "This request is not recorded on the server. No automatic resubmission was made."
          : "Could not check this request. Use Check status to reconnect; no new request will be sent.");
      }
    }
    void inspect();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [projectId, requestId, status, project]);

  async function plan() {
    if (submitting.current || waiting || !project || !media || !script.trim() || !observations.trim()) return;
    submitting.current = true;
    setBusy(true);
    setNotice(null);
    const request: VFXRequest = {
      request_id: crypto.randomUUID(), expected_version: project.version, script: script.trim(),
      sources: [{ media_id: media.media_id, source_sha256: media.sha256, source_start_s: start,
        source_end_s: end, observations: [{ source: "operator notes", text: observations.trim() }] }],
    };
    // Save identity before submitting. Refresh or a lost response must never send another paid request.
    try { sessionStorage.setItem(flowKey(projectId), JSON.stringify({ request, receipt: null })); }
    catch {
      setNotice("The browser could not save the request. Enable session storage before requesting effects.");
      submitting.current = false; setBusy(false); return;
    }
    setFlow({ request, receipt: null });
    try { store({ request, receipt: await api.planVFX(projectId, request) }); }
    catch (error) {
      const receipt: VFXReceipt = { schema_version: 1, request_id: request.request_id,
        project_version: request.expected_version, status: error instanceof APIError ? "failed" : "uncertain",
        generated: false, placed: false };
      store({ request, receipt });
      setNotice((error as Error).message);
    } finally { submitting.current = false; setBusy(false); }
  }

  async function check() {
    if (!flow || busy) return;
    setBusy(true);
    try { store({ ...flow, receipt: await api.getVFX(projectId, flow.request.request_id) }); setNotice(null); }
    catch (error) { setNotice((error as Error).message); }
    finally { setBusy(false); }
  }

  async function review() {
    if (!flow || !proposal || busy) return;
    setBusy(true);
    try {
      const receipt = await api.getVFX(projectId, flow.request.request_id);
      store({ ...flow, receipt });
      if (!proposalMatches(receipt, flow.request, proposal)) {
        setNotice("This proposal no longer matches the current project. Request a current proposal before review.");
        return;
      }
      setNotice(null);
      setReviewing(true);
    } catch (error) {
      setNotice(`${(error as Error).message}. The review was not opened.`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="vfx-panel" aria-label="AI effects">
      <div className="vfx-panel__heading"><h3>AI effects</h3><span className="label">Real footage</span></div>
      <p className="studio__hint">Plan an addition to a shot, then review the generated clip before importing it.</p>
      <p className="vfx-source">{media ? `${media.name} · ${start.toFixed(2)}-${end.toFixed(2)} s` : "Select a timeline clip or source in Media."}</p>
      <label className="vfx-field">Scene script or creative brief
        <textarea rows={3} maxLength={12000} value={script} onChange={(event) => setScript(event.target.value)} disabled={waiting} />
      </label>
      <label className="vfx-field">What happens in this footage?
        <textarea rows={3} maxLength={2000} value={observations} onChange={(event) => setObservations(event.target.value)} disabled={waiting}
          placeholder="Describe the person, action and background." />
      </label>
      <button className="btn btn--primary" disabled={waiting || !media || !script.trim() || !observations.trim()}
        onClick={() => void plan()}>{waiting ? "Planning…" : flow ? "Request new effect ideas" : "Request effect ideas"}</button>
      {flow ? <p className="vfx-status" role="status">{stale ? statusText("stale") : status ? statusText(status) : statusText("uncertain")}</p> : null}
      {notice ? <p className="vfx-notice" role="alert">{notice}</p> : null}
      {flow && status !== "unavailable" ? <button className="btn btn--tiny" disabled={busy} onClick={() => void check()}>Check status</button> : null}
      {proposal && !stale && status === "proposal" ? (
        <div className="vfx-proposal">
          {flow?.receipt?.provenance?.source === "simulated_provider" ? <p className="vfx-notice">Simulated proposal - offline test only.</p> : null}
          <h4>{proposal.decision === "none" ? "Keep this shot natural" : "Proposed addition"}</h4>
          <p>{proposal.reason}</p>
          {proposal.decision === "augment" ? <>
            <p className="num">Effect: {proposal.effect_start_s?.toFixed(2)}-{proposal.effect_end_s?.toFixed(2)} s in the source</p>
            <textarea aria-label="Effect prompt" rows={5} readOnly value={proposal.prompt} />
            <p className="studio__hint">Keep the filmed people, action, camera motion, geometry, text and original audio.</p>
            <div className="vfx-actions">
              <button className="btn btn--tiny" onClick={() => void navigator.clipboard.writeText(proposal.prompt)
                .then(() => setNotice("Prompt copied. Generate the clip in ChatCut, then return to review it."))
                .catch(() => setNotice("Select and copy the prompt above."))}>Copy prompt</button>
              <button className="btn btn--tiny" disabled={busy} onClick={() => void review()}>Import generated clip</button>
            </div>
          </> : null}
        </div>
      ) : null}
      {reviewing && flow && proposal && !stale ? <VFXReview projectId={projectId} request={flow.request}
        proposal={proposal} onClose={() => setReviewing(false)} onImported={(id) => {
          setReviewing(false); setNotice("Reviewed clip imported into Media. Use Place on timeline when ready.");
          useEditor.getState().selectMedia(id);
        }} /> : null}
    </section>
  );
}
