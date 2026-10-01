import { useEffect, useRef } from "react";
import { PHASE_LABEL as PHASE } from "../state/phases";
import { useEditor } from "../state/store";


const READABLE: Record<string, string> = {
  IMPORT_MEDIA: "Imported",
  ANALYZE_CLIP: "Analysed",
  SELECT_CLIP: "Selected",
  REJECT_CLIP: "Rejected",
  ADD_TRACK: "Track",
  ADD_CLIP: "Added shot",
  TRIM_CLIP: "Trimmed",
  MOVE_CLIP: "Moved",
  REORDER_CLIP: "Reordered",
  SPLIT_CLIP: "Split",
  APPLY_SPEED_CURVE: "Speed ramp",
  FREEZE_FRAME: "Freeze",
  APPLY_TRANSITION: "Transition",
  ALIGN_CUT_TO_BEAT: "Cut to beat",
  APPLY_COLOR_CORRECTION: "Colour",
  MATCH_COLOR: "Matched colour",
  APPLY_CREATIVE_LOOK: "Look",
  ADD_EFFECT: "Effect",
  ADD_MARKERS: "Beats",
  SET_INTENT: "Intent",
  SET_PHASE: "Phase",
  ADD_MUSIC: "Music",
  ADD_SFX: "Sound",
  FINALIZE_TIMELINE: "Finalised",
};

export function ActivityPanel({ embedded = false }: { embedded?: boolean }) {
  const activity = useEditor((state) => state.activity);
  const selectClip = useEditor((state) => state.selectClip);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (embedded) return;
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activity.length, embedded]);

  const body = (
      <div className="activity">
        {activity.map((entry, index) => (
          <div
            key={`${entry.sequence}-${index}`}
            className={index === activity.length - 1 ? "activity__row activity__row--new" : "activity__row"}
            onClick={() => entry.targetClipId && selectClip(entry.targetClipId)}
          >
            <span
              className={
                index === activity.length - 1 ? "activity__mark activity__mark--live" : "activity__mark"
              }
            >
              {index === activity.length - 1 ? "→" : "✓"}
            </span>
            <div>
              <div className="activity__type">
                {PHASE[entry.phase] ?? entry.phase}
                {" · "}
                {READABLE[entry.type] ?? entry.type}
              </div>
              <div className="activity__text">{entry.explanation}</div>
            </div>
          </div>
        ))}
        <div ref={bottom} />
      </div>
  );

  if (embedded) return body;
  return (
    <aside className="panel panel--right">
      <h2 className="label panel__title">AI editor</h2>
      {body}
    </aside>
  );
}
