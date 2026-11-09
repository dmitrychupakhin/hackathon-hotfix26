"use client";

import {
  motion,
  useMotionValue,
  useReducedMotion,
  useSpring,
} from "motion/react";
import { useEffect, useRef } from "react";

const planets = [
  { x: 115, color: "#DFEECF" },
  { x: 246, color: "rgba(197, 202, 198, 0.7)" },
  { x: 377, color: "#EAC7C0" },
];

function Planet({
  x: position,
  color,
  size = 18,
}: {
  x: number;
  color: string;
  size?: number;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const reducedMotion = useReducedMotion();
  const x = useSpring(useMotionValue(0), {
    stiffness: 130,
    damping: 22,
    mass: 0.7,
  });
  const y = useSpring(useMotionValue(0), {
    stiffness: 130,
    damping: 22,
    mass: 0.7,
  });

  useEffect(() => {
    if (reducedMotion) return;
    const reset = () => {
      x.set(0);
      y.set(0);
    };
    const move = (event: PointerEvent) => {
      if (event.pointerType === "touch" || !ref.current) return reset();
      const rect = ref.current.getBoundingClientRect();
      const dx = event.clientX - (rect.left + rect.width / 2) + x.get();
      const dy = event.clientY - (rect.top + rect.height / 2) + y.get();
      const distance = Math.hypot(dx, dy);
      const pull = Math.max(0, 1 - distance / 150) * 0.28;
      x.set(dx * pull);
      y.set(dy * pull);
    };
    window.addEventListener("pointermove", move, { passive: true });
    document.addEventListener("pointerleave", reset);
    window.addEventListener("blur", reset);
    return () => {
      window.removeEventListener("pointermove", move);
      document.removeEventListener("pointerleave", reset);
      window.removeEventListener("blur", reset);
    };
  }, [reducedMotion, x, y]);

  return (
    <motion.span
      ref={ref}
      className="absolute rounded-full"
      style={{
        left: position - size / 2,
        top: 9 - size / 2,
        width: size,
        height: size,
        backgroundColor: color,
        x,
        y,
      }}
    />
  );
}

export function InteractivePlanetLine({
  mirrored = false,
}: {
  mirrored?: boolean;
}) {
  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none absolute h-[18px] w-[386px] overflow-visible ${mirrored ? "top-5 right-0" : "bottom-5 left-0"}`}
    >
      {Array.from({ length: 20 }, (_, index) => 3 + index * 20).map(
        (position) => (
          <Planet key={position} x={position} color="#D1D3D5" size={6} />
        ),
      )}
      {planets.map((planet) => (
        <Planet
          key={planet.x}
          {...planet}
          x={mirrored ? 386 - planet.x : planet.x}
        />
      ))}
    </div>
  );
}
