import { staticFile } from "remotion";
import { CinematicRendererProps } from "./types";

/**
 * Demo fixture for the SignalFromTomorrowWithMusic composition.
 *
 * The four original VEO 3.1 reference clips were never committed to
 * public/ (commit 5223eec added the fixture without its assets), so any
 * browser load of this composition 404'd. The finished 30s master
 * (assets/signal-from-tomorrow-demo.mp4) IS tracked in git — this fixture
 * slices that master into the same scene windows and uses its extracted
 * audio track as the soundtrack, so the demo renders without missing files.
 */
export const signalFromTomorrowWithMusicFixture: CinematicRendererProps = {
  titleFontSize: 78,
  titleWidth: 1320,
  signalLineCount: 18,
  soundtrack: {
    src: staticFile("music/signal-from-tomorrow/demo_30s.m4a"),
    volume: 0.42,
    fadeInSeconds: 1.5,
    fadeOutSeconds: 2.5,
  },
  scenes: [
    {
      id: "sc1",
      kind: "video",
      startSeconds: 0,
      durationSeconds: 4,
      src: staticFile("video/signal-from-tomorrow/demo_final_30s.mp4"),
      tone: "cold",
      trimBeforeSeconds: 1,
      fadeInFrames: 0,
    },
    {
      id: "sc2",
      kind: "video",
      startSeconds: 4,
      durationSeconds: 4,
      src: staticFile("video/signal-from-tomorrow/demo_final_30s.mp4"),
      tone: "steel",
      trimBeforeSeconds: 4,
    },
    {
      id: "sc3",
      kind: "title",
      startSeconds: 8,
      durationSeconds: 3,
      text: "YESTERDAY, THEY LAUNCHED.",
      accent: "#89d7ff",
      intensity: 1,
    },
    {
      id: "sc4",
      kind: "video",
      startSeconds: 11,
      durationSeconds: 7,
      src: staticFile("video/signal-from-tomorrow/demo_final_30s.mp4"),
      tone: "cold",
      trimBeforeSeconds: 11,
    },
    {
      id: "sc5",
      kind: "title",
      startSeconds: 18,
      durationSeconds: 3,
      text: "THE SIGNAL CAME FROM EARTH.",
      accent: "#a6e6ff",
      intensity: 1.15,
    },
    {
      id: "sc6",
      kind: "video",
      startSeconds: 21,
      durationSeconds: 6,
      src: staticFile("video/signal-from-tomorrow/demo_final_30s.mp4"),
      tone: "void",
      trimBeforeSeconds: 21,
    },
    {
      id: "sc7",
      kind: "title",
      startSeconds: 27,
      durationSeconds: 3,
      text: "SIGNAL FROM TOMORROW",
      accent: "#d6f1ff",
      intensity: 0.9,
    },
  ],
};
