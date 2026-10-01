export function timecode(seconds: number, fps = 30): string {
  const safe = Math.max(0, seconds);
  const minutes = Math.floor(safe / 60);
  const wholeSeconds = Math.floor(safe % 60);
  const frames = Math.floor((safe % 1) * fps);
  return `${String(minutes).padStart(2, "0")}:${String(wholeSeconds).padStart(2, "0")}.${String(
    frames,
  ).padStart(2, "0")}`;
}

export function duration(seconds: number): string {
  return `${seconds.toFixed(2)}s`;
}

export function score(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : String(Math.round(value * 100));
}
