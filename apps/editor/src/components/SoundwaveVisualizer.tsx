import { useEffect, useState } from "react";

export function SoundwaveVisualizer({ active = true }: { active?: boolean }) {
  const [bars, setBars] = useState([40, 65, 30, 85, 50, 75, 45]);

  useEffect(() => {
    if (!active) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduced.matches) return;

    const interval = window.setInterval(() => {
      if (document.hidden) return;
      setBars([
        25 + Math.sin(Date.now() * 0.007) * 20 + Math.random() * 15,
        35 + Math.cos(Date.now() * 0.005) * 25 + Math.random() * 20,
        20 + Math.sin(Date.now() * 0.008 + 1) * 20 + Math.random() * 15,
        50 + Math.sin(Date.now() * 0.006 + 2) * 35 + Math.random() * 15,
        30 + Math.cos(Date.now() * 0.007 + 3) * 25 + Math.random() * 20,
        45 + Math.sin(Date.now() * 0.005 + 4) * 30 + Math.random() * 20,
        30 + Math.cos(Date.now() * 0.008 + 5) * 20 + Math.random() * 15,
      ]);
    }, 120);

    return () => window.clearInterval(interval);
  }, [active]);

  return (
    <div className="soundwave" aria-hidden="true">
      {bars.map((height, i) => (
        <span
          key={i}
          className="soundwave__bar"
          style={{ height: `${Math.max(15, Math.min(100, height))}%` }}
        />
      ))}
    </div>
  );
}
