import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { CaptionOverlay, CaptionBlockData } from "./CaptionOverlay";
import { GlitchEffects, getFrameJitter } from "./GlitchEffects";
import { KenBurnsWrapper } from "./KenBurnsWrapper";
import { TransitionGlitch } from "./TransitionGlitch";
import { VHSOverlay } from "./VHSOverlay";
import { VHSTimestamp } from "./VHSTimestamp";
import { EffectsIntensity } from "./vhsUtils";

/* ── Types ──────────────────────────────────────────────────────────── */

interface SequenceBlock {
  blockId: number;
  motionType: string;
  imagePath: string;
  audioPath: string;
  videoPath?: string;
  audioDurationSec?: number;
}

interface AmbientLayers {
  droneAudio: string;
  vhsStatic: string;
  backgroundMusic?: string;
  scareStinger?: string;
  transitionWhoosh?: string;
}

export interface CompositionProps {
  caseId: string;
  sequences: SequenceBlock[];
  ambientLayers: AmbientLayers;
  captions: CaptionBlockData[];
  effectsIntensity?: EffectsIntensity;
  showTimestamp?: boolean;
}

/* ── Constants ──────────────────────────────────────────────────────── */

const FALLBACK_SCENE_SEC = 12;
const PADDING_SEC = 0.5; // breathing room after each block's audio
const KLING_DURATION_SEC = 5; // Kling generates 5-second clips
const KLING_TRIM_FRAMES = 10; // skip ~0.33s of static padding at start/end
const KLING_FADE_IN = 8; // frames to fade in (hides remaining start padding)
const KLING_FADE_OUT = 12; // frames to fade out (smooth reveal of Ken Burns layer)
const MAX_SINGLE_IMAGE_SEC = 10; // max seconds any single image stays on screen

/* ── Ken Burns motion cycle — used to vary visuals in long blocks ── */
const KB_MOTION_CYCLE = [
  "ken_burns_zoom_in",
  "ken_burns_pan_right",
  "ken_burns_slow_push",
  "ken_burns_pan_left",
  "ken_burns_zoom_out",
] as const;

/** Split a block's frame duration into sub-segments of ≤ MAX_SINGLE_IMAGE_SEC.
 *  Returns an array of { fromOffset, frames, motionType } relative to the block start. */
function computeSubSegments(
  totalFrames: number,
  fps: number,
  baseMotion: string,
): { fromOffset: number; frames: number; motionType: string }[] {
  const maxFrames = Math.ceil(MAX_SINGLE_IMAGE_SEC * fps);
  if (totalFrames <= maxFrames) {
    return [{ fromOffset: 0, frames: totalFrames, motionType: baseMotion }];
  }
  const segments: { fromOffset: number; frames: number; motionType: string }[] = [];
  let remaining = totalFrames;
  let offset = 0;
  let motionIdx = KB_MOTION_CYCLE.indexOf(baseMotion);
  if (motionIdx < 0) motionIdx = 0;
  while (remaining > 0) {
    const segFrames = Math.min(maxFrames, remaining);
    segments.push({
      fromOffset: offset,
      frames: segFrames,
      motionType: KB_MOTION_CYCLE[motionIdx % KB_MOTION_CYCLE.length],
    });
    offset += segFrames;
    remaining -= segFrames;
    motionIdx++;
  }
  return segments;
}

/* ── Volume mix ──────────────────────────────────────────────────────
 * Narration = 1.0   (primary — always loud and clear)
 * Scare SFX = 0.55  (Kling video audio)
 * Drone     = 0.12  (background texture — lowered to make room for music)
 * VHS hiss  = 0.05  (subtle analog feel)
 * Music     = 0.16  (horror score — audible backdrop, not competing)
 * Stinger   = 0.55  (jump scare hit — punchy but not jarring)
 * Whoosh    = 0.25  (dark scene transition — present but subtle)
 * ────────────────────────────────────────────────────────────────── */
const VOL_NARRATION = 1.0;
const VOL_SCARE_SFX = 0.55;
const VOL_DRONE = 0.12;
const VOL_VHS = 0.05;
const VOL_MUSIC = 0.16;
const VOL_STINGER = 0.55;
const VOL_WHOOSH = 0.25;

