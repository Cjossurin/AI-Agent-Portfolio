import React, { useRef, useEffect } from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { noise2D } from "@remotion/noise";
import { EffectsIntensity, INTENSITY, seededRandom } from "./vhsUtils";

/**
 * Enhanced VHS overlay with lost-footage artifacts.
 *
 * Always-on ambient layers:
 *  1. Horizontal scanlines (drifting)
 *  2. Dark vignette
 *  3. Chromatic aberration (animated RGB channel split)
 *  4. Opacity flicker
 *  5. VHS tracking lines (drifting horizontal bands)
 *  6. Rolling horizontal bar (CRT wash)
 *  7. Tape-head switching noise (bottom-of-frame bar)
 *  8. Real film grain (canvas-rendered per-frame noise)
 */
export const VHSOverlay: React.FC<{ intensity?: EffectsIntensity }> = ({
  intensity = "medium",
}) => {
  const frame = useCurrentFrame();
  const { height, width } = useVideoConfig();
  const s = INTENSITY[intensity].strength;

  // ── Flicker: oscillate opacity between 0.90 and 1.0
  const flicker = interpolate(Math.sin(frame * 0.8), [-1, 1], [0.90, 1.0]);

  // ── Scanline drift
  const scanlineOffset = (frame * 0.3) % 4;

  // ── Chromatic aberration: pulsing RGB offset (2–4px)
  const caOffset = 2 + Math.sin(frame * 0.15) * 2 * s;

  // ── Rolling bar: scrolls top→bottom every ~210 frames (~7s @ 30fps)
  const rollCycle = 210;
  const rollY = ((frame % rollCycle) / rollCycle) * (height + 80) - 80;

  // ── Tracking lines: 3 bands that drift at different speeds
  const trackY1 = ((frame * 0.7 + 100) % (height + 40)) - 20;
  const trackY2 = ((frame * 1.1 + 600) % (height + 40)) - 20;
  const trackY3 = ((frame * 0.5 + 350) % (height + 40)) - 20;
  // Slight horizontal jitter per band
  const trackJitter1 = noise2D("t1", frame * 0.05, 0) * 8 * s;
  const trackJitter2 = noise2D("t2", frame * 0.05, 0) * 6 * s;
  const trackJitter3 = noise2D("t3", frame * 0.05, 0) * 10 * s;

  // ── Tape-head switching: horizontal jitter at the very bottom
  const tapeHeadJitter = noise2D("th", frame * 0.1, 0) * 12 * s;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* 1. Scanlines */}
      <AbsoluteFill
        style={{
          backgroundImage: `repeating-linear-gradient(
            0deg,
            transparent,
            transparent 2px,
            rgba(0, 0, 0, 0.18) 2px,
            rgba(0, 0, 0, 0.18) 4px
          )`,
          backgroundPositionY: `${scanlineOffset}px`,
          mixBlendMode: "multiply",
          opacity: flicker,
        }}
      />

      {/* 2. Vignette */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,0.75) 100%)",
        }}
      />

      {/* 3. Chromatic aberration — red channel offset */}
      <AbsoluteFill
        style={{
          mixBlendMode: "screen",
          opacity: 0.06 * s,
          background: "transparent",
          boxShadow: `inset ${caOffset}px 0 0 rgba(255,0,0,0.6), inset ${-caOffset}px 0 0 rgba(0,255,255,0.6)`,
        }}
      />

      {/* 4. Flicker — global opacity pulse (applied to a tinted layer) */}
      <AbsoluteFill
        style={{
          backgroundColor: `rgba(255,255,255,${0.01 * s})`,
          opacity: flicker,
          mixBlendMode: "overlay",
        }}
      />

      {/* 5. VHS tracking lines — drifting horizontal bands */}
      {[
        { y: trackY1, jitter: trackJitter1, h: 14, opacity: 0.08 },
        { y: trackY2, jitter: trackJitter2, h: 10, opacity: 0.06 },
        { y: trackY3, jitter: trackJitter3, h: 18, opacity: 0.05 },
      ].map((band, idx) => (
        <div
          key={`track-${idx}`}
          style={{
            position: "absolute",
            top: band.y,
            left: 0,
            width: "100%",
            height: band.h,
            background: `linear-gradient(
              0deg,
              transparent,
              rgba(255,255,255,${band.opacity * s}) 30%,
              rgba(255,255,255,${band.opacity * s}) 70%,
              transparent
            )`,
            transform: `translateX(${band.jitter}px)`,
            mixBlendMode: "overlay",
            pointerEvents: "none",
          }}
        />
      ))}

      {/* 6. Rolling horizontal bar — CRT wash effect */}
      <div
        style={{
          position: "absolute",
          top: rollY,
          left: 0,
          width: "100%",
          height: 70,
          background: `linear-gradient(
            0deg,
            transparent,
            rgba(255,255,255,${0.05 * s}) 35%,
            rgba(255,255,255,${0.07 * s}) 50%,
            rgba(255,255,255,${0.05 * s}) 65%,
            transparent
          )`,
          mixBlendMode: "overlay",
          pointerEvents: "none",
        }}
      />

      {/* 7. Tape-head switching noise — bottom-of-frame distortion */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          width: "100%",
          height: 25,
          background: `repeating-linear-gradient(
            90deg,
            rgba(255,255,255,${0.12 * s}),
            rgba(255,255,255,${0.12 * s}) 1px,
            transparent 1px,
            transparent 3px
          )`,
          transform: `translateX(${tapeHeadJitter}px)`,
          mixBlendMode: "overlay",
          pointerEvents: "none",
        }}
      />

      {/* 8. Film grain — canvas-rendered per-frame noise */}
      <NoiseGrain frame={frame} width={width} height={height} strength={s} />
    </AbsoluteFill>
  );
};

/* ── Film grain canvas ─────────────────────────────────────────────── */

const GRAIN_SCALE = 4; // render at 1/4 resolution, scale up for performance

const NoiseGrain: React.FC<{
  frame: number;
  width: number;
  height: number;
  strength: number;
}> = ({ frame, width, height, strength }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const w = Math.ceil(width / GRAIN_SCALE);
  const h = Math.ceil(height / GRAIN_SCALE);

  useEffect(() => {
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    const imgData = ctx.createImageData(w, h);
    const data = imgData.data;
    for (let i = 0; i < data.length; i += 4) {
      const v = Math.floor(seededRandom(frame * 100003 + i) * 255);
      data[i] = v;
      data[i + 1] = v;
      data[i + 2] = v;
      data[i + 3] = 255;
    }
    ctx.putImageData(imgData, 0, 0);
  }, [frame, w, h]);

  return (
    <canvas
      ref={canvasRef}
      width={w}
      height={h}
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        opacity: 0.045 * strength,
        mixBlendMode: "overlay",
        pointerEvents: "none",
        imageRendering: "pixelated",
      }}
    />
  );
};
