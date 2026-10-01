import { useEffect, useMemo, useState } from "react";
import { ActivityPanel } from "./ActivityPanel";
import { Inspector } from "./Inspector";
import { PhaseRail } from "./PhaseRail";
import { VFXPanel } from "./VFXPanel";
import { api } from "../state/api";
import { findClip, useEditor } from "../state/store";
import type { ColorGrade, EffectSpec } from "../state/types";

type Tab = "ai" | "adjust" | "looks" | "effects" | "cuts";

const TABS: { id: Tab; label: string }[] = [
  { id: "ai", label: "AI" },
  { id: "adjust", label: "Adjust" },
  { id: "looks", label: "Looks" },
  { id: "effects", label: "Effects" },
  { id: "cuts", label: "Cuts" },
];

const LOOK_TONE: Record<string, string> = {
  luxury_warm: "linear-gradient(135deg, #5c3b14, #c8a24a)",
  noir_contrast: "linear-gradient(135deg, #111, #6b6b6b)",
  teal_orange: "linear-gradient(135deg, #1a4a4a, #c46a2d)",
  dream_reveal: "linear-gradient(135deg, #4a3a55, #e2b8c8)",
  action_impact: "linear-gradient(135deg, #3a1212, #d4552b)",
  spectrum_entrance: "linear-gradient(135deg, #2a1260, #e23bb1 50%, #f0c14a)",
  clean_natural: "linear-gradient(135deg, #3a4038, #c5c1b2)",
  mono_film: "linear-gradient(135deg, #161616, #9a9a9a)",
  night_cool: "linear-gradient(135deg, #0c1c32, #5aa0c8)",
  golden_hour: "linear-gradient(135deg, #7a3d12, #f0b45a)",
  bleach_bypass: "linear-gradient(135deg, #2a2a28, #b8b4a8)",
  vintage: "linear-gradient(135deg, #4a3018, #c9a36a)",
  cyberpunk: "linear-gradient(135deg, #1a0a3a, #19d4c6 55%, #e23bb1)",
  kodak_portra: "linear-gradient(135deg, #5a3a28, #e8c8a0)",
  fuji_eterna: "linear-gradient(135deg, #24383c, #9bb8b0)",
  vhs_tape: "linear-gradient(135deg, #201428, #7a6a88)",
  pastel: "linear-gradient(135deg, #6a5868, #e8c8d8)",
  high_key: "linear-gradient(135deg, #8a8880, #f4f1ea)",
};

interface Props {
  projectId: string;
  onMutate: () => void;
}

function slugId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

