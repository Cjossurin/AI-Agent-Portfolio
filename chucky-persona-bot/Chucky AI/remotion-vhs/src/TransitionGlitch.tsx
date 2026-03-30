import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { EffectsIntensity, INTENSITY, seededRandom, seededRange } from "./vhsUtils";

/**
 * Heavy glitch burst that fires at the boundaries of each scene:
 *   - Last ~8 frames of the outgoing scene
 *   - First ~5 frames of the incoming scene
 *
 * Wrap each per-block visual Sequence's content with this component.
 * It reads `useCurrentFrame()` relative to the Sequence it lives inside.
 */

const OUTRO_FRAMES = 8;
const INTRO_FRAMES = 5;

export const TransitionGlitch: React.FC<{
  durationInFrames: number;
  intensity?: EffectsIntensity;
  children: React.ReactNode;
}> = ({ durationInFrames, intensity = "medium", children }) => {
  const frame = useCurrentFrame();
  const s = INTENSITY[intensity].strength;

  const isInIntro = frame < INTRO_FRAMES;
  const isInOutro = frame >= durationInFrames - OUTRO_FRAMES;
  const isActive = isInIntro || isInOutro;

  if (!isActive) {
    return <>{children}</>;
  }

  // Progress within the transition zone (0→1)
  const progress = isInIntro
    ? interpolate(frame, [0, INTRO_FRAMES], [1, 0], { extrapolateRight: "clamp" })
    : interpolate(frame, [durationInFrames - OUTRO_FRAMES, durationInFrames], [0, 1], {
        extrapolateLeft: "clamp",
      });

  // Horizontal tear offset — increases with progress
  const tearOffset = seededRange(frame * 4447, -40, 40) * progress * s;

  // Brief brightness/contrast flash
  const flash = 1 + progress * 0.2 * s;

  // Static noise opacity
  const noiseOpacity = progress * 0.25 * s;

  // Chromatic split intensity
  const rgbSplit = progress * 6 * s;

  return (
    <AbsoluteFill>
      {/* Content with jitter + color filter */}
      <AbsoluteFill
        style={{
          transform: `translateX(${tearOffset * 0.4}px) translateY(${seededRange(frame * 2221, -2, 2) * progress * s}px)`,
          filter: `brightness(${flash}) contrast(${1 + progress * 0.08 * s})`,
        }}
      >
        {children}
      </AbsoluteFill>

      {/* Horizontal tearing bands */}
      <TransitionTears frame={frame} progress={progress} strength={s} />

      {/* RGB split flash */}
      <AbsoluteFill
        style={{
          pointerEvents: "none",
          mixBlendMode: "screen",
          opacity: progress * 0.12 * s,
          boxShadow: `inset ${rgbSplit}px 0 0 rgba(255,0,0,0.5), inset ${-rgbSplit}px 0 0 rgba(0,255,255,0.5)`,
        }}
      />

      {/* White flash overlay */}
      <AbsoluteFill
        style={{
          pointerEvents: "none",
          backgroundColor: `rgba(255,255,255,${noiseOpacity * 0.4})`,
          mixBlendMode: "overlay",
        }}
      />
    </AbsoluteFill>
  );
};

/* ── Horizontal tearing bands for transitions ──────────────────────── */

const TransitionTears: React.FC<{
  frame: number;
  progress: number;
  strength: number;
}> = ({ frame, progress, strength }) => {
  const tearCount = 3 + Math.floor(progress * 5);
  const tears: React.ReactNode[] = [];

  for (let i = 0; i < tearCount; i++) {
    const seed = frame * 3000 + i * 53;
    const y = `${seededRange(seed, 5, 95)}%`;
    const h = 4 + seededRandom(seed + 1) * 20 * progress;
    const offsetX = seededRange(seed + 2, -60, 60) * progress * strength;

    tears.push(
      <div
        key={`tt-${i}`}
        style={{
          position: "absolute",
          top: y,
          left: 0,
          width: "100%",
          height: h,
          background: `linear-gradient(90deg,
            transparent 0%,
            rgba(255,255,255,${0.12 * strength * progress}) 20%,
            rgba(255,255,255,${0.15 * strength * progress}) 50%,
            rgba(255,255,255,${0.12 * strength * progress}) 80%,
            transparent 100%
          )`,
          transform: `translateX(${offsetX}px)`,
          mixBlendMode: "overlay",
          pointerEvents: "none",
        }}
      />,
    );
  }

  return <>{tears}</>;
};
