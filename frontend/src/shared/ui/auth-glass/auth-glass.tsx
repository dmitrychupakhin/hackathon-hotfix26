"use client";

import {
  motion,
  useReducedMotion,
  useSpring,
  useTransform,
} from "motion/react";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { FIGURES } from "./auth-glass-geometry";
import { createAuthGlassRenderer } from "./auth-glass-webgl";
import map from "./refraction-map.json";

const STRIPS = [0, 1, 2, 3, 4, 5, 6];

export function AuthGlass({ children }: { children?: ReactNode }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [webglAvailable, setWebglAvailable] = useState(false);
  const id = useId().replace(/:/g, "");
  const filterId = `auth-glass-${id}`;
  const gradientId = `auth-figure-${id}`;
  const reduceMotion = useReducedMotion();
  const x = useSpring(0, { stiffness: 65, damping: 22, mass: 1 });
  const y = useSpring(0, { stiffness: 65, damping: 22, mass: 1 });
  const upperX = useTransform(x, [-1, 1], [-FIGURES[0].x, FIGURES[0].x]);
  const upperY = useTransform(y, [-1, 1], [-FIGURES[0].y, FIGURES[0].y]);
  const lowerX = useTransform(x, [-1, 1], [-FIGURES[1].x, FIGURES[1].x]);
  const lowerY = useTransform(y, [-1, 1], [-FIGURES[1].y, FIGURES[1].y]);

  useEffect(() => {
    if (reduceMotion) {
      x.jump(0);
      y.jump(0);
      return;
    }

    const onPointerMove = (event: PointerEvent) => {
      if (event.pointerType !== "mouse" && event.pointerType !== "pen") return;
      x.set(
        Math.max(-1, Math.min(1, (event.clientX / window.innerWidth) * 2 - 1)),
      );
      y.set(
        Math.max(-1, Math.min(1, (event.clientY / window.innerHeight) * 2 - 1)),
      );
    };
    const reset = () => {
      x.set(0);
      y.set(0);
    };
    const onPointerOut = (event: PointerEvent) => {
      if (!event.relatedTarget) reset();
    };

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("pointerout", onPointerOut);
    window.addEventListener("blur", reset);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerout", onPointerOut);
      window.removeEventListener("blur", reset);
    };
  }, [reduceMotion, x, y]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const renderer = createAuthGlassRenderer(canvas, map, setWebglAvailable);
    if (!renderer) return;

    const updatePointer = () => renderer.setPointer(x.get(), y.get());
    const unsubscribeX = x.on("change", updatePointer);
    const unsubscribeY = y.on("change", updatePointer);
    updatePointer();

    return () => {
      unsubscribeX();
      unsubscribeY();
      renderer.destroy();
    };
  }, [x, y]);

  return (
    <div className="relative isolate h-full min-h-[640px] overflow-hidden rounded-[24px] bg-content-0 [container-type:inline-size] after:pointer-events-none after:absolute after:inset-0 after:z-2 after:rounded-[inherit] after:shadow-[inset_0_0_0_1px_rgb(0_0_0_/_8%)] after:content-['']">
      <canvas
        ref={canvasRef}
        className="pointer-events-none absolute inset-0 size-full opacity-0 data-[active=true]:opacity-100"
        data-active={webglAvailable ? "true" : undefined}
        aria-hidden="true"
        tabIndex={-1}
      />
      <svg
        className="absolute top-0 left-0 size-[35%] origin-top-left [transform:scale(2.857143)] data-[webgl=true]:invisible"
        data-webgl={webglAvailable ? "true" : undefined}
        viewBox="0 0 912 1016"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <defs>
          <filter
            id={filterId}
            filterUnits="userSpaceOnUse"
            primitiveUnits="userSpaceOnUse"
            x="-100"
            y="-100"
            width="1112"
            height="1216"
            colorInterpolationFilters="sRGB"
          >
            <feGaussianBlur
              in="SourceGraphic"
              stdDeviation="22.79"
              result="frost"
            />
            {map && (
              <feImage
                href={map}
                x="0"
                y="0"
                width="912"
                height="1016"
                preserveAspectRatio="none"
                result="lens"
              />
            )}
            {map && (
              <feDisplacementMap
                in="frost"
                in2="lens"
                scale="80"
                xChannelSelector="R"
                yChannelSelector="G"
              />
            )}
          </filter>
        </defs>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop stopColor="#A4D36B" />
            <stop offset="1" stopColor="#D1E5B8" />
          </linearGradient>
        </defs>
        <g filter={`url(#${filterId})`}>
          <rect x="-200" y="-200" width="1312" height="1416" fill="white" />
          <motion.g data-figure="upper" style={{ x: upperX, y: upperY }}>
            <path d={FIGURES[0].path} fill={`url(#${gradientId})`} />
          </motion.g>
          <motion.g data-figure="lower" style={{ x: lowerX, y: lowerY }}>
            <path d={FIGURES[1].path} fill={`url(#${gradientId})`} />
          </motion.g>
        </g>
      </svg>
      <div className="pointer-events-none absolute inset-0 flex">
        {STRIPS.map((strip) => (
          <div
            key={strip}
            className="relative h-full min-w-0 flex-[1_1_0] border-x border-x-[rgb(255_255_255_/_10%)] first:border-l-0 before:absolute before:inset-0 before:bg-[linear-gradient(to_right,rgb(0_0_0_/_2.5%),rgb(0_0_0_/_0.9%)_12%,transparent_34%)] before:content-[''] after:absolute after:inset-0 after:shadow-[inset_1px_0_1px_rgb(255_255_255_/_70%),inset_-1px_0_4px_rgb(255_255_255_/_26%)] after:content-[''] first:after:shadow-[inset_-1px_0_4px_rgb(255_255_255_/_26%)]"
          />
        ))}
      </div>
      {children}
    </div>
  );
}