export function Studio({ projectId, onMutate }: Props) {
  const [tab, setTab] = useState<Tab>("ai");
  const [catalog, setCatalog] = useState<EffectSpec[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const project = useEditor((state) => state.project);
  const selectedClipId = useEditor((state) => state.selectedClipId);
  const found = findClip(project, selectedClipId);
  const clip = found?.clip ?? null;

  useEffect(() => {
    api.effects().then((result) => setCatalog(result.effects)).catch(() => setCatalog([]));
  }, []);

  const looks = useMemo(
    () => catalog.filter((item) => !item.primitive && item.arity === 1 && item.tags.includes("look")),
    [catalog],
  );
  const effects = useMemo(
    () => catalog.filter((item) => item.primitive && item.arity === 1 && item.id !== "lut3d"),
    [catalog],
  );
  const transitions = useMemo(
    () => catalog.filter((item) => item.arity === 2),
    [catalog],
  );

  const apply = async (label: string, work: () => Promise<unknown>) => {
    setBusy(label);
    try {
      await work();
      onMutate();
    } catch (problem) {
      useEditor.getState().setError((problem as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const needClip = !clip;

  return (
    <aside className="panel panel--right studio">
      <nav className="studio__tabs" aria-label="Studio">
        {TABS.map((item) => (
          <button
            key={item.id}
            className={tab === item.id ? "studio__tab studio__tab--on" : "studio__tab"}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="studio__body">
        {tab === "ai" ? (
          <>
            <PhaseRail />
            <p className="studio__hint">
              Each line is a real edit. Watch the timeline as shots, cuts and grades land.
            </p>
            <button
              className="btn btn--primary"
              disabled={busy !== null || !project || Object.keys(project.media).length === 0}
              onClick={() =>
                apply("edit", async () => {
                  await api.autoEdit(projectId, 0.32);
                })
              }
            >
              {busy === "edit" ? "Editing…" : "Run the AI edit"}
            </button>
            <VFXPanel key={projectId} projectId={projectId} />
            {clip ? <Inspector /> : null}
            <ActivityPanel embedded />
          </>
        ) : null}

        {tab === "adjust" ? (
          needClip ? <EmptyApply /> : (
            <AdjustForm
              grade={clip.color}
              busy={busy}
              onCommit={(next) =>
                apply("adjust", () =>
                  api.submit(projectId, {
                    type: "APPLY_COLOR_CORRECTION",
                    target: { kind: "clip", clip_id: clip.clip_id },
                    parameters: next,
                    public_explanation: "Adjusted the grade from the studio.",
                  }),
                )
              }
            />
          )
        ) : null}

        {tab === "looks" ? (
          needClip ? <EmptyApply /> : (
            <div className="card-grid">
              {looks.map((item) => (
                <button
                  key={item.id}
                  className="look-card"
                  disabled={busy !== null}
                  onClick={() =>
                    apply(item.id, () =>
                      api.submit(projectId, {
                        type: "APPLY_CREATIVE_LOOK",
                        target: { kind: "clip", clip_id: clip.clip_id },
                        parameters: { look_id: item.id, intensity: 0.75 },
                        public_explanation: `Applied ${item.name}.`,
                      }),
                    )
                  }
                >
                  <i className="look-card__swatch" style={{ background: LOOK_TONE[item.id] ?? "#2a2d31" }} />
                  <span className="look-card__name">{item.name}</span>
                  <span className="look-card__desc">{item.description}</span>
                </button>
              ))}
            </div>
          )
        ) : null}

        {tab === "effects" ? (
          needClip ? <EmptyApply /> : (
            <EffectsList
              effects={effects}
              busy={busy}
              applied={clip.effects.map((item) => item.effect_id)}
              onApply={(item) =>
                apply(item.id, () =>
                  api.submit(projectId, {
                    type: "ADD_EFFECT",
                    target: { kind: "clip", clip_id: clip.clip_id },
                    parameters: {
                      instance_id: slugId("fx"),
                      effect_id: item.id,
                      effect_version: item.version,
                      parameters: {},
                    },
                    public_explanation: `Added ${item.name}.`,
                  }),
                )
              }
            />
          )
        ) : null}

        {tab === "cuts" ? (
          <CutsList
            transitions={transitions}
            busy={busy}
            disabled={!project || !clip}
            onApply={(item) => {
              const pair = adjacentPair(project, clip?.clip_id ?? null);
              if (!pair) {
                useEditor.getState().setError("Select a clip that has a neighbour to cut against.");
                return;
              }
              apply(item.id, () =>
                api.submit(projectId, {
                  type: "APPLY_TRANSITION",
                  target: { kind: "track", track_id: pair.trackId },
                  parameters: {
                    transition_id: slugId("tr"),
                    effect_id: item.id,
                    effect_version: item.version,
                    from_clip_id: pair.from,
                    to_clip_id: pair.to,
                    duration_s: 0.4,
                  },
                  public_explanation: `Cut with ${item.name}.`,
                }),
              );
            }}
          />
        ) : null}
      </div>
    </aside>
  );
}

function EmptyApply() {
  return <p className="studio__hint">Select a clip on the timeline to grade, look, or effect it.</p>;
}

function EffectsList({
  effects,
  busy,
  applied,
  onApply,
}: {
  effects: EffectSpec[];
  busy: string | null;
  applied: string[];
  onApply: (item: EffectSpec) => void;
}) {
  const groups = new Map<string, EffectSpec[]>();
  for (const item of effects) {
    const list = groups.get(item.category) ?? [];
    list.push(item);
    groups.set(item.category, list);
  }
  return (
    <div className="fx-stack">
      {[...groups.entries()].map(([category, items]) => (
        <section key={category}>
          <h3 className="label">{category}</h3>
          <div className="chip-grid">
            {items.map((item) => (
              <button
                key={item.id}
                className={applied.includes(item.id) ? "fx-chip fx-chip--on" : "fx-chip"}
                title={item.description}
                disabled={busy !== null}
                onClick={() => onApply(item)}
              >
                {item.name}
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function CutsList({
  transitions,
  busy,
  disabled,
  onApply,
}: {
  transitions: EffectSpec[];
  busy: string | null;
  disabled: boolean;
  onApply: (item: EffectSpec) => void;
}) {
  return (
    <div className="chip-grid">
      {disabled ? <p className="studio__hint">Select a clip with a neighbour to add a transition.</p> : null}
      {transitions.map((item) => (
        <button
          key={item.id}
          className="fx-chip"
          title={item.description}
          disabled={disabled || busy !== null}
          onClick={() => onApply(item)}
        >
          {item.name}
        </button>
      ))}
    </div>
  );
}

function AdjustForm({
  grade,
  busy,
  onCommit,
}: {
  grade: ColorGrade;
  busy: string | null;
  onCommit: (next: Record<string, number>) => void;
}) {
  const [draft, setDraft] = useState(grade);
  useEffect(() => setDraft(grade), [grade]);

  const commit = () =>
    onCommit({
      exposure_stops: draft.exposure_stops,
      temperature_k: draft.temperature_k,
      tint: draft.tint,
      contrast: draft.contrast,
      saturation: draft.saturation,
      lift: draft.lift,
    });

  return (
    <div className="adjust">
      <Slider label="Exposure" value={draft.exposure_stops} min={-2} max={2} step={0.05}
        display={`${draft.exposure_stops >= 0 ? "+" : ""}${draft.exposure_stops.toFixed(2)}`}
        onChange={(value) => setDraft({ ...draft, exposure_stops: value })} onCommit={commit} disabled={busy !== null} />
      <Slider label="Temperature" value={draft.temperature_k} min={-1200} max={1200} step={10}
        display={`${draft.temperature_k >= 0 ? "+" : ""}${Math.round(draft.temperature_k)} K`}
        onChange={(value) => setDraft({ ...draft, temperature_k: value })} onCommit={commit} disabled={busy !== null} />
      <Slider label="Tint" value={draft.tint} min={-0.6} max={0.6} step={0.01}
        display={draft.tint.toFixed(2)}
        onChange={(value) => setDraft({ ...draft, tint: value })} onCommit={commit} disabled={busy !== null} />
      <Slider label="Contrast" value={draft.contrast} min={0.4} max={2} step={0.01}
        display={`${draft.contrast.toFixed(2)}×`}
        onChange={(value) => setDraft({ ...draft, contrast: value })} onCommit={commit} disabled={busy !== null} />
      <Slider label="Saturation" value={draft.saturation} min={0} max={2} step={0.01}
        display={`${draft.saturation.toFixed(2)}×`}
        onChange={(value) => setDraft({ ...draft, saturation: value })} onCommit={commit} disabled={busy !== null} />
      <Slider label="Lift" value={draft.lift} min={-0.3} max={0.3} step={0.01}
        display={draft.lift.toFixed(2)}
        onChange={(value) => setDraft({ ...draft, lift: value })} onCommit={commit} disabled={busy !== null} />
    </div>
  );
}

function Slider({
  label, value, min, max, step, display, onChange, onCommit, disabled,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  display: string;
  onChange: (value: number) => void;
  onCommit: () => void;
  disabled: boolean;
}) {
  return (
    <label className="slider">
      <span className="slider__meta">
        <span>{label}</span>
        <b className="num">{display}</b>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
        onPointerUp={onCommit}
        onKeyUp={(event) => event.key === "Enter" && onCommit()}
      />
    </label>
  );
}

function adjacentPair(project: ReturnType<typeof useEditor.getState>["project"], clipId: string | null) {
  if (!project || !clipId) return null;
  for (const track of project.timeline.tracks) {
    const index = track.clips.findIndex((item) => item.clip_id === clipId);
    if (index < 0) continue;
    if (index > 0) {
      return { trackId: track.track_id, from: track.clips[index - 1].clip_id, to: clipId };
    }
    if (index < track.clips.length - 1) {
      return { trackId: track.track_id, from: clipId, to: track.clips[index + 1].clip_id };
    }
  }
  return null;
}
