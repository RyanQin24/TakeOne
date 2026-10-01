import { findClip, useEditor } from "../state/store";
import { duration, timecode } from "../lib/timecode";

// The inspector explains a decision. It is deliberately read-only: every change to a
// project is an operation, and an inspector full of sliders would become a second, quieter
// way to mutate state that the activity feed could not explain.

export function Inspector() {
  const project = useEditor((state) => state.project);
  const selectedClipId = useEditor((state) => state.selectedClipId);
  const activity = useEditor((state) => state.activity);
  const found = findClip(project, selectedClipId);
  if (!project || !found) return null;

  const { clip } = found;
  const media = project.media[clip.media_id];
  const grade = clip.color;
  const reasons = activity.filter((entry) => entry.targetClipId === clip.clip_id);
  const rates = clip.speed_curve?.points.map((point) => point.rate) ?? [];

  return (
    <div className="inspector">
      <div className="inspector__head">
        <span className="inspector__title">{clip.label ?? clip.clip_id}</span>
        <span className="label">{media?.name}</span>
      </div>

      <div className="inspector__group">
        <span className="label">Edit</span>
        <div className="inspector__line">
          <span>Source</span>
          <b className="num">
            {timecode(clip.source_start_s)} — {timecode(clip.source_end_s)}
          </b>
        </div>
        <div className="inspector__line">
          <span>On the timeline</span>
          <b className="num">
            {timecode(clip.timeline_start_s)} · {duration(clip.timeline_duration_s)}
          </b>
        </div>
        {rates.length ? (
          <div className="inspector__line">
            <span>Speed</span>
            <b className="num">
              {rates.map((rate) => `${rate.toFixed(2)}×`).join(" → ")}
            </b>
          </div>
        ) : null}
      </div>

      <div className="inspector__group">
        <span className="label">Colour</span>
        {grade.exposure_stops !== 0 ? (
          <div className="inspector__line">
            <span>Exposure</span>
            <b className="num">{grade.exposure_stops > 0 ? "+" : ""}{grade.exposure_stops.toFixed(2)} stops</b>
          </div>
        ) : null}
        {grade.temperature_k !== 0 ? (
          <div className="inspector__line">
            <span>Temperature</span>
            <b className="num">{grade.temperature_k > 0 ? "+" : ""}{grade.temperature_k.toFixed(0)} K</b>
          </div>
        ) : null}
        {grade.contrast !== 1 ? (
          <div className="inspector__line">
            <span>Contrast</span><b className="num">{grade.contrast.toFixed(2)}×</b>
          </div>
        ) : null}
        {grade.matched_to ? (
          <div className="inspector__line">
            <span>Matched to</span><b>{grade.matched_to}</b>
          </div>
        ) : null}
        {grade.look_id ? (
          <div className="inspector__line">
            <span>{grade.look_id.replace(/_/g, " ")}</span>
            <b className="num">{Math.round(grade.look_intensity * 100)}%</b>
          </div>
        ) : null}
      </div>

      {clip.effects.length ? (
        <div className="inspector__group">
          <span className="label">Effects</span>
          {clip.effects.map((effect) => (
            <div className="inspector__line" key={effect.instance_id}>
              <span>{effect.effect_id.replace(/_/g, " ")}</span>
              <b className="num">
                {effect.start_s === null
                  ? "whole clip"
                  : `${effect.start_s.toFixed(2)}–${(effect.end_s ?? 0).toFixed(2)}s`}
              </b>
            </div>
          ))}
        </div>
      ) : null}

      {reasons.length ? (
        <div className="inspector__group">
          <span className="label">Why</span>
          {reasons.slice(-4).map((entry, index) => (
            <p className="activity__text" key={index}>{entry.explanation}</p>
          ))}
        </div>
      ) : null}
    </div>
  );
}
