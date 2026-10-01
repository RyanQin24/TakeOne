import { useMemo } from "react";
import type { SpeedCurve as Curve } from "../../state/types";

// The curve drawn on a clip is the curve the renderer executes: the same control points,
// sampled. It is not a decorative squiggle that happens to appear when a ramp is applied.

export function SpeedCurveTrace({ curve, width }: { curve: Curve; width: number }) {
  const path = useMemo(() => {
    const points = curve.points;
    if (points.length < 2 || width < 8) return "";
    const total = points[points.length - 1].time_s || 1;
    const rates = points.map((point) => point.rate);
    const low = Math.min(...rates, 1);
    const high = Math.max(...rates, 1);
    const span = high - low || 1;
    const samples = Math.max(8, Math.min(96, Math.round(width / 3)));
    const coordinates: string[] = [];
    for (let index = 0; index <= samples; index += 1) {
      const t = (index / samples) * total;
      const rate = rateAt(points, t);
      const x = (t / total) * width;
      const y = 18 - ((rate - low) / span) * 14 - 2;
      coordinates.push(`${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`);
    }
    return coordinates.join(" ");
  }, [curve, width]);

  if (!path) return null;
  const length = Math.max(width * 1.4, 40);

  return (
    <svg className="clip__curve" viewBox={`0 0 ${Math.max(width, 1)} 20`} preserveAspectRatio="none">
      <path d={path} style={{ ["--len" as string]: `${length}` }} />
    </svg>
  );
}

function ease(name: string, x: number): number {
  const clamped = Math.min(1, Math.max(0, x));
  switch (name) {
    case "ease_in":
      return clamped * clamped;
    case "ease_out":
      return 2 * clamped - clamped * clamped;
    case "ease_in_out":
      return clamped * clamped * (3 - 2 * clamped);
    case "hold":
      return clamped >= 1 ? 1 : 0;
    default:
      return clamped;
  }
}

function rateAt(points: Curve["points"], time: number): number {
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const current = points[index];
    if (time <= current.time_s) {
      const span = current.time_s - previous.time_s;
      const fraction = span === 0 ? 0 : (time - previous.time_s) / span;
      return previous.rate + (current.rate - previous.rate) * ease(current.easing, fraction);
    }
  }
  return points[points.length - 1].rate;
}