/* ── Scare video overlay — fades in/out to hide Kling's static padding ── */

const ScareVideoOverlay: React.FC<{
  videoPath: string;
  durationInFrames: number;
}> = ({ videoPath, durationInFrames }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(
    frame,
    [0, KLING_FADE_IN, durationInFrames - KLING_FADE_OUT, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  return (
    <AbsoluteFill style={{ opacity }}>
      <OffthreadVideo
        src={staticFile(videoPath)}
        startFrom={KLING_TRIM_FRAMES}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
};

/* ── Helpers ────────────────────────────────────────────────────────── */

/** Compute per-scene frame counts and cumulative start offsets. */
function computeSceneTiming(sequences: SequenceBlock[], fps: number) {
  const durations: number[] = [];
  const offsets: number[] = [];
  let running = 0;

  for (const seq of sequences) {
    const dur = Math.ceil(
      ((seq.audioDurationSec ?? FALLBACK_SCENE_SEC) + PADDING_SEC) * fps,
    );
    offsets.push(running);
    durations.push(dur);
    running += dur;
  }

  return { durations, offsets, totalFrames: running };
}

/* ── Root Composition ─────────────────────────────────────────────── */

export const RootComposition: React.FC<CompositionProps> = ({
  sequences,
  ambientLayers,
  captions,
  effectsIntensity = "medium",
  showTimestamp = true,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { durations, offsets, totalFrames } = computeSceneTiming(sequences, fps);

  // Frame jitter — micro-displacement during glitch events
  const jitter = getFrameJitter(frame, effectsIntensity);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* ── Layer 1: Narration audio per block ─────────────────────── */}
      {sequences.map((seq, i) => (
        <Sequence
          key={`audio-${seq.blockId}`}
          from={offsets[i]}
          durationInFrames={durations[i]}
        >
          {seq.audioPath && <Audio src={staticFile(seq.audioPath)} volume={VOL_NARRATION} />}
        </Sequence>
      ))}

      {/* ── Layer 2: SFX — scare video audio (if present) ─────────── */}
      {sequences.map((seq, i) =>
        seq.videoPath ? (
          <Sequence
            key={`sfx-${seq.blockId}`}
            from={offsets[i]}
            durationInFrames={durations[i]}
          >
            <Audio src={staticFile(seq.videoPath)} volume={VOL_SCARE_SFX} />
          </Sequence>
        ) : null,
      )}

      {/* ── Layer 3: Horror drone ──────────────────────────────────── */}
      <Sequence from={0} durationInFrames={totalFrames}>
        <Audio src={staticFile(ambientLayers.droneAudio)} volume={VOL_DRONE} loop />
      </Sequence>

      {/* ── Layer 4: VHS static hiss ───────────────────────────────── */}
      <Sequence from={0} durationInFrames={totalFrames}>
        <Audio src={staticFile(ambientLayers.vhsStatic)} volume={VOL_VHS} loop />
      </Sequence>

      {/* ── Layer 5: Background music — low horror bed, looped ─────── */}
      {ambientLayers.backgroundMusic && (
        <Sequence from={0} durationInFrames={totalFrames}>
          <Audio src={staticFile(ambientLayers.backgroundMusic)} volume={VOL_MUSIC} loop />
        </Sequence>
      )}

      {/* ── Layer 6: Scare stinger — plays at start of each scare block */}
      {ambientLayers.scareStinger &&
        sequences.map((seq, i) =>
          seq.motionType === "kling_i2v_scare" && seq.videoPath ? (
            <Sequence
              key={`stinger-${seq.blockId}`}
              from={offsets[i]}
              durationInFrames={Math.ceil(2 * fps)}
            >
              <Audio src={staticFile(ambientLayers.scareStinger!)} volume={VOL_STINGER} />
            </Sequence>
          ) : null,
        )}

      {/* ── Layer 7: Transition whoosh — between blocks (skip first) ── */}
      {ambientLayers.transitionWhoosh &&
        sequences.map((seq, i) =>
          i > 0 ? (
            <Sequence
              key={`whoosh-${seq.blockId}`}
              from={Math.max(0, offsets[i] - Math.ceil(0.3 * fps))}
              durationInFrames={Math.ceil(1.5 * fps)}
            >
              <Audio src={staticFile(ambientLayers.transitionWhoosh!)} volume={VOL_WHOOSH} />
            </Sequence>
          ) : null,
        )}

      {/* ── Visual layer: images / videos per block ────────────────── */}
      {sequences.map((seq, i) => {
        // Determine a fallback image: use previous block's image (or own for block 0)
        const fallbackImage =
          i > 0 ? sequences[i - 1].imagePath : seq.imagePath;

        // For scare blocks, the Ken Burns layer underneath uses the PREVIOUS
        // block's image (or own for block 0) so that when the scare video
        // fades out, the reveal is a different image than the next block.
        const kenBurnsImage =
          seq.motionType === "kling_i2v_scare"
            ? (i > 0 ? sequences[i - 1].imagePath : seq.imagePath)
            : seq.imagePath;

        // Base motion for Ken Burns (scare blocks default to zoom_in)
        const baseMotion =
          seq.motionType === "kling_i2v_scare"
            ? "ken_burns_zoom_in"
            : seq.motionType;

        // Split long blocks into visual sub-segments so no image stays > 10s
        const subSegs = computeSubSegments(durations[i], fps, baseMotion);

        return (
          <Sequence
            key={`visual-${seq.blockId}`}
            from={offsets[i]}
            durationInFrames={durations[i]}
          >
            {/* Transition glitch at scene boundaries */}
            <TransitionGlitch durationInFrames={durations[i]} intensity={effectsIntensity}>
              {/* Color degradation + frame jitter wrapper */}
              <AbsoluteFill
                style={{
                  filter: "saturate(0.75) contrast(1.05) brightness(0.95) sepia(0.08)",
                  transform: `translate(${jitter.x}px, ${jitter.y}px)`,
                }}
              >
                {/* Static fallback image — prevents black screen if primary fails */}
                <Img
                  src={staticFile(fallbackImage)}
                  style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                    position: "absolute",
                    top: 0,
                    left: 0,
                  }}
                />

                {/* Ken Burns sub-segments — each ≤ MAX_SINGLE_IMAGE_SEC with
                    a different motion so the visual stays dynamic */}
                {subSegs.map((sub, si) => (
                  <Sequence
                    key={`kb-${seq.blockId}-${si}`}
                    from={sub.fromOffset}
                    durationInFrames={sub.frames}
                  >
                    <KenBurnsWrapper
                      motionType={sub.motionType}
                      durationInFrames={sub.frames}
                    >
                      <Img
                        src={staticFile(kenBurnsImage)}
                        style={{
                          width: "100%",
                          height: "100%",
                          objectFit: "cover",
                        }}
                      />
                    </KenBurnsWrapper>
                  </Sequence>
                ))}

                {/* Overlay Kling scare video — trimmed & crossfaded to hide static padding */}
                {seq.motionType === "kling_i2v_scare" && seq.videoPath && (() => {
                  const scareFrames = Math.ceil(KLING_DURATION_SEC * fps) - KLING_TRIM_FRAMES * 2;
                  return (
                    <Sequence from={0} durationInFrames={scareFrames}>
                      <ScareVideoOverlay
                        videoPath={seq.videoPath}
                        durationInFrames={scareFrames}
                      />
                    </Sequence>
                  );
                })()}
              </AbsoluteFill>
            </TransitionGlitch>
          </Sequence>
        );
      })}

      {/* ── Caption overlay — karaoke-style word highlights ────────── */}
      {captions && captions.length > 0 && (
        <Sequence from={0} durationInFrames={totalFrames}>
          <CaptionOverlay
            captions={captions}
            sceneDurations={durations}
          />
        </Sequence>
      )}

      {/* ── Glitch effects — intermittent bursts ──────────────────── */}
      <Sequence from={0} durationInFrames={totalFrames}>
        <GlitchEffects intensity={effectsIntensity} />
      </Sequence>

      {/* ── VHS overlay on top of everything ───────────────────────── */}
      <Sequence from={0} durationInFrames={totalFrames}>
        <VHSOverlay intensity={effectsIntensity} />
      </Sequence>

      {/* ── VHS timestamp — optional "REC" + date/time ─────────────── */}
      {showTimestamp && (
        <Sequence from={0} durationInFrames={totalFrames}>
          <VHSTimestamp intensity={effectsIntensity} />
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
