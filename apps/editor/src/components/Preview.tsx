import { useEffect, useRef } from "react";
import { useEditor } from "../state/store";
import { timecode } from "../lib/timecode";

export function Preview() {
  const previewUrl = useEditor((state) => state.previewUrl);
  const comparing = useEditor((state) => state.comparing);
  const setComparing = useEditor((state) => state.setComparing);
  const setPlayhead = useEditor((state) => state.setPlayhead);
  const playhead = useEditor((state) => state.playhead);
  const project = useEditor((state) => state.project);
  const status = useEditor((state) => state.status);
  const video = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const element = video.current;
    if (!element) return undefined;
    const onTime = () => setPlayhead(element.currentTime);
    element.addEventListener("timeupdate", onTime);
    return () => element.removeEventListener("timeupdate", onTime);
  }, [setPlayhead, previewUrl]);

  const fps = project?.render_settings.fps ?? 30;

  return (
    <section className="preview">
      <div className="preview__frame">
        {previewUrl ? (
          <video ref={video} src={previewUrl} controls preload="auto" />
        ) : (
          <span className="preview__empty">
            {status ??
              (project?.timeline.tracks.some((track) => track.clips.length)
                ? "Render a preview when you want to watch the cut"
                : "The AI will build the cut here — watch the timeline")}
          </span>
        )}
        {previewUrl ? (
          <span className="preview__badge">{comparing ? "Original" : "Preview render"}</span>
        ) : null}
      </div>
      <div className="preview__bar">
        <span className="num label">{timecode(playhead, fps)}</span>
        <span className="label">
          of {timecode(project?.timeline.duration_s ?? 0, fps)}
        </span>
        <div className="topbar__spacer" />
        <button
          className="btn btn--ghost"
          onPointerDown={() => setComparing(true)}
          onPointerUp={() => setComparing(false)}
          onPointerLeave={() => setComparing(false)}
        >
          Hold for original
        </button>
      </div>
    </section>
  );
}
