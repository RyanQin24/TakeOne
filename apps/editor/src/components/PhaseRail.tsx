import { STAGES, STAGE_LABEL, STAGE_OF } from "../state/phases";
import { useEditor } from "../state/store";

/* Four stages, not nine. The nine internal phase names are unchanged and still
 * drive the reducer; this rail shows the four an operator reads. */
export function PhaseRail() {
  const phase = useEditor((state) => state.project?.phase ?? "understand");
  const current = STAGE_OF[phase] ?? "review";
  const reached = STAGES.indexOf(current);

  return (
    <ol className="phase-rail" aria-label="Edit stages">
      {STAGES.map((stage, index) => {
        const state = index < reached ? "done" : index === reached ? "live" : "wait";
        return (
          <li key={stage} className={`phase-rail__step phase-rail__step--${state}`}>
            <span className="phase-rail__dot" />
            <span className="phase-rail__name">{STAGE_LABEL[stage]}</span>
          </li>
        );
      })}
    </ol>
  );
}
