import { useEffect } from "react";
import type { Clip } from "../../state/types";
import { useEditor } from "../../state/store";
import { SpeedCurveTrace } from "./SpeedCurve";

interface Props {
  clip: Clip;
  scale: number;
  laneWidth: number;
  disabled: boolean;
  onDragStart: (event: React.DragEvent<HTMLButtonElement>) => void;
  onDragEnd: () => void;
  onStep: (direction: number) => void;
}

export function ClipView({ clip, scale, laneWidth, disabled, onDragStart, onDragEnd, onStep }: Props) {
  const selectedClipId = useEditor((state) => state.selectedClipId);
  const selectClip = useEditor((state) => state.selectClip);
  const entering = useEditor((state) => state.entering.has(clip.clip_id));
  const settle = useEditor((state) => state.settle);

  useEffect(() => {
    if (!entering) return undefined;
    const timer = window.setTimeout(() => settle(clip.clip_id), 400);
    return () => window.clearTimeout(timer);
  }, [entering, clip.clip_id, settle]);

  const left = clip.timeline_start_s * scale;
  const width = Math.max(6, clip.timeline_duration_s * scale);
  const badges: string[] = [];
  if (clip.color.look_id) badges.push(clip.color.look_id.replace(/_/g, " "));
  if (clip.color.matched_to) badges.push("matched");
  if (clip.effects.length) badges.push(`${clip.effects.length} fx`);

  return (
    <button
      className={[
        "clip",
        selectedClipId === clip.clip_id ? "clip--selected" : "",
        entering ? "clip--entering" : "",
      ].join(" ")}
      style={{ left, width }}
      draggable={!disabled}
      aria-disabled={disabled}
      aria-label={`${clip.label ?? clip.clip_id}. Drag to reorder, or use Alt and arrow keys.`}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onKeyDown={(event) => {
        if (!disabled && event.altKey && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
          event.preventDefault();
          onStep(event.key === "ArrowLeft" ? -1 : 1);
        }
      }}
      onClick={() => selectClip(selectedClipId === clip.clip_id ? null : clip.clip_id)}
      title={`${clip.label ?? clip.clip_id} · ${clip.timeline_duration_s.toFixed(2)}s`}
    >
      <span className="clip__label">{clip.label ?? clip.clip_id}</span>
      {clip.speed_curve ? (
        <>
          <SpeedCurveTrace curve={clip.speed_curve} width={width} />
          <span className="clip__rate num">
            {Math.min(...clip.speed_curve.points.map((point) => point.rate)).toFixed(2)}×
          </span>
        </>
      ) : null}
      <span className="clip__badges">
        {badges.slice(0, 2).map((badge) => (
          <span className="clip__badge" key={badge}>{badge}</span>
        ))}
      </span>
      {void laneWidth}
    </button>
  );
}
