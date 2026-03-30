import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

interface KenBurnsProps {
  motionType: string;
  durationInFrames: number;
  children: React.ReactNode;
}

/**
 * Applies a slow, continuous CSS transform to its children based on motionType.
 *
 * Supported motionTypes:
 *   ken_burns_zoom_in   — scale 1.0 → 1.12
 *   ken_burns_zoom_out  — scale 1.12 → 1.0
 *   ken_burns_pan_right — translateX 0% → -5%
 *   ken_burns_pan_left  — translateX -5% → 0%
 *   ken_burns_slow_push — scale 1.0 → 1.06, slight upward drift
 */
export const KenBurnsWrapper: React.FC<KenBurnsProps> = ({
  motionType,
  durationInFrames,
  children,
}) => {
  const frame = useCurrentFrame();

  const progress = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  let transform = "";

  switch (motionType) {
    case "ken_burns_zoom_in":
      transform = `scale(${1 + progress * 0.12})`;
      break;

    case "ken_burns_zoom_out":
      transform = `scale(${1.12 - progress * 0.12})`;
      break;

    case "ken_burns_pan_right":
      transform = `scale(1.08) translateX(${-progress * 5}%)`;
      break;

    case "ken_burns_pan_left":
      transform = `scale(1.08) translateX(${-5 + progress * 5}%)`;
      break;

    case "ken_burns_slow_push":
      transform = `scale(${1 + progress * 0.06}) translateY(${-progress * 2}%)`;
      break;

    default:
      transform = `scale(${1 + progress * 0.08})`;
      break;
  }

  return (
    <AbsoluteFill
      style={{
        transform,
        transformOrigin: "center center",
        willChange: "transform",
      }}
    >
      {children}
    </AbsoluteFill>
  );
};
