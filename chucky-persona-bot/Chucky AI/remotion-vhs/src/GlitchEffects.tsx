import React, { useRef, useEffect } from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import {
  EffectsIntensity,
  INTENSITY,
  seededRandom,
  seededRange,
  isInGlitchWindow,
  glitchProgress,
} from "./vhsUtils";

/**
 * Intermittent glitch effects that fire periodically to simulate
 * corrupted / lost footage artifacts.
 *
 * Events:
 *  1. Glitch block displacement — colored rectangles shifted horizontally
 *  2. TV static / snow bursts — full-screen canvas noise
 *  3. Signal loss moments — rare heavy degradation ("tape getting eaten")
 */
export const GlitchEffects: React.FC<{ intensity?: EffectsIntensity }> = ({
  intensity = "medium",
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const cfg = INTENSITY[intensity];
  const s = cfg.strength;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* 1. Glitch block displacement */}
      <GlitchBlocks
        frame={frame}
        width={width}
        height={height}
        interval={cfg.glitchInterval}
        duration={cfg.glitchDuration}
        strength={s}
      />

      {/* 2. TV static / snow burst */}
      <StaticBurst
        frame={frame}
        width={width}
        height={height}
        interval={cfg.staticInterval}
        duration={cfg.staticDuration}
        strength={s}
      />

      {/* 3. Signal loss — rare heavy event */}
      <SignalLoss
        frame={frame}
        width={width}
        height={height}
        interval={cfg.signalLossInterval}
        duration={cfg.signalLossDuration}
        strength={s}
      />
    </AbsoluteFill>
  );
};

/* ── Glitch blocks ─────────────────────────────────────────────────── */

const GlitchBlocks: React.FC<{
  frame: number;
  width: number;
  height: number;
  interval: number;
  duration: number;
  strength: number;
}> = ({ frame, width, height, interval, duration, strength }) => {
  const prog = glitchProgress(frame, interval, duration, 0);
  if (prog < 0) return null;

  // Generate 2-5 blocks deterministically
  const blockCount = 2 + Math.floor(seededRandom(frame * 7919) * 4);
  const blocks: React.ReactNode[] = [];

  for (let i = 0; i < blockCount; i++) {
    const seed = frame * 1000 + i * 137;
    const blockHeight = 30 + seededRandom(seed) * 90;
    const y = seededRange(seed + 1, 0, height - blockHeight);
    const offsetX = seededRange(seed + 2, -50, 50) * strength;
    const isRed = seededRandom(seed + 3) > 0.5;
    const color = isRed ? "rgba(255,0,50,0.25)" : "rgba(0,200,255,0.25)";
    const opacity = interpolate(prog, [0, duration - 1], [0.8, 0.3], {
      extrapolateRight: "clamp",
    });

    blocks.push(
      <div
        key={`gb-${i}`}
        style={{
          position: "absolute",
          left: 0,
          top: y,
          width: "100%",
          height: blockHeight,
          backgroundColor: color,
          transform: `translateX(${offsetX}px)`,
          opacity: opacity * strength,
          mixBlendMode: "screen",
          pointerEvents: "none",
        }}
      />,
    );
  }

  return <>{blocks}</>;
};

/* ── TV static / snow burst ────────────────────────────────────────── */

const STATIC_SCALE = 4; // render at 1/4 resolution

const StaticBurst: React.FC<{
  frame: number;
  width: number;
  height: number;
  interval: number;
  duration: number;
  strength: number;
}> = ({ frame, width, height, interval, duration, strength }) => {
  const prog = glitchProgress(frame, interval, duration, 47);
  if (prog < 0) return null;

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const w = Math.ceil(width / STATIC_SCALE);
  const h = Math.ceil(height / STATIC_SCALE);

  // Opacity ramps in and out
  const opacity = interpolate(prog, [0, 1, duration - 2, duration - 1], [0, 0.35, 0.35, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  useEffect(() => {
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    const imgData = ctx.createImageData(w, h);
    const data = imgData.data;
    for (let i = 0; i < data.length; i += 4) {
      const v = Math.floor(seededRandom(frame * 200003 + i + prog * 9999) * 255);
      data[i] = v;
      data[i + 1] = v;
      data[i + 2] = v;
      data[i + 3] = 255;
    }
    ctx.putImageData(imgData, 0, 0);
  }, [frame, prog, w, h]);

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
        opacity: opacity * strength,
        mixBlendMode: "overlay",
        pointerEvents: "none",
        imageRendering: "pixelated",
      }}
    />
  );
};

