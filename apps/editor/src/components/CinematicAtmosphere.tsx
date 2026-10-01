import { useEffect, useRef } from "react";

interface NodeOrb {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  baseAlpha: number;
  color: string;
  phase: number;
}

export function CinematicAtmosphere() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId = 0;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const onResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener("resize", onResize);

    const mouse = { x: width / 2, y: height / 2, tx: width / 2, ty: height / 2 };
    const onMouseMove = (e: MouseEvent) => {
      mouse.tx = e.clientX;
      mouse.ty = e.clientY;
    };
    window.addEventListener("mousemove", onMouseMove);

    // Muted cinematic palette matching TakeOne neutral and state tokens:
    // Warm amber glow, deep studio red glow, cool slate highlight
    const colors = [
      "rgba(176, 146, 86, 0.08)",  // amber / attention
      "rgba(216, 53, 43, 0.05)",   // studio rolling red
      "rgba(255, 255, 255, 0.04)", // silver white
      "rgba(125, 155, 131, 0.06)", // ready green
      "rgba(138, 138, 138, 0.05)", // slate sim
    ];

    const orbs: NodeOrb[] = Array.from({ length: 6 }, (_, i) => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      radius: 180 + Math.random() * 220,
      baseAlpha: 0.8 + Math.random() * 0.4,
      color: colors[i % colors.length],
      phase: Math.random() * Math.PI * 2,
    }));

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

    let lastTime = performance.now();

    const render = (time: number) => {
      const dt = Math.min((time - lastTime) / 1000, 0.1);
      lastTime = time;

      if (!reduced.matches && !document.hidden) {
        mouse.x += (mouse.tx - mouse.x) * 0.05;
        mouse.y += (mouse.ty - mouse.y) * 0.05;

        ctx.clearRect(0, 0, width, height);

        // Render ambient light nodes
        for (const orb of orbs) {
          orb.x += orb.vx;
          orb.y += orb.vy;
          orb.phase += dt * 0.5;

          if (orb.x < -orb.radius) orb.x = width + orb.radius;
          if (orb.x > width + orb.radius) orb.x = -orb.radius;
          if (orb.y < -orb.radius) orb.y = height + orb.radius;
          if (orb.y > height + orb.radius) orb.y = -orb.radius;

          // Parallax effect influenced by mouse
          const dx = (mouse.x - width / 2) * 0.04;
          const dy = (mouse.y - height / 2) * 0.04;

          const currentRadius = orb.radius + Math.sin(orb.phase) * 20;

          const grad = ctx.createRadialGradient(
            orb.x + dx,
            orb.y + dy,
            0,
            orb.x + dx,
            orb.y + dy,
            currentRadius
          );
          grad.addColorStop(0, orb.color);
          grad.addColorStop(1, "rgba(0, 0, 0, 0)");

          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(orb.x + dx, orb.y + dy, currentRadius, 0, Math.PI * 2);
          ctx.fill();
        }

        // Draw fine cinematic grid lines
        ctx.strokeStyle = "rgba(255, 255, 255, 0.015)";
        ctx.lineWidth = 1;
        const gridSize = 80;
        ctx.beginPath();
        for (let x = 0; x < width; x += gridSize) {
          ctx.moveTo(x, 0);
          ctx.lineTo(x, height);
        }
        for (let y = 0; y < height; y += gridSize) {
          ctx.moveTo(0, y);
          ctx.lineTo(width, y);
        }
        ctx.stroke();
      }

      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("mousemove", onMouseMove);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="cinematic-atmosphere"
      aria-hidden="true"
    />
  );
}
