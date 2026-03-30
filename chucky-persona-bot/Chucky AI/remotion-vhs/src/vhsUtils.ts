/**
 * Shared utilities for VHS / lost-footage / glitch effects.
 *
 * All randomness is seeded by frame number so Remotion renders are
 * deterministic (identical output across multiple renders).
 */

/* ── Intensity presets ──────────────────────────────────────────────── */

export type EffectsIntensity = "subtle" | "medium" | "heavy";

interface IntensityConfig {
  /** Multiplier applied to most opacity / displacement values. */
  strength: number;
  /** Glitch block event fires roughly every N frames. */
  glitchInterval: number;
  /** Duration of a glitch block event in frames. */
  glitchDuration: number;
  /** Full-screen static burst fires roughly every N frames. */
  staticInterval: number;
  /** Duration of a static burst in frames. */
  staticDuration: number;
  /** Heavy signal-loss event fires roughly every N frames. */
  signalLossInterval: number;
  /** Duration of a signal-loss event in frames. */
  signalLossDuration: number;
}

export const INTENSITY: Record<EffectsIntensity, IntensityConfig> = {
  subtle: {
    strength: 0.5,
    glitchInterval: 180,
    glitchDuration: 2,
    staticInterval: 300,
    staticDuration: 3,
    signalLossInterval: 1200,
    signalLossDuration: 6,
  },
  medium: {
    strength: 1.0,
    glitchInterval: 120,
    glitchDuration: 3,
    staticInterval: 200,
    staticDuration: 5,
    signalLossInterval: 750,
    signalLossDuration: 10,
  },
  heavy: {
    strength: 1.6,
    glitchInterval: 75,
    glitchDuration: 4,
    staticInterval: 120,
    staticDuration: 6,
    signalLossInterval: 450,
    signalLossDuration: 14,
  },
};

/* ── Deterministic pseudo-random (Mulberry32) ──────────────────────── */

export function seededRandom(seed: number): number {
  let t = (seed + 0x6d2b79f5) | 0;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

/** Returns a deterministic float in [min, max). */
export function seededRange(seed: number, min: number, max: number): number {
  return min + seededRandom(seed) * (max - min);
}

/* ── Glitch event timing ───────────────────────────────────────────── */

/**
 * Returns true when `frame` falls inside one of the periodic glitch windows.
 *
 * Events fire every `interval` frames and last `duration` frames.
 * The `offset` parameter shifts the pattern so different effect types
 * don't always fire on the exact same frames.
 */
export function isInGlitchWindow(
  frame: number,
  interval: number,
  duration: number,
  offset = 0,
): boolean {
  const shifted = frame + offset;
  return shifted % interval < duration;
}

/**
 * Returns how many frames into the current glitch window we are (0-based),
 * or -1 if we're not in a window.
 */
export function glitchProgress(
  frame: number,
  interval: number,
  duration: number,
  offset = 0,
): number {
  const shifted = frame + offset;
  const pos = shifted % interval;
  return pos < duration ? pos : -1;
}
