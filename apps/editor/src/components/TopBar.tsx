import { PHASES } from "../state/types";
import { TakeOneNav } from "./TakeOneNav";
import { useEditor } from "../state/store";

interface Props {
  title: string;
  onHome: () => void;
  onRender: () => void;
  onExport: () => void;
  onUndo: () => void;
  exporting: boolean;
}

export function TopBar({ title, onHome, onRender, onExport, onUndo, exporting }: Props) {
  const project = useEditor((state) => state.project);
  const connected = useEditor((state) => state.connected);
  const jobs = useEditor((state) => state.jobs);

  const phase = project?.phase ?? "understand";
  const reached = PHASES.indexOf(phase === "complete" ? "finalize" : phase);
  const running = jobs.find((job) => job.status === "RUNNING" || job.status === "QUEUED");
  const progress = running
    ? (reached + running.progress) / PHASES.length
    : (reached + 1) / PHASES.length;

  return (
    <header className="topbar">
      <button className="topbar__brand" onClick={onHome}>
        <span className="topbar__mark" aria-hidden>T/1</span>TAKE ONE
      </button>
      <TakeOneNav />
      <span className="topbar__rule" aria-hidden />
      <span className="topbar__workspace"><b>Edit</b><small>Finishing suite</small></span>
      <span className="topbar__title">{title}</span>
      <div className="topbar__spacer" />
      <div className="topbar__phase">
        <span className="topbar__phase-name">
          {running ? running.stage : phase === "complete" ? "ready" : phase}
        </span>
        <div className="topbar__meter" aria-hidden>
          <span style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>
        <span className="num label">{Math.round(progress * 100)}%</span>
      </div>
      <div className="topbar__status">
        <i className={connected ? "dot dot--live" : "dot"} />
        <span className="label">{connected ? "live" : "offline"}</span>
      </div>
      <button className="btn btn--ghost" onClick={onUndo}>Undo</button>
      <button className="btn btn--ghost" onClick={onRender} disabled={!project?.timeline.duration_s}>Preview</button>
      <button className="btn btn--primary" onClick={onExport} disabled={exporting || !project?.timeline.duration_s}>
        {exporting ? "Exporting…" : "Export MP4"}
      </button>
    </header>
  );
}
