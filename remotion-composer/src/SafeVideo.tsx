import React from "react";
import { AbsoluteFill, OffthreadVideo, getRemotionEnvironment } from "remotion";
import { resolveAsset } from "./resolveAsset";

/**
 * OffthreadVideo that survives an empty `src` **in interactive previews**.
 *
 * Several compositions ship `defaultProps` with `videoSrc: ""` (they are
 * driven by pipeline props at render time and have no meaningful stock
 * clip). Opening one in the Studio used to crash the whole composition with
 * Remotion's `No src passed`, so you could never get to the props editor to
 * paste a path in. The Backlot NLE preview embeds the same components via
 * `@remotion/player`, so the guard keys off "not rendering" rather than
 * "is Studio" — both previews stay usable.
 *
 * Rendering keeps the original behaviour: a missing asset must fail loudly
 * rather than silently ship a placeholder card inside a delivered video.
 */
export const SafeVideo: React.FC<
  React.ComponentProps<typeof OffthreadVideo> & { label?: string }
> = ({ src, label, ...rest }) => {
  const resolved = resolveAsset((src ?? "") as string);

  if (!resolved && !getRemotionEnvironment().isRendering) {
    return <MissingMediaPlaceholder label={label} />;
  }

  return <OffthreadVideo src={resolved} {...rest} />;
};

const MissingMediaPlaceholder: React.FC<{ label?: string }> = ({ label }) => (
  <AbsoluteFill
    style={{
      backgroundColor: "#0B1220",
      alignItems: "center",
      justifyContent: "center",
      color: "#94A3B8",
      fontFamily: "system-ui, sans-serif",
      textAlign: "center",
      padding: 48,
      gap: 12,
    }}
  >
    <div style={{ fontSize: 28, color: "#CBD5E1" }}>
      {label ?? "videoSrc"} is empty
    </div>
    <div style={{ fontSize: 18, lineHeight: 1.5, maxWidth: 720 }}>
      Set it in the props editor to preview. This composition is driven by
      pipeline props at render time, so it ships without a stock clip.
    </div>
  </AbsoluteFill>
);
