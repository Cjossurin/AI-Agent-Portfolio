import React from "react";
import {
  AbsoluteFill,
  interpolateColors,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

/* ── Types ──────────────────────────────────────────────────────────── */

interface CaptionWord {
  word: string;
  start: number;
  end: number;
}

interface CaptionGroup {
  words: CaptionWord[];
  start: number;
  end: number;
}

export interface CaptionBlockData {
  blockId: number;
  captionGroups: CaptionGroup[];
}

interface CaptionOverlayProps {
  captions: CaptionBlockData[];
  sceneDurations: number[];
}

/* ── Style constants ────────────────────────────────────────────────── */

const INACTIVE_COLOR = "#FFFFFF";
const ACTIVE_COLOR = "#FF2222"; // blood red
const FONT_SIZE = 80; // 75–85px range
const FONT_FAMILY =
  "'Creepster', 'Impact', 'Arial Black', sans-serif";

/**
 * Heavy black outline via text-shadow (all 8 directions + blur glow).
 * Ensures readability on any background while keeping a horror feel.
 */
const TEXT_SHADOW = [
  "3px 3px 0 #000",
  "-3px -3px 0 #000",
  "3px -3px 0 #000",
  "-3px 3px 0 #000",
  "0 3px 0 #000",
  "0 -3px 0 #000",
  "3px 0 0 #000",
  "-3px 0 0 #000",
  "0 0 12px rgba(0,0,0,0.9)",
  "0 0 24px rgba(0,0,0,0.5)",
].join(", ");

/* Google Fonts import — Creepster (horror typeface) */
const FONT_CSS = `@import url('https://fonts.googleapis.com/css2?family=Creepster&display=swap');`;

/* ── Component ──────────────────────────────────────────────────────── */

export const CaptionOverlay: React.FC<CaptionOverlayProps> = ({
  captions,
  sceneDurations,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Determine which scene we're in from cumulative durations
  let sceneIndex = 0;
  let sceneStartFrame = 0;
  for (let i = 0; i < sceneDurations.length; i++) {
    if (frame < sceneStartFrame + sceneDurations[i]) {
      sceneIndex = i;
      break;
    }
    sceneStartFrame += sceneDurations[i];
    if (i === sceneDurations.length - 1) {
      sceneIndex = i;
    }
  }

  const localTimeSec = (frame - sceneStartFrame) / fps;

  const captionBlock = captions[sceneIndex];
  if (!captionBlock || !captionBlock.captionGroups.length) return null;

  // Find the active caption group at this timestamp.
  // Small grace periods to prevent jarring gaps between groups.
  const activeGroup = captionBlock.captionGroups.find(
    (g) => localTimeSec >= g.start - 0.05 && localTimeSec <= g.end + 0.15,
  );

  if (!activeGroup) return null;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* Font import */}
      <style>{FONT_CSS}</style>

      {/* Caption container — vertically centered, slight lower bias */}
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: 0,
          right: 0,
          transform: "translateY(-50%)",
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "row",
            justifyContent: "center",
            alignItems: "center",
            gap: 18,
            flexWrap: "wrap",
            maxWidth: 950,
            padding: "0 40px",
          }}
        >
          {activeGroup.words.map((word, i) => {
            // Each word transitions white → blood red over ~80ms
            // as the narrator reaches it (karaoke-style color change).
            const color = interpolateColors(
              localTimeSec,
              [word.start - 0.08, word.start],
              [INACTIVE_COLOR, ACTIVE_COLOR],
            );

            return (
              <span
                key={`${activeGroup.start}-${i}`}
                style={{
                  fontFamily: FONT_FAMILY,
                  fontSize: FONT_SIZE,
                  fontWeight: 400,
                  color,
                  textTransform: "uppercase",
                  textShadow: TEXT_SHADOW,
                  letterSpacing: 2,
                  lineHeight: 1.2,
                  whiteSpace: "nowrap",
                }}
              >
                {word.word}
              </span>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
