"use client";

import {
  motion,
  useAnimationFrame,
  useInView,
  useMotionValue,
  useReducedMotion,
  useTransform,
} from "motion/react";
import { useEffect, useRef } from "react";

// A seeded distribution keeps server and client markup identical.
const planets = Array.from({ length: 30 }, (_, index) => {
  const random = (salt: number) => {
    const value = Math.sin((index + 1) * salt) * 43758.5453;
    return value - Math.floor(value);
  };
  const radius = 140 + random(24.731) * 600;
  const rounded = (value: number) => Number(value.toFixed(3));
  const angle = (index * Math.PI * (3 - Math.sqrt(5))) % (Math.PI * 2);
  return {
    id: index,
    radius,
    angle,
    left: rounded(((Math.cos(angle) * radius) / 820) * 100),
    top: rounded(((Math.sin(angle) * radius * 0.8) / 640) * 100),
    size: rounded(10 + random(39.425) * 12),
    color: ["bg-[#EAC7C0]", "bg-[#ECD7BF]", "bg-accent-300"][index % 3],
  };
});

type Cursor = { x: number; y: number; active: boolean };

function Planet({
  planet,
  cursor,
  bounds,
  flipX,
  flipY,
}: {
  planet: (typeof planets)[number];
  flipX: boolean;
  flipY: boolean;
  cursor: React.RefObject<Cursor>;
  bounds: React.RefObject<DOMRect | null>;
}) {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const reducedMotion = useReducedMotion();
  const floatX = useMotionValue(0);
  const floatY = useMotionValue(0);
  const renderedX = useTransform(() => x.get() + floatX.get());
  const renderedY = useTransform(() => y.get() + floatY.get());
  const elapsed = useRef(0);
  const opacity = useMotionValue(1);
  useAnimationFrame((_, delta) => {
    if (reducedMotion || !bounds.current) return;
    const rect = bounds.current;
    const baseX = (rect.width * planet.left) / 100;
    const baseY = (rect.height * planet.top) / 100;
    elapsed.current += Math.min(delta, 32) / 1000;
    const angle =
      planet.angle + elapsed.current * ((Math.PI * 2) / (65 + planet.id * 4));
    const px = (Math.cos(angle) * planet.radius * rect.width) / 820 + x.get();
    const py =
      (Math.sin(angle) * planet.radius * 0.8 * rect.height) / 640 + y.get();
    const screenX = flipX ? rect.right - px : rect.left + px;
    const screenY = flipY ? rect.bottom - py : rect.top + py;
    const margin = planet.size / 2;
    const visible =
      px >= -margin &&
      py >= -margin &&
      px <= rect.width + margin &&
      py <= rect.height + margin &&
      screenX >= -margin &&
      screenX <= window.innerWidth + margin &&
      screenY >= -margin &&
      screenY <= window.innerHeight + margin;
    if (!visible) {
      if (opacity.get() !== 0) opacity.set(0);
      return;
    }
    floatX.set(px - x.get() - baseX);
    floatY.set(py - y.get() - baseY);
    if (opacity.get() !== 1) opacity.set(1);
    if (!cursor.current.active) return;
    const dx =
      (flipX ? rect.right - cursor.current.x : cursor.current.x - rect.left) -
      baseX -
      renderedX.get();
    const dy =
      (flipY ? rect.bottom - cursor.current.y : cursor.current.y - rect.top) -
      baseY -
      renderedY.get();
    const distance = Math.hypot(dx, dy);
    const reach = 360;
    if (distance >= reach || distance < 1) return;
    const proximity = 1 - distance / reach;
    const speed = 8 + 110 * proximity ** 2;
    const step = Math.min(distance, (speed * Math.min(delta, 32)) / 1000);
    let nextX = x.get() + (dx / distance) * step;
    let nextY = y.get() + (dy / distance) * step;
    // Keep each planet within the local orbit area, including on narrow screens.
    const maxDrift = (64 * rect.width) / 820;
    const drift = Math.hypot(nextX, nextY);
    if (drift > maxDrift) {
      nextX *= maxDrift / drift;
      nextY *= maxDrift / drift;
    }
    x.set(nextX);
    y.set(nextY);
  });
  return (
    <motion.span
      className={`absolute rounded-full ${planet.color}`}
      style={{
        left: `${planet.left}%`,
        top: `${planet.top}%`,
        width: planet.size,
        height: planet.size,
        opacity,
        x: renderedX,
        y: renderedY,
        translateX: "-50%",
        translateY: "-50%",
      }}
    />
  );
}

export function InteractivePlanets({
  count = 30,
  flipX = false,
  flipY = false,
}: {
  count?: number;
  flipX?: boolean;
  flipY?: boolean;
}) {
  const container = useRef<HTMLDivElement>(null);
  const inView = useInView(container);
  const bounds = useRef<DOMRect | null>(null);
  useEffect(() => {
    const updateBounds = () => {
      bounds.current = container.current?.getBoundingClientRect() ?? null;
    };
    updateBounds();
    const observer = new ResizeObserver(updateBounds);
    if (container.current) observer.observe(container.current);
    window.addEventListener("scroll", updateBounds, { passive: true });
    window.addEventListener("resize", updateBounds);
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", updateBounds);
      window.removeEventListener("resize", updateBounds);
    };
  }, []);
  const cursor = useRef<Cursor>({ x: 0, y: 0, active: false });
  useEffect(() => {
    const move = (event: PointerEvent) => {
      cursor.current = {
        x: event.clientX,
        y: event.clientY,
        active: event.pointerType !== "touch",
      };
    };
    const reset = () => {
      cursor.current.active = false;
    };
    window.addEventListener("pointermove", move, { passive: true });
    document.addEventListener("pointerleave", reset);
    window.addEventListener("blur", reset);
    window.addEventListener("scroll", reset, { passive: true });
    return () => {
      window.removeEventListener("pointermove", move);
      document.removeEventListener("pointerleave", reset);
      window.removeEventListener("blur", reset);
      window.removeEventListener("scroll", reset);
    };
  }, []);
  return (
    <div
      ref={container}
      aria-hidden="true"
      className="pointer-events-none absolute top-0 left-0 aspect-[820/640] w-[min(820px,85vw)] overflow-hidden"
    >
      {inView &&
        planets
          .slice(0, count)
          .map((planet) => (
            <Planet
              key={planet.id}
              planet={planet}
              flipX={flipX}
              flipY={flipY}
              cursor={cursor}
              bounds={bounds}
            />
          ))}
    </div>
  );
}
