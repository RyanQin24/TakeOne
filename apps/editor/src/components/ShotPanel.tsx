import { useCallback, useRef, useState } from "react";
import { api } from "../state/api";
import { score } from "../lib/timecode";
import { useEditor } from "../state/store";

const ACCEPT = "video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.webm,.mkv,.avi";

export function ShotPanel({ projectId, onMutate }: { projectId: string; onMutate: () => void }) {
  const project = useEditor((state) => state.project);
  const selected = useEditor((state) => state.selectedMediaId);
  const selectMedia = useEditor((state) => state.selectMedia);
  const setError = useEditor((state) => state.setError);
  const [over, setOver] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const sending = useRef(false);

  const send = useCallback(async (list: FileList | File[] | null) => {
    if (!list || sending.current) return;
    const files = Array.from(list).filter(
      (file) => file.type.startsWith("video/") || /\.(mp4|mov|m4v|webm|mkv|avi)$/i.test(file.name),
    );
    if (!files.length) { setError("Choose a video file (MP4, MOV, WebM, MKV or AVI)."); return; }
    sending.current = true;
    const current = () => useEditor.getState().projectId === projectId;
    let imported = false;
    try {
      for (const [index, file] of files.entries()) {
        if (!current()) return;
        setStatus(`Sending ${index + 1}/${files.length}`);
        await api.uploadMedia(projectId, file, true);
        imported = true;
      }
      if (current()) setError(null);
    } catch (problem) {
      if (current()) setError((problem as Error).message);
    } finally {
      sending.current = false;
      setStatus(null);
      if (imported && current()) onMutate();
    }
  }, [projectId, setError, onMutate]);

  if (!project) return null;
  const items = Object.values(project.media);
  const onTimeline = new Set(
    project.timeline.tracks.flatMap((track) => track.clips.map((clip) => clip.media_id)),
  );

  return (
    <aside className="panel panel--left">
      <div className="panel__head">
        <h2 className="label panel__title">Media · {items.length}</h2>
        <label className="btn btn--tiny" role="button" tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault(); event.currentTarget.querySelector("input")?.click();
            }
          }}>
          {status ?? "Import videos"}
          <input
            type="file"
            accept={ACCEPT}
            multiple
            hidden
            disabled={status !== null}
            onChange={(event) => {
              void send(event.target.files);
              event.target.value = "";
            }}
          />
        </label>
      </div>

      <div
        className={over ? "dropzone dropzone--compact dropzone--over" : "dropzone dropzone--compact"}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          void send(event.dataTransfer.files);
        }}
      >
        <span role="status">{status ?? "Drop videos from your computer here"}</span>
      </div>

      {items.map((item) => {
        const selection = project.selection[item.media_id];
        const state = selection?.state ?? "pending";
        return (
          <div key={item.media_id} className="shot-wrap">
            <button
              className={[
                "shot",
                state === "rejected" ? "shot--rejected" : "",
                selected === item.media_id ? "shot--selected" : "",
              ].join(" ")}
              onClick={() => selectMedia(selected === item.media_id ? null : item.media_id)}
            >
              <div className="shot__frame">
                {item.thumbnail_path ? (
                  <img src={api.mediaUrl(projectId, item.media_id, "thumbnail")} alt="" />
                ) : null}
                <i className={`shot__state shot__state--${state}`} />
              </div>
              <div className="shot__body">
                <span className="shot__name">{item.name}</span>
                <span className="shot__score num">{score(selection?.score)}</span>
              </div>
              {selection?.reason ? <p className="shot__reason">{selection.reason}</p> : null}
              {state === "analyzing" ? <p className="shot__reason">Reading this take…</p> : null}
            </button>
            {!onTimeline.has(item.media_id) ? (
              <button
                className="btn btn--tiny shot__place"
                onClick={() => api.placeMedia(projectId, item.media_id).then(() => {
                  if (useEditor.getState().projectId === projectId) onMutate();
                }).catch((problem) => {
                  if (useEditor.getState().projectId === projectId) setError((problem as Error).message);
                })}
              >
                Place on timeline
              </button>
            ) : null}
          </div>
        );
      })}
    </aside>
  );
}
