import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { EffectsIntensity, INTENSITY, seededRandom } from "./vhsUtils";

/**
 * VHS-style "REC" indicator + fake date/time counter.
 *
 * Renders in the top-right corner with a blinking red dot,
 * monospace font, and subtle flicker — like camcorder footage.
 */
export const VHSTimestamp: React.FC<{
  intensity?: EffectsIntensity;
}> = ({ intensity = "medium" }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = INTENSITY[intensity].strength;

  // Blinking REC dot — toggles every ~20 frames
  const dotVisible = Math.floor(frame / 20) % 2 === 0;

  // Fake date: fixed at a creepy 90s date, time increments from a start point
  const baseHour = 2;
  const baseMin = 34;
  const totalSeconds = Math.floor(frame / fps);
  const seconds = totalSeconds % 60;
  const minutes = (baseMin + Math.floor(totalSeconds / 60)) % 60;
  const hours = (baseHour + Math.floor((baseMin + Math.floor(totalSeconds / 60)) / 60)) % 12;
  const timeStr = `${String(hours || 12).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")} AM`;

  // Subtle flicker on the text
  const textFlicker = interpolate(
    Math.sin(frame * 1.2 + seededRandom(frame * 31) * 2),
    [-1, 1],
    [0.7, 1.0],
  );

  return (
    <div
      style={{
        position: "absolute",
        top: 40,
        right: 30,
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-end",
        fontFamily: "'Courier New', 'Courier', monospace",
        color: "rgba(255,255,255,0.75)",
        fontSize: 28,
        letterSpacing: 2,
        textShadow: "1px 1px 4px rgba(0,0,0,0.8)",
        opacity: textFlicker * (0.6 + 0.4 * s),
        pointerEvents: "none",
        userSelect: "none",
      }}
    >
      {/* REC indicator */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div
          style={{
            width: 12,
            height: 12,
            borderRadius: "50%",
            backgroundColor: dotVisible ? "#ff2020" : "transparent",
            boxShadow: dotVisible ? "0 0 6px 2px rgba(255,32,32,0.6)" : "none",
          }}
        />
        <span style={{ fontWeight: "bold" }}>REC</span>
      </div>

      {/* Date line */}
      <div style={{ fontSize: 22, marginTop: 4, opacity: 0.85 }}>
        JAN 15 1997
      </div>

      {/* Time line */}
      <div style={{ fontSize: 22, opacity: 0.85 }}>
        {timeStr}
      </div>
    </div>
  );
};
