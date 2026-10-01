import { useEffect, useReducer, useRef, useState } from "react";
import { api } from "../state/api";
import { useEditor } from "../state/store";
import { PRESERVATION, proposalMatches } from "../state/vfx";
import type { DerivativeMetadata, Preservation, VFXProposal, VFXRequest } from "../state/vfx";

const LABELS: Record<Preservation, string> = {
  people: "Real people and their appearance", action: "Original action and performance",
  camera_motion: "Camera movement and framing", geometry: "Scene geometry and continuity",
  text_logos: "Text and logos",
};

export type ReviewPlaybackState = "idle" | "playing" | "invalid" | "complete";
export type ReviewPlayback = { source: ReviewPlaybackState; candidate: ReviewPlaybackState };
export type ReviewPlaybackAction =
  | { type: "reset" }
  | { type: "start" | "invalidate" | "complete"; media: keyof ReviewPlayback };

export const EMPTY_REVIEW_PLAYBACK: ReviewPlayback = { source: "idle", candidate: "idle" };

export function reviewPlayback(
  state: ReviewPlayback,
  action: ReviewPlaybackAction,
): ReviewPlayback {
  if (action.type === "reset") return EMPTY_REVIEW_PLAYBACK;
  if (action.type === "complete" && state[action.media] !== "playing") return state;
  const next = action.type === "start" ? "playing"
    : action.type === "invalidate" ? "invalid" : "complete";
  return { ...state, [action.media]: next };
}

