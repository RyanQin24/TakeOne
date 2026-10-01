export function Ruler({ duration, scale }: { duration: number; scale: number }) {
  const step = duration > 60 ? 10 : duration > 20 ? 4 : duration > 8 ? 2 : 1;
  const ticks: number[] = [];
  for (let time = 0; time <= duration + 0.001; time += step) ticks.push(time);
  return (
    <div className="ruler">
      {ticks.map((time) => (
        <span key={time} className="ruler__tick num" style={{ left: time * scale }}>
          {formatTick(time)}
        </span>
      ))}
    </div>
  );
}

function formatTick(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}
