import { useLayoutEffect, useRef, useState } from "react";
import { useEditor } from "../../state/store";
import { ClipView } from "./ClipView";
import { Ruler } from "./Ruler";
import { api } from "../../state/api";
import { dropPosition, reorderRequest } from "./reorder";

const MIN_SCALE = 12;

export function Timeline({ onMutate }: { onMutate: () => void }) {
  const project = useEditor((state) => state.project);
  const playhead = useEditor((state) => state.playhead);
  const lane = useRef<HTMLDivElement>(null);
  const [laneWidth, setLaneWidth] = useState(800);
  const [drag, setDrag] = useState<{ clipId: string; trackId: string; version: number } | null>(null);
  const [hint, setHint] = useState<{ index: number; time: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const move = async (clipId: string, trackId: string, index: number) => {
    if (!project || pending.current) return;
    const track = project.timeline.tracks.find((item) => item.track_id === trackId);
    if (!track || index < 0 || index >= track.clips.length || track.clips[index].clip_id === clipId) return;
    const projectId = project.project_id;
    pending.current = true;
    setBusy(true);
    try {
      await api.submit(projectId, reorderRequest(clipId, index));
      if (useEditor.getState().projectId !== projectId) return;
      useEditor.getState().setError(null);
      useEditor.getState().setPreview(null);
      onMutate();
    } catch (problem) {
      if (useEditor.getState().projectId === projectId) useEditor.getState().setError((problem as Error).message);
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };

  useLayoutEffect(() => {
    const element = lane.current;
    if (!element) return undefined;
    const observer = new ResizeObserver(([entry]) => setLaneWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, [project?.timeline.tracks.length]);

  if (!project) return null;

  const duration = Math.max(project.timeline.duration_s, 1);
  const scale = Math.max(MIN_SCALE, laneWidth / duration);
  const videoTracks = project.timeline.tracks.filter((track) => track.kind !== "audio");
  const clipById = new Map(
    project.timeline.tracks.flatMap((track) => track.clips.map((clip) => [clip.clip_id, clip])),
  );

  return (
    <section className="timeline">
      <p className="timeline__help" role="status">
        {busy ? "Saving clip position…" : "Drag clips to reorder · Alt + ← / → also moves a shot · Undo restores the previous cut"}
      </p>
      {!videoTracks.some((track) => track.clips.length) ? <p className="timeline__help">Import videos from your computer to start your timeline.</p> : null}
      <div className="timeline__scroll">
        {project.timeline.tracks.some((track) =>
          track.clips.some((clip) => clip.effects.length),
        ) ? (
          <div className="timeline__row">
            <span className="timeline__name">FX</span>
            <div className="timeline__lane timeline__lane--fx">
              {project.timeline.tracks.flatMap((track) =>
                track.clips.flatMap((clip) =>
                  clip.effects.map((effect) => {
                    const start = clip.timeline_start_s + (effect.start_s ?? 0);
                    const end = effect.end_s === null ? clip.timeline_end_s : clip.timeline_start_s + effect.end_s;
                    return (
                      <span
                        key={`${clip.clip_id}-${effect.instance_id}`}
                        className="effect-strip"
                        style={{ left: start * scale, width: Math.max(24, (end - start) * scale) }}
                      >
                        {effect.effect_id.replace(/_/g, " ").toUpperCase()}
                      </span>
                    );
                  }),
                ),
              )}
            </div>
          </div>
        ) : null}

        {videoTracks.map((track, index) => (
          <div className="timeline__row" key={track.track_id}>
            <span className="timeline__name">{track.track_id}</span>
            <div className="timeline__lane" ref={index === 0 ? lane : undefined}
              onDragOver={(event) => {
                if (!drag || drag.trackId !== track.track_id || busy) return;
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
                setHint(dropPosition(track.clips, drag.clipId, (event.clientX - event.currentTarget.getBoundingClientRect().left) / scale));
              }}
              onDrop={(event) => {
                event.preventDefault();
                if (drag?.trackId === track.track_id && drag.version === project.version) {
                  const position = dropPosition(track.clips, drag.clipId, (event.clientX - event.currentTarget.getBoundingClientRect().left) / scale);
                  void move(drag.clipId, track.track_id, position.index);
                } else if (drag) {
                  useEditor.getState().setError("The timeline changed while dragging. Please try again.");
                }
                setDrag(null);
                setHint(null);
              }}>
              {track.clips.map((clip, clipIndex) => (
                <ClipView key={clip.clip_id} clip={clip} scale={scale} laneWidth={laneWidth}
                  disabled={busy || project.finalized}
                  onDragStart={(event) => {
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", clip.clip_id);
                    useEditor.getState().selectClip(clip.clip_id);
                    setDrag({ clipId: clip.clip_id, trackId: track.track_id, version: project.version });
                  }}
                  onDragEnd={() => { setDrag(null); setHint(null); }}
                  onStep={(direction) => void move(clip.clip_id, track.track_id, clipIndex + direction)} />
              ))}
              {drag?.trackId === track.track_id && hint ? <span className="timeline__drop" style={{ left: hint.time * scale }} /> : null}
              {project.timeline.transitions.map((transition) => {
                const incoming = clipById.get(transition.to_clip_id);
                if (!incoming) return null;
                return (
                  <span
                    key={transition.transition_id}
                    className="transition"
                    style={{
                      left: incoming.timeline_start_s * scale,
                      width: Math.max(14, transition.duration_s * scale),
                    }}
                  >
                    {transition.effect_id.slice(0, 4).toUpperCase()}
                  </span>
                );
              })}
              {index === 0 ? (
                <span className="playhead" style={{ left: playhead * scale }} />
              ) : null}
            </div>
          </div>
        ))}

        {project.timeline.markers.length || project.audio.length ? (
          <div className="timeline__row">
            <span className="timeline__name">A1</span>
            <div className="timeline__lane timeline__lane--audio">
              {project.audio.map((event) => (
                <span
                  key={event.event_id}
                  className="effect-strip"
                  style={{
                    left: event.timeline_start_s * scale,
                    width: Math.max(18, event.duration_s * scale),
                  }}
                >
                  {event.kind.toUpperCase()}
                </span>
              ))}
              {project.timeline.markers.map((marker) => (
                <span
                  key={marker.marker_id}
                  className={marker.kind === "impact" ? "marker marker--impact" : "marker"}
                  style={{ left: marker.time_s * scale }}
                />
              ))}
            </div>
          </div>
        ) : null}
      </div>
      <p className="timeline__help">Moving shots closes gaps. Transitions between separated shots are removed; music and markers stay at their current times.</p>
      <Ruler duration={duration} scale={scale} />
    </section>
  );
}
