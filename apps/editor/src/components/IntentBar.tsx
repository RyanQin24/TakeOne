import { api } from "../state/api";
import { useEditor } from "../state/store";

const INTENTS = [
  "Make it more cinematic",
  "Faster pacing",
  "Slower pacing",
  "More dramatic",
  "Fewer effects",
  "More natural",
  "Try a different opening",
];

export function IntentBar({ projectId }: { projectId: string }) {
  const project = useEditor((state) => state.project);
  const setError = useEditor((state) => state.setError);

  const send = async (prompt: string) => {
    try {
      await api.submit(projectId, {
        type: "SET_INTENT",
        target: { kind: "project" },
        parameters: {
          intent: {
            prompt,
            target_duration_s: project?.intent?.target_duration_s ?? 12,
            aspect_ratio: project?.intent?.aspect_ratio ?? "16:9",
          },
        },
        public_explanation: prompt,
      });
    } catch (problem) {
      setError((problem as Error).message);
    }
  };

  return (
    <div className="intent">
      {INTENTS.map((intent) => (
        <button key={intent} className="btn btn--chip" onClick={() => void send(intent)}>
          {intent}
        </button>
      ))}
    </div>
  );
}