export function VFXReview({ projectId, request, proposal, onClose, onImported }: {
  projectId: string; request: VFXRequest; proposal: VFXProposal;
  onClose: () => void; onImported: (mediaId: string) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const sourceVideo = useRef<HTMLVideoElement>(null);
  const candidateVideo = useRef<HTMLVideoElement>(null);
  const source = useEditor((state) => state.project?.media[proposal.media_id]);
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [checks, setChecks] = useState<Partial<Record<Preservation | "audio", boolean>>>({});
  const [busy, setBusy] = useState(false);
  const importing = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [modelVersion, setModelVersion] = useState("");
  const [jobId, setJobId] = useState("");
  const [prompt, setPrompt] = useState(proposal.prompt);
  const [settings, setSettings] = useState("{}");
  const [cost, setCost] = useState("");
  const [unit, setUnit] = useState("credits");
  const [rights, setRights] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [notes, setNotes] = useState("");
  const [audio, setAudio] = useState<"reviewed" | "silent_source">("reviewed");
  const [space, setSpace] = useState("rec709");
  const [playback, dispatchPlayback] = useReducer(reviewPlayback, EMPTY_REVIEW_PLAYBACK);
  const played = playback.source === "complete" && playback.candidate === "complete";
  const span = proposal.source_end_s - proposal.source_start_s;

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  useEffect(() => {
    if (!file) return;
    const next = URL.createObjectURL(file);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [file]);
  useEffect(() => {
    dispatchPlayback({ type: "reset" });
    setChecks({});
  }, [projectId, proposal.media_id, proposal.source_start_s, proposal.source_end_s, url]);

  function choose(next: File | null) {
    sourceVideo.current?.pause(); candidateVideo.current?.pause();
    setFile(next); setChecks({}); dispatchPlayback({ type: "reset" }); setError(null);
  }

  function playbackError(message: string) {
    sourceVideo.current?.pause(); candidateVideo.current?.pause();
    dispatchPlayback({ type: "reset" }); setChecks({}); setError(message);
  }

  async function compare() {
    const original = sourceVideo.current;
    const candidate = candidateVideo.current;
    if (!original || !candidate) return;
    original.currentTime = proposal.source_start_s;
    candidate.currentTime = 0;
    dispatchPlayback({ type: "reset" });
    // One audible stream at a time, so the comparison does not double the sound.
    original.muted = true;
    try { await Promise.all([original.play(), candidate.play()]); }
    catch { playbackError("This browser could not play the comparison. Try a browser-compatible MP4."); }
  }

  const canImport = !!file && played && [...PRESERVATION, "audio"].every((key) => checks[key as keyof typeof checks])
    && !!provider.trim() && !!model.trim() && !!jobId.trim() && !!prompt.trim() && !!rights.trim()
    && !!reviewer.trim() && !!notes.trim() && !!unit.trim() && !busy;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canImport || !file || importing.current) return;
    const current = useEditor.getState().project;
    if (current?.project_id !== projectId || current.version !== request.expected_version) {
      setError("The project changed. Close this review and request a current proposal."); return;
    }
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(settings) as Record<string, unknown>;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
      if (cost.trim() && (!Number.isFinite(Number(cost)) || Number(cost) < 0)) throw new Error();
    } catch { setError("Settings must be a JSON object and any reported cost must be a non-negative number."); return; }
    const metadata: DerivativeMetadata = {
      source_media_id: proposal.media_id, source_sha256: proposal.source_sha256,
      source_start_s: proposal.source_start_s, source_end_s: proposal.source_end_s,
      output_source_space: space, provider: provider.trim(), model: model.trim(),
      model_version: modelVersion.trim() || "not-reported", job_id: jobId.trim(), prompt: prompt.trim(),
      settings: { ...parsed, proposal_request_id: request.request_id },
      cost: { amount: cost.trim() ? Number(cost) : null, unit: unit.trim(), status: cost.trim() ? "reported" : "unknown" },
      rights_evidence: rights.trim(), review: { reviewer: reviewer.trim(), decision: "approved", notes: notes.trim(),
        preserved: Object.fromEntries(PRESERVATION.map((key) => [key, checks[key] === true])) as Record<Preservation, boolean>, audio },
    };
    importing.current = true; setBusy(true); setError(null);
    try {
      const receipt = await api.getVFX(projectId, request.request_id);
      if (!proposalMatches(receipt, request, proposal)) {
        setError("The proposal no longer matches the current project. Close this review and request a current proposal.");
        return;
      }
      onImported((await api.uploadDerivative(projectId, file, metadata)).media_id);
    } catch (problem) {
      setError(`${(problem as Error).message}. The clip was not approved by this response.`);
    }
    finally { importing.current = false; setBusy(false); }
  }

  return (
    <dialog className="vfx-review" ref={dialog} aria-labelledby="vfx-review-title"
      onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
      <form onSubmit={(event) => void submit(event)}>
        <header className="vfx-review__head"><div><p className="label">AI effects / Review</p>
          <h2 id="vfx-review-title">Keep the real take</h2>
          <p>{source?.name} · source {proposal.source_start_s.toFixed(2)}-{proposal.source_end_s.toFixed(2)} s</p></div>
          <button className="btn btn--tiny" type="button" disabled={busy} onClick={onClose}>Close</button></header>
        <label className="vfx-field">Generated clip
          <input type="file" accept=".mp4,.mov,.webm,.mkv,.avi,video/*" disabled={busy}
            onChange={(event) => choose(event.target.files?.[0] ?? null)} />
        </label>
        {file && url ? <>
          <div className="vfx-compare">
            <figure><figcaption>Original source</figcaption>
              <video ref={sourceVideo} src={api.mediaUrl(projectId, proposal.media_id, "original")} controls playsInline preload="metadata"
                onError={() => playbackError("The source cannot be played here. Close this review and verify the original media.")}
                onLoadedMetadata={(event) => {
                  dispatchPlayback({ type: "invalidate", media: "source" });
                  event.currentTarget.currentTime = proposal.source_start_s;
                }}
                onPlay={(event) => {
                  if (event.currentTarget.currentTime < proposal.source_start_s || event.currentTarget.currentTime >= proposal.source_end_s)
                    event.currentTarget.currentTime = proposal.source_start_s;
                  if (event.currentTarget.currentTime <= proposal.source_start_s + 0.05)
                    dispatchPlayback({ type: "start", media: "source" });
                }}
                onSeeking={() => dispatchPlayback({ type: "invalidate", media: "source" })}
                onSeeked={(event) => {
                  if (Math.abs(event.currentTarget.currentTime - proposal.source_start_s) <= 0.05)
                    dispatchPlayback({ type: "start", media: "source" });
                }}
                onTimeUpdate={(event) => {
                  if (event.currentTarget.currentTime >= proposal.source_end_s) {
                    event.currentTarget.pause();
                    dispatchPlayback({ type: "complete", media: "source" });
                  }
                }}
                onEnded={() => dispatchPlayback({ type: "complete", media: "source" })} />
            </figure>
            <figure><figcaption>Candidate · {file.name}</figcaption>
              <video key={url} ref={candidateVideo} src={url} controls playsInline preload="metadata"
                onError={() => playbackError("The candidate cannot be played here. Use a browser-compatible MP4 before reviewing it.")}
                onLoadedMetadata={(event) => {
                  dispatchPlayback({ type: "invalidate", media: "candidate" });
                  const duration = event.currentTarget.duration;
                  if (!Number.isFinite(duration) || Math.abs(duration - span) > 0.1)
                    setError(`Candidate length is ${duration.toFixed(2)} s; the source span is ${span.toFixed(2)} s. Import will verify exact compatibility.`);
                }}
                onPlay={(event) => {
                  if (event.currentTarget.currentTime <= 0.05)
                    dispatchPlayback({ type: "start", media: "candidate" });
                }}
                onSeeking={() => dispatchPlayback({ type: "invalidate", media: "candidate" })}
                onSeeked={(event) => {
                  if (event.currentTarget.currentTime <= 0.05)
                    dispatchPlayback({ type: "start", media: "candidate" });
                }}
                onEnded={() => dispatchPlayback({ type: "complete", media: "candidate" })} />
            </figure>
          </div>
          <button className="btn btn--tiny" type="button" onClick={() => void compare()} disabled={busy}>Play comparison</button>
          <p className="studio__hint">Comparison plays the candidate sound. Use each player's controls to listen to the original too. Inspect the whole clip before approving.</p>
        </> : null}
        <div className="vfx-review__columns">
          <fieldset disabled={busy || !played} className="vfx-checks"><legend>What stayed intact?</legend>
            {PRESERVATION.map((key) => <label key={key}><input type="checkbox" checked={checks[key] ?? false}
              onChange={(event) => setChecks({ ...checks, [key]: event.target.checked })} />{LABELS[key]}</label>)}
            <label><input type="checkbox" checked={checks.audio ?? false}
              onChange={(event) => setChecks({ ...checks, audio: event.target.checked })} />Original sound is preserved, or both clips are intentionally silent</label>
            <label className="vfx-field">Audio review<select value={audio} onChange={(event) => setAudio(event.target.value as typeof audio)}>
              <option value="reviewed">Original sound reviewed</option><option value="silent_source">Confirmed silent source and candidate</option>
            </select></label>
            <label className="vfx-field">Reviewed by<input required maxLength={200} value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></label>
            <label className="vfx-field">Review notes<textarea required maxLength={4000} rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
          </fieldset>
          <fieldset disabled={busy} className="vfx-fields"><legend>Generation receipt</legend>
            <div className="vfx-field-pair">
              <label className="vfx-field">Provider<input required maxLength={200} value={provider} onChange={(event) => setProvider(event.target.value)} placeholder="ChatCut" /></label>
              <label className="vfx-field">Model<input required maxLength={200} value={model} onChange={(event) => setModel(event.target.value)} /></label>
            </div>
            <label className="vfx-field">Job ID<input required maxLength={200} value={jobId} onChange={(event) => setJobId(event.target.value)} /></label>
            <label className="vfx-field">Actual generation prompt<textarea required maxLength={16000} rows={3} value={prompt} onChange={(event) => setPrompt(event.target.value)} /></label>
            <label className="vfx-field">Footage and generation rights<textarea required maxLength={4000} rows={2} value={rights} onChange={(event) => setRights(event.target.value)} placeholder="Who filmed it and what permits this use?" /></label>
            <details><summary>Settings, charge and color</summary>
              <label className="vfx-field">Model version, if reported<input maxLength={200} value={modelVersion} onChange={(event) => setModelVersion(event.target.value)} /></label>
              <label className="vfx-field">Actual settings (JSON)<textarea maxLength={16384} rows={3} value={settings} onChange={(event) => setSettings(event.target.value)} /></label>
              <div className="vfx-field-pair">
                <label className="vfx-field">Reported charge<input type="number" min={0} step="any" value={cost} onChange={(event) => setCost(event.target.value)} placeholder="Unknown" /></label>
                <label className="vfx-field">Charge unit<input maxLength={64} value={unit} onChange={(event) => setUnit(event.target.value)} /></label>
              </div>
              <label className="vfx-field">Output color space<select value={space} onChange={(event) => setSpace(event.target.value)}>
                <option value="rec709">Rec.709</option><option value="srgb">sRGB</option>
              </select></label>
            </details>
          </fieldset>
        </div>
        {error ? <p className="vfx-notice" role="alert">{error}</p> : null}
        <footer className="vfx-review__foot"><p className="studio__hint">Approval imports a reviewed copy into Media. Place it on the timeline separately.</p>
          <button className="btn btn--primary" type="submit" disabled={!canImport}>{busy ? "Verifying and importing…" : "Approve and import"}</button></footer>
      </form>
    </dialog>
  );
}
