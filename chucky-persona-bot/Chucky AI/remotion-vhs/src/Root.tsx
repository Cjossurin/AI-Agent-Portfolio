import React from "react";
import { Composition } from "remotion";
import { RootComposition, CompositionProps } from "./Composition";

const FPS = 30;
const FALLBACK_SCENE_SEC = 12;
const PADDING_SEC = 0.5;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="RootComposition"
        // @ts-expect-error Remotion 4.x LooseComponentType vs typed FC
        component={RootComposition}
        durationInFrames={FPS * FALLBACK_SCENE_SEC}
        fps={FPS}
        width={1080}
        height={1920}
        defaultProps={
          {
            caseId: "preview",
            sequences: [],
            ambientLayers: {
              droneAudio: "assets/shared/drone_audio.mp3",
              vhsStatic: "assets/shared/vhs_static.mp3",
            },
            captions: [],
            effectsIntensity: "medium",
            showTimestamp: true,
          } satisfies CompositionProps
        }
        calculateMetadata={({ props }) => {
          const p = props as unknown as CompositionProps;
          let totalFrames = 0;
          for (const seq of p.sequences) {
            totalFrames += Math.ceil(
              ((seq.audioDurationSec ?? FALLBACK_SCENE_SEC) + PADDING_SEC) * FPS,
            );
          }
          return {
            durationInFrames: Math.max(totalFrames, FPS),
          };
        }}
      />
    </>
  );
};