/* ── Signal loss — the "tape getting eaten" moment ─────────────────── */

const SignalLoss: React.FC<{
  frame: number;
  width: number;
  height: number;
  interval: number;
  duration: number;
  strength: number;
}> = ({ frame, height, interval, duration, strength }) => {
  const prog = glitchProgress(frame, interval, duration, 83);
  if (prog < 0) return null;

  // Envelope: ramp in 3 frames, sustain, ramp out 3 frames
  const envelope = interpolate(
    prog,
    [0, 3, duration - 3, duration - 1],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  // Heavy horizontal tearing: multiple offset bands
  const tearCount = 6 + Math.floor(seededRandom(frame * 3331) * 6);
  const tears: React.ReactNode[] = [];
  for (let i = 0; i < tearCount; i++) {
    const seed = frame * 5000 + i * 71;
    const y = seededRange(seed, 0, height);
    const tearH = 8 + seededRandom(seed + 1) * 40;
    const offsetX = seededRange(seed + 2, -80, 80) * strength;
    tears.push(
      <div
        key={`tear-${i}`}
        style={{
          position: "absolute",
          top: y,
          left: 0,
          width: "100%",
          height: tearH,
          background: `linear-gradient(90deg,
            rgba(255,255,255,${0.15 * strength}) 0%,
            rgba(200,200,200,${0.1 * strength}) 50%,
            transparent 100%
          )`,
          transform: `translateX(${offsetX}px)`,
          mixBlendMode: "overlay",
          pointerEvents: "none",
        }}
      />,
    );
  }

  // Brightness spike
  const brightness = 1 + envelope * 0.15 * strength;

  return (
    <AbsoluteFill
      style={{
        opacity: envelope,
        filter: `brightness(${brightness})`,
        pointerEvents: "none",
      }}
    >
      {/* Color channel explosion */}
      <AbsoluteFill
        style={{
          background: `linear-gradient(
            ${seededRange(frame, 0, 360)}deg,
            rgba(255,0,0,${0.08 * strength}),
            rgba(0,255,255,${0.08 * strength})
          )`,
          mixBlendMode: "screen",
        }}
      />

      {/* Horizontal tearing bands */}
      {tears}

      {/* Heavy noise overlay */}
      <AbsoluteFill
        style={{
          backgroundColor: `rgba(255,255,255,${0.06 * strength * envelope})`,
          mixBlendMode: "overlay",
        }}
      />
    </AbsoluteFill>
  );
};

/* ── Frame jitter helper (exported for use in Composition.tsx) ─────── */

/**
 * Returns { x, y } displacement values for the current frame.
 * Only non-zero during active glitch/signal-loss windows.
 */
export function getFrameJitter(
  frame: number,
  intensity: EffectsIntensity = "medium",
): { x: number; y: number } {
  const cfg = INTENSITY[intensity];
  const s = cfg.strength;

  const inGlitch = isInGlitchWindow(frame, cfg.glitchInterval, cfg.glitchDuration, 0);
  const inSignalLoss = isInGlitchWindow(frame, cfg.signalLossInterval, cfg.signalLossDuration, 83);

  if (!inGlitch && !inSignalLoss) return { x: 0, y: 0 };

  const magnitude = inSignalLoss ? 4 : 2;
  return {
    x: seededRange(frame * 8887, -magnitude, magnitude) * s,
    y: seededRange(frame * 9973, -magnitude, magnitude) * s,
  };
}
