import { useCallback, useEffect, useState } from "react";
import { api } from "../state/api";
import { useEditor } from "../state/store";
import { TakeOneNav } from "./TakeOneNav";
import { CinematicAtmosphere } from "./CinematicAtmosphere";
import { SoundwaveVisualizer } from "./SoundwaveVisualizer";

interface Props {
  onOpen: (projectId: string) => void;
}

const ACCEPT = "video/mp4,video/quicktime,video/webm,video/x-matroska,video/x-msvideo,.mp4,.mov,.webm,.mkv,.avi";

const INSPIRATION_PROMPTS = [
  "A high-speed camera track through darkness that snaps into brilliant neon clarity.",
  "Warm 35mm golden hour portrait with gentle camera drift and deliberate pacing.",
  "Tense noir two-shot with sharp angle changes and sudden rhythmic momentum.",
];

export function Launch({ onOpen }: Props) {
  const [prompt, setPrompt] = useState("Make a mysterious luxury introduction that becomes powerful.");
  const [existing, setExisting] = useState<{ project_id: string; title: string; updated_utc: string }[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);

  useEffect(() => {
    api.projects().then((result) => setExisting(result.projects)).catch(() => setExisting([]));
  }, []);

  const takeFiles = useCallback((list: FileList | File[] | null) => {
    if (!list) return;
    const next = Array.from(list).filter((file) => file.type.startsWith("video/") || /\.(mp4|mov|m4v|webm|mkv|avi)$/i.test(file.name));
    if (next.length) setFiles((current) => [...current, ...next]);
  }, []);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const id = `film-${Date.now().toString(36)}`;
      const title = prompt.slice(0, 80) || "Untitled film";
      await api.createProject(id, title, {
        prompt,
        target_duration_s: Math.max(12, files.length * 3),
        aspect_ratio: "16:9",
      });
      if (files.length) useEditor.getState().queueIngest(files);
      onOpen(id);
    } catch (problem) {
      setError((problem as Error).message);
    } finally {
      setBusy(false);
      setStatus(null);
    }
  };

  const handleSpotlight = (e: React.MouseEvent<HTMLElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty("--spot-x", `${e.clientX - rect.left}px`);
    e.currentTarget.style.setProperty("--spot-y", `${e.clientY - rect.top}px`);
  };

  return (
    <div className="launch">
      <CinematicAtmosphere />
      <header className="launch__bar">
        <span className="launch__mark" aria-hidden>T/1</span>
        <span className="launch__wordmark">TAKE ONE</span>
        <span className="launch__rule" aria-hidden />
        <span className="launch__where"><b>Edit</b><small>Finishing suite</small></span>
        <div className="launch__telemetry">
          <span className="telemetry__dot" aria-hidden="true" />
          <span className="telemetry__label">MP4 EXPORT</span>
          <SoundwaveVisualizer active={!busy} />
        </div>
        <TakeOneNav />
      </header>
      <div className="launch__inner">
        <div className="launch__kicker">
          <span className="badge-pill">LOCAL VIDEO EDITOR</span>
          <span className="kicker-meta">Import · Arrange · Export MP4</span>
        </div>
        <h1 className="launch__title">What should this film feel like?</h1>
        <p className="launch__lead">
          Import videos from your computer, drag shots into order, then export an MP4.
          Originals are copied into a local folder for this film. AI editing is optional in Studio.
        </p>

        <div className="viewfinder-container">
          <span className="vf-bracket vf-tl" aria-hidden="true" />
          <span className="vf-bracket vf-tr" aria-hidden="true" />
          <span className="vf-bracket vf-bl" aria-hidden="true" />
          <span className="vf-bracket vf-br" aria-hidden="true" />
          <div
            className={over ? "dropzone dropzone--over" : "dropzone"}
            onMouseMove={handleSpotlight}
            onDragOver={(event) => {
              event.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(event) => {
              event.preventDefault();
              setOver(false);
              takeFiles(event.dataTransfer.files);
            }}
          >
            <span className="dropzone__mark">+</span>
            <span className="dropzone__title">Drop clips here</span>
            <span className="label">MP4, MOV, WebM, MKV</span>
            <label className="btn btn--ghost" role="button" tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault(); event.currentTarget.querySelector("input")?.click();
                }
              }}>
              Import videos
              <input
                type="file"
                accept={ACCEPT}
                multiple
                hidden
                onChange={(event) => {
                  takeFiles(event.target.files);
                  event.target.value = "";
                }}
              />
            </label>
          </div>
        </div>

        {files.length ? (
          <ul className="file-chips">
            {files.map((file, index) => (
              <li key={`${file.name}-${file.size}-${index}`} className="file-chip">
                <span>{file.name}</span>
                <button type="button" onClick={() => setFiles((current) => current.filter((_, i) => i !== index))}>
                  ×
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        <div className="launch__field-wrap">
          <input
            className="launch__field"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && !busy && create()}
            placeholder="A slow, expensive reveal that snaps into power…"
          />
          <div className="launch__chips">
            {INSPIRATION_PROMPTS.map((item, i) => (
              <button
                key={i}
                type="button"
                className="launch__chip"
                onClick={() => setPrompt(item)}
              >
                {item.slice(0, 48)}…
              </button>
            ))}
          </div>
        </div>

        <div className="launch__row">
          <span className="label">
            {existing.length} project{existing.length === 1 ? "" : "s"}
            {files.length ? ` · ${files.length} clip${files.length === 1 ? "" : "s"} ready` : ""}
          </span>
          <button className="btn btn--primary" onClick={create} disabled={busy}>
            {busy ? status ?? "Creating…" : files.length ? "Create film with videos" : "Create film"}
          </button>
        </div>
        {error ? <p className="error">{error}</p> : null}

        <div className="launch__list">
          {existing.slice(0, 8).map((item) => (
            <button
              key={item.project_id}
              className="project-card"
              onMouseMove={handleSpotlight}
              onClick={() => onOpen(item.project_id)}
            >
              <span className="project-card__title">{item.title}</span>
              <span className="num label">{item.project_id}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
