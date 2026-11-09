"use client";

import {
  type MotionValue,
  motion,
  useMotionValue,
  useReducedMotion,
  useSpring,
  useTransform,
} from "motion/react";
import { useEffect, useRef } from "react";

const radii = [240, 390, 540];
const spring = { stiffness: 130, damping: 22, mass: 0.7 };

function Ellipse({
  radius,
  x,
  y,
  influence,
  index,
}: {
  index: number;
  radius: number;
  x: MotionValue<number>;
  y: MotionValue<number>;
  influence: MotionValue<number>;
}) {
  const reducedMotion = useReducedMotion();
  const direction = index % 2 === 0 ? 1 : -1;
  const path = useTransform(() => {
    const cursorX = x.get();
    const cursorY = y.get();
    const strength = influence.get();
    const points = Array.from({ length: 129 }, (_, index) => {
      const angle = (index / 128) * Math.PI * 2;
      const px = Math.cos(angle) * radius;
      const py = Math.sin(angle) * radius * 0.8;
      const distance = Math.hypot(cursorX - px, cursorY - py);
      const pull = Math.exp(-((distance / 150) ** 2)) * 0.28 * strength;
      return `${index === 0 ? "M" : "L"}${(px + (cursorX - px) * pull).toFixed(2)},${(py + (cursorY - py) * pull).toFixed(2)}`;
    });
    return `${points.join(" ")} Z`;
  });
  return (
    <motion.g
      style={{ originX: "0px", originY: "0px" }}
      animate={
        reducedMotion
          ? { rotate: 0, scale: 1 }
          : {
              rotate: [0, 6 * direction, 0, -6 * direction, 0],
              scale: [1, 1.035, 1, 0.965, 1],
            }
      }
      transition={{
        duration: 16 + index * 6,
        repeat: Infinity,
        ease: "easeInOut",
      }}
    >
      <motion.path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeWidth={1}
        vectorEffect="non-scaling-stroke"
      />
    </motion.g>
  );
}

export function InteractiveEllipses({
  count = 3,
  flipX = false,
  flipY = false,
}: {
  count?: number;
  flipX?: boolean;
  flipY?: boolean;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const reducedMotion = useReducedMotion();
  const x = useSpring(useMotionValue(0), spring);
  const y = useSpring(useMotionValue(0), spring);
  const influence = useSpring(useMotionValue(0), spring);

  useEffect(() => {
    if (reducedMotion) return;
    function reset() {
      influence.set(0);
    }
    function move(event: PointerEvent) {
      const svg = ref.current;
      if (!svg || event.pointerType === "touch") {
        reset();
        return;
      }
      const rect = svg.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const localX =
        ((flipX ? rect.right - event.clientX : event.clientX - rect.left) *
          640) /
        rect.width;
      const localY =
        ((flipY ? rect.bottom - event.clientY : event.clientY - rect.top) *
          520) /
        rect.height;
      const nearby =
        localX > -100 && localX < 740 && localY > -100 && localY < 620;
      if (!nearby) {
        reset();
        return;
      }
      x.set(localX);
      y.set(localY);
      influence.set(1);
    }
    window.addEventListener("pointermove", move, { passive: true });
    document.addEventListener("pointerleave", reset);
    window.addEventListener("blur", reset);
    return () => {
      window.removeEventListener("pointermove", move);
      document.removeEventListener("pointerleave", reset);
      window.removeEventListener("blur", reset);
    };
  }, [x, y, influence, reducedMotion, flipX, flipY]);

  return (
    <svg
      ref={ref}
      aria-hidden="true"
      viewBox="0 0 640 520"
      className="pointer-events-none absolute top-0 left-0 h-auto w-[min(640px,65vw)] overflow-hidden text-special-300"
    >
      {radii.slice(0, count).map((radius, index) => (
        <Ellipse
          key={radius}
          radius={radius}
          index={index}
          x={x}
          y={y}
          influence={influence}
        />
      ))}
    </svg>
  );
}
